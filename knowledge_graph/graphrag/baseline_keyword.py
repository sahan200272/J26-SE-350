"""Flat keyword search baseline comparator for evaluating GraphRAG multi-hop entity gain."""

import re
import time
from typing import Any, Dict, List, Optional, Set
from neo4j import Driver

from graph_schema.schema import get_driver
from graphrag.models import RetrievalRequest, RetrievalResult
from graphrag.retriever import retrieve_subgraph

# Common stop words to exclude from keyword query splitting
STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "is", "are", "was", "were", "what", "who", "when", "where", "why", "how",
    "can", "could", "should", "would", "do", "does", "did", "about", "any",
}


def _extract_query_keywords(query: str) -> List[str]:
    """Tokenize query into non-stopword lowercase terms for keyword search."""
    tokens = re.findall(r"\b[a-zA-Z0-9_\-]+\b", query.lower())
    terms = [t for t in tokens if t not in STOP_WORDS and len(t) >= 3]
    return terms or tokens


def keyword_baseline_search(
    query: str,
    top_k: int = 15,
    driver: Optional[Driver] = None,
    include_private: bool = False,
) -> Dict[str, Any]:
    """Execute a non-graph flat keyword search baseline without relationship traversal.

    Matches query terms only against individual node name and description properties.
    """
    start_time = time.perf_counter()
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    terms = _extract_query_keywords(query)
    results: List[Dict[str, Any]] = []

    if not terms:
        return {
            "query": query,
            "terms": [],
            "nodes": [],
            "count": 0,
            "latency_ms": round((time.perf_counter() - start_time) * 1000.0, 2),
        }

    cypher = """
    MATCH (n)
    WHERE NOT n:Conversation
      AND n.key IS NOT NULL
      AND ($include_private OR coalesce(n['sensitivity'], 'normal') <> 'private')
      AND ANY(term IN $terms WHERE
          (n.name IS NOT NULL AND toLower(n.name) CONTAINS term)
          OR (n['description'] IS NOT NULL AND toLower(n['description']) CONTAINS term)
      )
    RETURN n.key AS key,
           n.name AS name,
           labels(n)[0] AS type,
           n['description'] AS description,
           n['status'] AS status,
           n['priority'] AS priority
    LIMIT $top_k
    """

    try:
        with driver.session() as session:
            records = session.run(
                cypher,
                terms=terms,
                include_private=include_private,
                top_k=top_k,
            )
            for rec in records:
                if not rec.get("key"):
                    continue
                results.append({
                    "key": str(rec["key"]),
                    "name": str(rec.get("name") or rec["key"]),
                    "type": rec.get("type") or "Concept",
                    "description": rec.get("description"),
                    "status": rec.get("status"),
                    "priority": rec.get("priority"),
                })
    finally:
        if close_driver:
            driver.close()

    latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    return {
        "query": query,
        "terms": terms,
        "nodes": results,
        "count": len(results),
        "latency_ms": latency_ms,
    }


def compare_retrieval(
    request: RetrievalRequest,
    driver: Optional[Driver] = None,
) -> Dict[str, Any]:
    """Compare GraphRAG multi-hop retrieval against the flat keyword baseline.

    Calculates:
      - Multi-hop entity gain: Entities uncovered through relational paths that flat keywords missed.
      - Structural gain: Connected relational paths vs isolated node hits.
    """
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    try:
        # 1. Execute GraphRAG multi-hop retrieval
        graph_res: RetrievalResult = retrieve_subgraph(request, driver=driver)

        # 2. Execute flat keyword baseline
        keyword_res = keyword_baseline_search(
            query=request.query,
            top_k=request.top_k,
            driver=driver,
            include_private=request.include_private,
        )

        graph_keys = {n["key"] for n in graph_res.nodes}
        keyword_keys = {n["key"] for n in keyword_res["nodes"]}

        # Entities reached via relational graph traversal that keyword search completely missed
        gain_keys = graph_keys - keyword_keys
        gain_entities = [n for n in graph_res.nodes if n["key"] in gain_keys]

        summary_narrative = (
            f"GraphRAG discovered {len(graph_keys)} entities and {len(graph_res.ranked_paths)} "
            f"relational paths across {request.max_hops}-hop traversal. "
            f"Flat keyword search matched {len(keyword_keys)} isolated nodes. "
            f"Multi-hop entity gain: {len(gain_entities)} entities ({', '.join(g['name'] for g in gain_entities[:5]) or 'None'}) "
            f"uncovered through relationship links that did not contain query keywords."
        )

        return {
            "query": request.query,
            "detected_intent": graph_res.detected_intent,
            "max_hops": request.max_hops,
            "metrics": {
                "graphrag_entity_count": len(graph_keys),
                "keyword_entity_count": len(keyword_keys),
                "multi_hop_gain_count": len(gain_entities),
                "graphrag_paths_found": len(graph_res.ranked_paths),
                "graphrag_latency_ms": graph_res.latency_ms,
                "keyword_latency_ms": keyword_res["latency_ms"],
            },
            "multi_hop_entity_gain": gain_entities,
            "graphrag_result": graph_res.model_dump(),
            "keyword_baseline": keyword_res,
            "summary": summary_narrative,
        }
    finally:
        if close_driver:
            driver.close()
