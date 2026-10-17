"""Graph ingestion engine for entity and relationship payloads."""

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from neo4j import Driver, ManagedTransaction, Transaction
from rapidfuzz.fuzz import token_sort_ratio

from graph_schema.models import (
    ALLOWED_NODE_LABELS,
    ALLOWED_RELATIONSHIP_TYPES,
    SINGLE_VALUED_RELATIONSHIPS,
    SYMMETRIC_RELATIONSHIPS,
    Entity,
    EntityRef,
    Payload,
    Relationship,
    canonical_pair,
    normalize_key,
)
from graph_schema.schema import get_driver

logger = logging.getLogger(__name__)

ALIAS_THRESHOLD: int = 90

ALLOWED_EDGE_PROPS: Set[str] = {"confidence", "kind", "label", "quote"}

PROVENANCE_CREATED_IN_LABELS: Set[str] = {
    "Task",
    "Decision",
    "Issue",
    "Question",
    "Idea",
    "Note",
    "Document",
}


@dataclass
class IngestResult:
    """Summary of operations performed during payload ingestion."""

    nodes_created: int = 0
    nodes_merged: int = 0
    edges_created: int = 0
    edges_merged: int = 0
    edges_replaced: int = 0
    aliases_added: int = 0
    warnings: List[str] = field(default_factory=list)
    touched: Set[Tuple[str, str]] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Convert IngestResult to JSON-serializable dictionary."""
        return {
            "nodes_created": self.nodes_created,
            "nodes_merged": self.nodes_merged,
            "edges_created": self.edges_created,
            "edges_merged": self.edges_merged,
            "edges_replaced": self.edges_replaced,
            "aliases_added": self.aliases_added,
            "warnings": self.warnings,
            "touched": [list(t) for t in sorted(self.touched)],
        }


def compute_meeting_key(
    name: str,
    props: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None,
) -> str:
    """Compute normalized key for a Meeting entity.

    If a date is known (props['date'] or payload timestamp date part),
    returns normalize_key(f'{name} {date}'), otherwise normalize_key(name).
    """
    date_val = None
    if props and props.get("date"):
        date_val = str(props["date"]).strip()
    elif timestamp:
        ts = timestamp.strip()
        if "T" in ts:
            date_val = ts.split("T")[0]
        elif len(ts) >= 10 and ts[:10].count("-") == 2:
            date_val = ts[:10]

    if date_val:
        return normalize_key(f"{name} {date_val}")
    return normalize_key(name)


def _load_keys_for_label(
    tx: Any,
    label: str,
) -> Dict[str, Dict[str, Any]]:
    """Load all existing keys, names, and aliases for a label from Neo4j."""
    assert label in ALLOWED_NODE_LABELS, f"Invalid node label: {label}"
    query = f"MATCH (n:{label}) RETURN n.key AS key, n.name AS name, n.aliases AS aliases"
    result = tx.run(query)
    cache: Dict[str, Dict[str, Any]] = {}
    for record in result:
        key = record["key"]
        aliases = record.get("aliases") or []
        cache[key] = {
            "name": record.get("name") or key,
            "aliases": list(aliases) if isinstance(aliases, list) else [],
        }
    return cache


def _resolve_entity_key(
    tx: Any,
    label: str,
    candidate_key: str,
    display_name: str,
    label_cache: Dict[str, Dict[str, Dict[str, Any]]],
    result: IngestResult,
) -> Tuple[str, bool]:
    """Resolve an entity key against existing nodes using exact or fuzzy matching.

    Returns:
        Tuple of (resolved_key, is_fuzzy_match).
    """
    assert label in ALLOWED_NODE_LABELS, f"Invalid node label: {label}"
    if label not in label_cache:
        label_cache[label] = _load_keys_for_label(tx, label)

    cache = label_cache[label]

    # 1. Exact key match
    if candidate_key in cache:
        return candidate_key, False

    # Deadlines represent calendar dates and must never be fuzzy-merged across different dates
    if label == "Deadline":
        cache[candidate_key] = {"name": display_name, "aliases": []}
        return candidate_key, False

    # 2. Fuzzy match against existing keys
    best_key: Optional[str] = None
    best_ratio: float = 0.0

    for existing_key in cache:
        ratio = float(token_sort_ratio(candidate_key, existing_key))
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = existing_key

    if best_key is not None and best_ratio >= ALIAS_THRESHOLD:
        # Fuzzy match: reuse existing node and add display_name to aliases
        entry = cache[best_key]
        existing_aliases = entry["aliases"]
        if display_name != entry["name"] and display_name not in existing_aliases:
            entry["aliases"].append(display_name)
            result.aliases_added += 1
            alias_query = (
                f"MATCH (n:{label} {{key: $key}}) "
                f"SET n.aliases = CASE "
                f"WHEN n.aliases IS NULL THEN [$alias] "
                f"WHEN NOT $alias IN n.aliases THEN n.aliases + $alias "
                f"ELSE n.aliases END"
            )
            tx.run(alias_query, key=best_key, alias=display_name)

        return best_key, True

    # 3. No match: record candidate in cache
    cache[candidate_key] = {"name": display_name, "aliases": []}
    return candidate_key, False


def _ingest_payload_in_tx(tx: Any, payload: Payload) -> IngestResult:
    """Execute ingestion logic within a single Neo4j transaction."""
    result = IngestResult()
    label_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
    resolved_entity_keys: Dict[Tuple[str, str], str] = {}

    # 1. Process entities
    for entity in payload.entities:
        if entity.op == "retract":
            # TODO(RP-29): Implement entity retraction and tombstone history
            logger.warning(
                "Entity '%s' (%s) has op='retract'; skipped deletion (TODO(RP-29)).",
                entity.name,
                entity.type,
            )
            result.warnings.append(
                f"Entity '{entity.name}' ({entity.type}) has op='retract'; skipped deletion (TODO(RP-29))."
            )
            continue

        label = entity.type
        assert label in ALLOWED_NODE_LABELS, f"Invalid node label: {label}"

        if label == "Meeting":
            candidate_key = compute_meeting_key(entity.name, entity.props, payload.timestamp)
        else:
            candidate_key = normalize_key(entity.name)

        resolved_key, is_fuzzy = _resolve_entity_key(
            tx=tx,
            label=label,
            candidate_key=candidate_key,
            display_name=entity.name,
            label_cache=label_cache,
            result=result,
        )
        resolved_entity_keys[(label, normalize_key(entity.name))] = resolved_key

        clean_props = dict(entity.props)

        if is_fuzzy:
            merge_query = (
                f"MERGE (n:{label} {{key: $key}}) "
                f"ON MATCH SET n.updated_at = datetime(), n += $props"
            )
            res = tx.run(merge_query, key=resolved_key, props=clean_props)
            res.consume()
            result.nodes_merged += 1
        else:
            merge_query = (
                f"MERGE (n:{label} {{key: $key}}) "
                f"ON CREATE SET n.name = $name, n.created_at = datetime(), n.updated_at = datetime(), n += $props "
                f"ON MATCH SET n.updated_at = datetime(), n += $props"
            )
            res = tx.run(merge_query, key=resolved_key, name=entity.name, props=clean_props)
            summary = res.consume()
            if summary.counters.nodes_created > 0:
                result.nodes_created += 1
            else:
                result.nodes_merged += 1

        result.touched.add((label, resolved_key))

    # Helper to resolve or create endpoint entity
    def ensure_endpoint(ref: EntityRef) -> str:
        label = ref.type
        assert label in ALLOWED_NODE_LABELS, f"Invalid node label: {label}"
        name_key = normalize_key(ref.name)
        lookup_key = (label, name_key)
        if lookup_key in resolved_entity_keys:
            return resolved_entity_keys[lookup_key]

        if label == "Meeting":
            cand_key = compute_meeting_key(ref.name, None, payload.timestamp)
        else:
            cand_key = name_key

        target_key, _ = _resolve_entity_key(
            tx=tx,
            label=label,
            candidate_key=cand_key,
            display_name=ref.name,
            label_cache=label_cache,
            result=result,
        )
        resolved_entity_keys[lookup_key] = target_key

        # MERGE endpoint node to ensure it exists
        merge_query = (
            f"MERGE (n:{label} {{key: $key}}) "
            f"ON CREATE SET n.name = $name, n.created_at = datetime(), n.updated_at = datetime() "
            f"ON MATCH SET n.updated_at = datetime()"
        )
        res = tx.run(merge_query, key=target_key, name=ref.name)
        summary = res.consume()
        if summary.counters.nodes_created > 0:
            result.nodes_created += 1
        else:
            result.nodes_merged += 1

        result.touched.add((label, target_key))
        return target_key

    # 2. Process relationships
    for rel in payload.relationships:
        if rel.op == "retract":
            # TODO(RP-29): Implement relationship retraction and conflict policy
            logger.warning(
                "Relationship '%s' from '%s' to '%s' has op='retract'; skipped deletion (TODO(RP-29)).",
                rel.type,
                rel.from_entity.name,
                rel.to_entity.name,
            )
            result.warnings.append(
                f"Relationship '{rel.type}' from '{rel.from_entity.name}' to '{rel.to_entity.name}' has op='retract'; skipped deletion (TODO(RP-29))."
            )
            continue

        rel_type = rel.type
        assert rel_type in ALLOWED_RELATIONSHIP_TYPES, f"Invalid relationship type: {rel_type}"

        from_label = rel.from_entity.type
        to_label = rel.to_entity.type
        assert from_label in ALLOWED_NODE_LABELS, f"Invalid from label: {from_label}"
        assert to_label in ALLOWED_NODE_LABELS, f"Invalid to label: {to_label}"

        from_key = ensure_endpoint(rel.from_entity)
        to_key = ensure_endpoint(rel.to_entity)
        from_name = rel.from_entity.name
        to_name = rel.to_entity.name

        # Symmetric ordering check
        if rel_type in SYMMETRIC_RELATIONSHIPS:
            canon_from, canon_to = canonical_pair(rel_type, from_key, to_key)
            if canon_from != from_key:
                from_key, to_key = canon_from, canon_to
                from_label, to_label = to_label, from_label
                from_name, to_name = to_name, from_name

        # Single-valued relationship replacement check
        if rel_type in SINGLE_VALUED_RELATIONSHIPS:
            check_query = (
                f"MATCH (a:{from_label} {{key: $from_key}})-[r:{rel_type}]->(c) "
                f"WHERE c.key <> $to_key "
                f"RETURN c.key AS old_key, c.name AS old_name"
            )
            check_res = tx.run(check_query, from_key=from_key, to_key=to_key)
            old_targets = list(check_res)
            if old_targets:
                for rec in old_targets:
                    old_display = rec.get("old_name") or rec.get("old_key")
                    new_display = to_name or to_key
                    # TODO(RP-29): Create Change/history nodes and apply conflict policy
                    result.warnings.append(f"{rel_type}: {old_display} -> {new_display}")
                    result.edges_replaced += 1

                del_query = (
                    f"MATCH (a:{from_label} {{key: $from_key}})-[r:{rel_type}]->(c) "
                    f"WHERE c.key <> $to_key "
                    f"DELETE r"
                )
                tx.run(del_query, from_key=from_key, to_key=to_key)

        # Merge relationship edge
        edge_props = {k: v for k, v in rel.props.items() if k in ALLOWED_EDGE_PROPS}
        merge_rel_query = (
            f"MATCH (a:{from_label} {{key: $from_key}}) "
            f"MATCH (b:{to_label} {{key: $to_key}}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            f"ON CREATE SET r.created_at = datetime(), r.source = $source, r.last_seen = datetime(), r += $props "
            f"ON MATCH SET r.last_seen = datetime(), r += $props"
        )
        res = tx.run(
            merge_rel_query,
            from_key=from_key,
            to_key=to_key,
            source=payload.source,
            props=edge_props,
        )
        summary = res.consume()
        if summary.counters.relationships_created > 0:
            result.edges_created += 1
        else:
            result.edges_merged += 1

    # 3. Provenance linking
    conv_key = normalize_key(payload.source)
    conv_name = payload.source
    assert "Conversation" in ALLOWED_NODE_LABELS
    conv_query = (
        "MERGE (c:Conversation {key: $key}) "
        "ON CREATE SET c.name = $name, c.created_at = datetime(), c.updated_at = datetime() "
        "ON MATCH SET c.updated_at = datetime()"
    )
    conv_res = tx.run(conv_query, key=conv_key, name=conv_name)
    conv_summary = conv_res.consume()
    if conv_summary.counters.nodes_created > 0:
        result.nodes_created += 1
    else:
        result.nodes_merged += 1

    touched_entities = list(result.touched)
    for label, entity_key in touched_entities:
        if label == "Conversation" and entity_key == conv_key:
            continue

        assert label in ALLOWED_NODE_LABELS
        if label in PROVENANCE_CREATED_IN_LABELS:
            assert "CREATED_IN" in ALLOWED_RELATIONSHIP_TYPES
            prov_query = (
                f"MATCH (e:{label} {{key: $entity_key}}) "
                f"MATCH (c:Conversation {{key: $conv_key}}) "
                f"MERGE (e)-[r:CREATED_IN]->(c) "
                f"ON CREATE SET r.created_at = datetime(), r.source = $source, r.last_seen = datetime() "
                f"ON MATCH SET r.last_seen = datetime()"
            )
        else:
            assert "MENTIONS" in ALLOWED_RELATIONSHIP_TYPES
            prov_query = (
                f"MATCH (c:Conversation {{key: $conv_key}}) "
                f"MATCH (e:{label} {{key: $entity_key}}) "
                f"MERGE (c)-[r:MENTIONS]->(e) "
                f"ON CREATE SET r.created_at = datetime(), r.source = $source, r.last_seen = datetime() "
                f"ON MATCH SET r.last_seen = datetime()"
            )

        prov_res = tx.run(
            prov_query,
            entity_key=entity_key,
            conv_key=conv_key,
            source=payload.source,
        )
        prov_summary = prov_res.consume()
        if prov_summary.counters.relationships_created > 0:
            result.edges_created += 1
        else:
            result.edges_merged += 1

    result.touched.add(("Conversation", conv_key))

    return result


def ingest_payload(
    payload: Payload,
    driver: Optional[Driver] = None,
    dry_run: bool = False,
) -> IngestResult:
    """Ingest a Payload into the Neo4j graph database.

    Args:
        payload: Validated Payload object containing entities and relationships.
        driver: Optional Neo4j Driver. If None, schema.get_driver() is used.
        dry_run: If True, execute within a transaction that is rolled back,
                 returning what would have been created without writing changes.

    Returns:
        IngestResult summarizing nodes/edges created, merged, replaced, and warnings.
    """
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    try:
        with driver.session() as session:
            if dry_run:
                tx = session.begin_transaction()
                try:
                    result = _ingest_payload_in_tx(tx, payload)
                finally:
                    tx.rollback()
                    tx.close()
            else:
                result = session.execute_write(_ingest_payload_in_tx, payload)

        logger.info(
            "Ingestion completed for source '%s': nodes_created=%d, nodes_merged=%d, "
            "edges_created=%d, edges_merged=%d, edges_replaced=%d, aliases_added=%d, warnings=%d",
            payload.source,
            result.nodes_created,
            result.nodes_merged,
            result.edges_created,
            result.edges_merged,
            result.edges_replaced,
            result.aliases_added,
            len(result.warnings),
        )
        return result
    finally:
        if close_driver:
            driver.close()
