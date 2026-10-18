"""Constrained Multi-Hop GraphRAG Traversal Engine and Mathematical Scorer."""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from neo4j import Driver, Session

from graph_schema.models import normalize_key
from graph_schema.schema import get_driver
from graphrag.anchor_resolver import (
    detect_query_intent,
    get_relationship_intent_salience,
    resolve_seed_anchors,
)
from graphrag.models import (
    AnchorMatch,
    PathHop,
    ProvenanceRef,
    RetrievalRequest,
    RetrievalResult,
    ScoredPath,
)

logger = logging.getLogger(__name__)


def compute_recency_score(props: Dict[str, Any], reference_time: Optional[datetime] = None) -> float:
    """Calculate a recency score [0.0..1.0] from timestamp or date properties.

    Score decay schedule:
      - Within 7 days: 1.00
      - Within 30 days: 0.85
      - Within 90 days: 0.70
      - Within 365 days: 0.50
      - Older than 1 year: 0.30
      - Missing/unparseable timestamp: 0.60
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # Inspect common date/time keys
    date_val = None
    for key in ("updated_at", "created_at", "last_seen", "timestamp", "date"):
        if key in props and props[key]:
            date_val = props[key]
            break

    if not date_val:
        return 0.60

    try:
        # Handle Neo4j DateTime object or string
        if hasattr(date_val, "to_native"):
            dt = date_val.to_native()
        elif isinstance(date_val, str):
            clean = date_val.replace("Z", "+00:00")
            if "T" in clean:
                dt = datetime.fromisoformat(clean)
            else:
                dt = datetime.fromisoformat(clean + "T00:00:00+00:00")
        elif isinstance(date_val, datetime):
            dt = date_val
        else:
            return 0.60

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        delta_days = abs((reference_time - dt).total_seconds()) / 86400.0
        if delta_days <= 7.0:
            return 1.00
        elif delta_days <= 30.0:
            return 0.85
        elif delta_days <= 90.0:
            return 0.70
        elif delta_days <= 365.0:
            return 0.50
        else:
            return 0.30
    except Exception:
        return 0.60


def score_path(
    path_nodes: List[Dict[str, Any]],
    path_hops: List[PathHop],
    intent: str,
) -> ScoredPath:
    """Compute mathematical composite score for a multi-hop relational path.

    Formula (Jira RP-27):
      final_score = 0.35 * (0.75 ** (d - 1)) + 0.25 * mean_conf + 0.25 * mean_intent + 0.15 * recency
    """
    d = len(path_hops)
    assert d >= 1, "Path must contain at least 1 hop"

    # 1. Hop decay: 0.75 ** (d - 1)
    hop_decay = 0.75 ** (d - 1)

    # 2. Confidence score: mean of edge confidences
    confidences = [h.confidence for h in path_hops]
    confidence_score = sum(confidences) / len(confidences) if confidences else 1.0

    # 3. Intent salience: mean of intent-aligned edge weights
    saliences = [
        get_relationship_intent_salience(h.relationship_type, intent)  # type: ignore[arg-type]
        for h in path_hops
    ]
    intent_salience = sum(saliences) / len(saliences) if saliences else 0.5

    # 4. Recency score: mean recency across nodes and edges
    recencies = []
    for node in path_nodes:
        recencies.append(compute_recency_score(node.get("props", {})))
    for hop in path_hops:
        recencies.append(compute_recency_score(hop.props))
    recency_score = sum(recencies) / len(recencies) if recencies else 0.60

    # Composite formula
    final_score = (
        0.35 * hop_decay
        + 0.25 * confidence_score
        + 0.25 * intent_salience
        + 0.15 * recency_score
    )

    rel_types = [h.relationship_type for h in path_hops]

    return ScoredPath(
        nodes=path_nodes,
        relationships=rel_types,
        hops=path_hops,
        length=d,
        hop_decay=round(hop_decay, 4),
        confidence_score=round(confidence_score, 4),
        intent_salience=round(intent_salience, 4),
        recency_score=round(recency_score, 4),
        final_score=round(final_score, 4),
    )


def _extract_node_dict(node: Any) -> Dict[str, Any]:
    """Helper to convert Neo4j node or dict to standardized node dict."""
    if isinstance(node, dict):
        props = dict(node.get("props", {}))
        for k, v in node.items():
            if k not in ("key", "name", "type", "props"):
                props[k] = v
        return {
            "key": node["key"],
            "name": node.get("name") or node["key"],
            "type": node.get("type", "Concept"),
            "props": props,
        }

    # Neo4j Node object
    labels = list(node.labels) if hasattr(node, "labels") else ["Concept"]
    props = dict(node.items()) if hasattr(node, "items") else {}
    node_type = labels[0] if labels else "Concept"
    key = props.get("key", "")
    name = props.get("name", key)
    clean_props = {k: v for k, v in props.items() if k not in ("key", "name")}

    return {
        "key": key,
        "name": name,
        "type": node_type,
        "props": clean_props,
    }


def _expand_alias_anchors(session: Any, anchors: List[AnchorMatch]) -> List[AnchorMatch]:
    """Expand anchors across transparent ALIAS_OF edges."""
    expanded: Dict[str, AnchorMatch] = {a.key: a for a in anchors}

    for anchor in list(anchors):
        query = """
        MATCH (a {key: $key})-[:ALIAS_OF]-(canonical)
        WHERE NOT canonical:Conversation
        RETURN canonical.key AS key,
               canonical.name AS name,
               labels(canonical)[0] AS type
        """
        records = session.run(query, key=anchor.key)
        for rec in records:
            ckey = rec["key"]
            if ckey not in expanded:
                expanded[ckey] = AnchorMatch(
                    key=ckey,
                    name=rec.get("name") or ckey,
                    type=rec.get("type") or "Concept",
                    match_type="exact_alias",
                    score=anchor.score,
                )

    return list(expanded.values())


def _fetch_provenance_for_nodes(
    session: Any,
    node_keys: Set[str],
) -> List[ProvenanceRef]:
    """Retrieve Conversation provenance sources for nodes (hub suppression)."""
    if not node_keys:
        return []

    provenance_list: List[ProvenanceRef] = []
    seen = set()

    query = """
    MATCH (c:Conversation)-[r:MENTIONS]->(n)
    WHERE n.key IN $keys
    RETURN c.key AS ckey, c.name AS cname, 'MENTIONS' AS rel, n.key AS ekey, r.source AS source, r.created_at AS ts
    UNION
    MATCH (n)-[r:CREATED_IN]->(c:Conversation)
    WHERE n.key IN $keys
    RETURN c.key AS ckey, c.name AS cname, 'CREATED_IN' AS rel, n.key AS ekey, r.source AS source, r.created_at AS ts
    """
    records = session.run(query, keys=list(node_keys))
    for rec in records:
        ckey = rec["ckey"]
        ekey = rec["ekey"]
        rel = rec["rel"]
        pair = (ckey, rel, ekey)
        if pair not in seen:
            seen.add(pair)
            provenance_list.append(
                ProvenanceRef(
                    conversation_key=ckey,
                    conversation_name=rec.get("cname") or ckey,
                    relationship=rel,
                    entity_key=ekey,
                    source=str(rec.get("source")) if rec.get("source") else None,
                    timestamp=str(rec.get("ts")) if rec.get("ts") else None,
                )
            )

    return provenance_list


def retrieve_subgraph(
    request: RetrievalRequest,
    driver: Optional[Driver] = None,
) -> RetrievalResult:
    """Execute constrained multi-hop GraphRAG traversal with composite path scoring.

    Enforces:
      - Provenance Hub Suppression: Intermediate hops strictly forbid :Conversation nodes.
      - Alias Transparency: Transparent traversal of ALIAS_OF edges.
      - Privacy Filtering: Filter nodes with sensitivity='private' when include_private=False.
      - Bounded Traversal: max_hops strictly bounded 1..3.
      - Mathematical Scoring: final_score = 0.35*decay + 0.25*conf + 0.25*intent + 0.15*recency.
    """
    start_time = time.perf_counter()

    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    intent = request.intent or detect_query_intent(request.query)
    max_hops = max(1, min(3, int(request.max_hops)))

    try:
        with driver.session() as session:
            # 1. Resolve Seed Anchors
            anchors = resolve_seed_anchors(
                session=session,
                query=request.query,
                seed_entities=request.seed_entities,
                include_private=request.include_private,
            )

            # Expand anchors with alias transparency
            anchors = _expand_alias_anchors(session, anchors)

            if not anchors:
                from graphrag.context_builder import build_formatted_context

                empty_result = RetrievalResult(
                    query=request.query,
                    detected_intent=intent,
                    anchors=[],
                    nodes=[],
                    edges=[],
                    ranked_paths=[],
                    provenance=[],
                    formatted_context="",
                    latency_ms=round((time.perf_counter() - start_time) * 1000.0, 2),
                )
                empty_result.formatted_context = build_formatted_context(empty_result)
                return empty_result

            anchor_keys = [a.key for a in anchors]

            # 2. Constrained Multi-Hop Path Traversal Query
            # Intermediate nodes: NOT Conversation, and privacy compliant.
            # Terminal nodes: NOT Conversation, and privacy compliant.
            traversal_cypher = f"""
            MATCH (a)
            WHERE a.key IN $anchor_keys
            MATCH p = (a)-[r*1..{max_hops}]-(b)
            WHERE ALL(n IN nodes(p) WHERE n.key IS NOT NULL AND ($include_private OR coalesce(n['sensitivity'], 'normal') <> 'private'))
              AND ALL(n IN nodes(p)[1..-1] WHERE NOT n:Conversation)
              AND NOT b:Conversation
            RETURN p
            """

            records = session.run(
                traversal_cypher,
                anchor_keys=anchor_keys,
                include_private=request.include_private,
            )

            raw_paths: List[ScoredPath] = []
            seen_signatures: Set[Tuple[Any, ...]] = set()

            for rec in records:
                p = rec["p"]
                p_nodes = [_extract_node_dict(n) for n in p.nodes]
                p_rels = list(p.relationships)

                # Prevent cyclic loops
                node_keys = [n["key"] for n in p_nodes]
                if len(set(node_keys)) != len(node_keys):
                    continue

                # Build hops sequence
                hops: List[PathHop] = []
                for i in range(len(p_rels)):
                    r = p_rels[i]
                    from_dict = p_nodes[i]
                    to_dict = p_nodes[i + 1]

                    rel_props = dict(r.items()) if hasattr(r, "items") else {}
                    confidence = float(rel_props.get("confidence", 1.0))
                    clean_props = {k: v for k, v in rel_props.items() if k != "confidence"}

                    hops.append(
                        PathHop(
                            from_node={
                                "key": from_dict["key"],
                                "name": from_dict["name"],
                                "type": from_dict["type"],
                            },
                            relationship_type=r.type,
                            to_node={
                                "key": to_dict["key"],
                                "name": to_dict["name"],
                                "type": to_dict["type"],
                            },
                            confidence=round(confidence, 4),
                            props=clean_props,
                        )
                    )

                sig = tuple(
                    (node_keys[i], hops[i].relationship_type, node_keys[i + 1])
                    for i in range(len(hops))
                )
                if sig in seen_signatures:
                    continue
                seen_signatures.add(sig)

                scored = score_path(p_nodes, hops, intent)
                raw_paths.append(scored)

            # Sort paths by final_score descending
            raw_paths.sort(key=lambda x: x.final_score, reverse=True)
            top_paths = raw_paths[: request.top_k]

            # 3. Extract Subgraph Nodes and Edges
            subgraph_nodes_dict: Dict[str, Dict[str, Any]] = {}
            subgraph_edges: List[Dict[str, Any]] = []
            seen_edge_signatures: Set[Tuple[str, str, str]] = set()

            # Seed anchor nodes
            for a in anchors:
                if a.key not in subgraph_nodes_dict:
                    subgraph_nodes_dict[a.key] = {
                        "key": a.key,
                        "name": a.name,
                        "type": a.type,
                        "props": {},
                    }

            # Elements from top ranked paths
            for path in top_paths:
                for n in path.nodes:
                    if n["key"] not in subgraph_nodes_dict:
                        subgraph_nodes_dict[n["key"]] = n

                for hop in path.hops:
                    edge_sig = (
                        hop.from_node["key"],
                        hop.relationship_type,
                        hop.to_node["key"],
                    )
                    if edge_sig not in seen_edge_signatures:
                        seen_edge_signatures.add(edge_sig)
                        subgraph_edges.append({
                            "from": hop.from_node["key"],
                            "from_name": hop.from_node["name"],
                            "from_type": hop.from_node["type"],
                            "type": hop.relationship_type,
                            "to": hop.to_node["key"],
                            "to_name": hop.to_node["name"],
                            "to_type": hop.to_node["type"],
                            "confidence": hop.confidence,
                            "props": hop.props,
                        })

            # 4. Provenance Collection (Hub-Suppressed Attachment)
            all_node_keys = set(subgraph_nodes_dict.keys())
            provenance = _fetch_provenance_for_nodes(session, all_node_keys)

            latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            from graphrag.context_builder import build_formatted_context

            result = RetrievalResult(
                query=request.query,
                detected_intent=intent,
                anchors=anchors,
                nodes=list(subgraph_nodes_dict.values()),
                edges=subgraph_edges,
                ranked_paths=top_paths,
                provenance=provenance,
                formatted_context="",
                latency_ms=latency_ms,
            )

            result.formatted_context = build_formatted_context(result)
            return result
    finally:
        if close_driver:
            driver.close()
