"""Integration tests for GraphRAG constrained multi-hop retrieval against Neo4j.

Runs only when KG_INTEGRATION=1 and Neo4j is reachable.
CRITICAL: These tests MUST NOT wipe the running database. All test entities
use keys/names prefixed with 'zz test' or 'conv_zz_test'.
"""

import os
from typing import Generator
import pytest

from graph_schema.ingest import ingest_payload
from graph_schema.models import Entity, EntityRef, Payload, Relationship
from graph_schema.schema import get_driver
from graphrag.baseline_keyword import compare_retrieval, keyword_baseline_search
from graphrag.context_builder import get_pending_items_context
from graphrag.models import RetrievalRequest, RetrievalResult
from graphrag.retriever import retrieve_subgraph


def is_neo4j_reachable() -> bool:
    """Check if Neo4j instance is reachable."""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


skip_integration = pytest.mark.skipif(
    os.getenv("KG_INTEGRATION") != "1" or not is_neo4j_reachable(),
    reason="Integration tests skipped unless KG_INTEGRATION=1 and Neo4j is reachable",
)


@pytest.fixture(autouse=True)
def clean_test_graph() -> Generator[None, None, None]:
    """Clean up only nodes whose key starts with 'zz test' or 'conv_zz_test'."""
    def _cleanup() -> None:
        try:
            driver = get_driver()
            with driver.session() as session:
                session.run(
                    "MATCH (n) WHERE n.key STARTS WITH 'zz test' "
                    "OR (n:Conversation AND n.key STARTS WITH 'conv_zz_test') "
                    "DETACH DELETE n"
                )
            driver.close()
        except Exception:
            pass

    _cleanup()
    yield
    _cleanup()


@pytest.mark.integration
@skip_integration
def test_graphrag_1hop_traversal_and_scoring() -> None:
    """Verify 1-hop traversal from seed anchor with mathematical scoring."""
    payload = Payload(
        source="conv_zz_test_graphrag_1hop",
        entities=[
            Entity(type="Person", name="zz test Alice"),
            Entity(type="Task", name="zz test Implement feature", props={"status": "in progress"}),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Implement feature"),
                type="ASSIGNED_TO",
                to_entity=EntityRef(type="Person", name="zz test Alice"),
                props={"confidence": 0.95},
            )
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    try:
        req = RetrievalRequest(
            query="Who is assigned to zz test Implement feature?",
            max_hops=1,
            top_k=5,
        )
        res: RetrievalResult = retrieve_subgraph(req, driver=driver)

        assert res.detected_intent == "task_status"
        assert len(res.anchors) >= 1
        assert any(a.key == "zz test implement feature" for a in res.anchors)

        assert len(res.ranked_paths) >= 1
        top_p = res.ranked_paths[0]
        assert top_p.length == 1
        assert top_p.hop_decay == 1.0
        assert top_p.final_score > 0.80

        node_keys = {n["key"] for n in res.nodes}
        assert "zz test alice" in node_keys
        assert "zz test implement feature" in node_keys
    finally:
        driver.close()


@pytest.mark.integration
@skip_integration
def test_graphrag_2hop_and_3hop_traversal() -> None:
    """Verify 2-hop and 3-hop traversal chains across related entities."""
    # Chain: Task -> Person -> Team -> Tool
    payload = Payload(
        source="conv_zz_test_graphrag_multihop",
        entities=[
            Entity(type="Task", name="zz test Benchmark Core", props={"priority": "high", "status": "open"}),
            Entity(type="Person", name="zz test Bob"),
            Entity(type="Team", name="zz test AI Core Team"),
            Entity(type="Tool", name="zz test Neo4j Engine"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Benchmark Core"),
                type="ASSIGNED_TO",
                to_entity=EntityRef(type="Person", name="zz test Bob"),
            ),
            Relationship(
                from_entity=EntityRef(type="Person", name="zz test Bob"),
                type="MEMBER_OF",
                to_entity=EntityRef(type="Team", name="zz test AI Core Team"),
            ),
            Relationship(
                from_entity=EntityRef(type="Team", name="zz test AI Core Team"),
                type="USES",
                to_entity=EntityRef(type="Tool", name="zz test Neo4j Engine"),
            ),
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    try:
        # 2-hop query from Task anchor: should reach Team
        req_2hop = RetrievalRequest(
            query="zz test Benchmark Core team",
            max_hops=2,
            top_k=10,
        )
        res_2hop = retrieve_subgraph(req_2hop, driver=driver)
        node_keys_2hop = {n["key"] for n in res_2hop.nodes}
        assert "zz test ai core team" in node_keys_2hop
        assert any(p.length == 2 for p in res_2hop.ranked_paths)

        # 3-hop query from Task anchor: should reach Tool
        req_3hop = RetrievalRequest(
            query="zz test Benchmark Core tools",
            max_hops=3,
            top_k=15,
        )
        res_3hop = retrieve_subgraph(req_3hop, driver=driver)
        node_keys_3hop = {n["key"] for n in res_3hop.nodes}
        assert "zz test neo4j engine" in node_keys_3hop
        assert any(p.length == 3 for p in res_3hop.ranked_paths)
    finally:
        driver.close()


@pytest.mark.integration
@skip_integration
def test_graphrag_provenance_hub_suppression() -> None:
    """Verify :Conversation nodes are NOT used as bridge hops during multi-hop expansion."""
    payload = Payload(
        source="conv_zz_test_hub_session",
        entities=[
            Entity(type="Task", name="zz test Task In Audio"),
            Entity(type="Person", name="zz test Unrelated Person In Audio"),
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    try:
        req = RetrievalRequest(
            query="zz test Task In Audio",
            max_hops=2,
        )
        res = retrieve_subgraph(req, driver=driver)

        # Task and Person both link to conv_zz_test_hub_session, but since Conversation
        # is suppressed as a bridge hop, no path should connect Task <-> Person via Conversation
        for path in res.ranked_paths:
            for node in path.nodes:
                assert node.get("type") != "Conversation"

        # Conversation must still be attached in provenance
        prov_sources = {p.conversation_key for p in res.provenance}
        assert "conv_zz_test_hub_session" in prov_sources
    finally:
        driver.close()


@pytest.mark.integration
@skip_integration
def test_graphrag_privacy_filtering() -> None:
    """Verify sensitivity='private' nodes are excluded when include_private=False."""
    payload = Payload(
        source="conv_zz_test_privacy",
        entities=[
            Entity(type="Person", name="zz test Charlie"),
            Entity(
                type="Note",
                name="zz test Secret salary note",
                props={"sensitivity": "private", "description": "Confidential compensation details"},
            ),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Person", name="zz test Charlie"),
                type="MENTIONS",
                to_entity=EntityRef(type="Note", name="zz test Secret salary note"),
            )
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    try:
        # Default include_private=False: private note must not appear
        req_public = RetrievalRequest(query="zz test Charlie notes", include_private=False)
        res_public = retrieve_subgraph(req_public, driver=driver)
        node_keys_public = {n["key"] for n in res_public.nodes}
        assert "zz test secret salary note" not in node_keys_public

        # include_private=True: private note is included
        req_private = RetrievalRequest(query="zz test Charlie notes", include_private=True)
        res_private = retrieve_subgraph(req_private, driver=driver)
        node_keys_private = {n["key"] for n in res_private.nodes}
        assert "zz test secret salary note" in node_keys_private
    finally:
        driver.close()


@pytest.mark.integration
@skip_integration
def test_graphrag_vs_keyword_baseline_gain() -> None:
    """Verify compare_retrieval demonstrates multi-hop entity gain over flat keywords."""
    payload = Payload(
        source="conv_zz_test_baseline_gain",
        entities=[
            Entity(type="Task", name="zz test Audio pipeline optimization", props={"status": "blocked"}),
            Entity(type="Issue", name="zz test Cuda memory fragmentation", props={"severity": "critical"}),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Audio pipeline optimization"),
                type="BLOCKED_BY",
                to_entity=EntityRef(type="Issue", name="zz test Cuda memory fragmentation"),
            )
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    try:
        # Query only specifies "Audio pipeline optimization"
        req = RetrievalRequest(
            query="What is blocking zz test Audio pipeline optimization?",
            max_hops=2,
        )
        comparison = compare_retrieval(req, driver=driver)

        # Baseline only finds the task (which matches "audio pipeline optimization")
        # GraphRAG traverses BLOCKED_BY to also discover the issue "Cuda memory fragmentation"
        assert comparison["metrics"]["graphrag_entity_count"] >= 2
        assert comparison["metrics"]["multi_hop_gain_count"] >= 1
        gain_keys = {g["key"] for g in comparison["multi_hop_entity_gain"]}
        assert "zz test cuda memory fragmentation" in gain_keys
    finally:
        driver.close()


@pytest.mark.integration
@skip_integration
def test_pending_items_context_retrieval() -> None:
    """Verify get_pending_items_context retrieves active tasks and blockers."""
    payload = Payload(
        source="conv_zz_test_pending_items",
        entities=[
            Entity(type="Task", name="zz test Urgent security patch", props={"status": "in progress", "priority": "urgent"}),
            Entity(type="Deadline", name="zz test 2026-10-30", props={"date": "2026-10-30"}),
            Entity(type="Person", name="zz test Lead Dev"),
            Entity(type="Issue", name="zz test Upstream library break", props={"severity": "high"}),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Urgent security patch"),
                type="DUE_ON",
                to_entity=EntityRef(type="Deadline", name="zz test 2026-10-30"),
            ),
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Urgent security patch"),
                type="ASSIGNED_TO",
                to_entity=EntityRef(type="Person", name="zz test Lead Dev"),
            ),
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Urgent security patch"),
                type="BLOCKED_BY",
                to_entity=EntityRef(type="Issue", name="zz test Upstream library break"),
            ),
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    try:
        pending = get_pending_items_context(driver=driver)
        assert pending["count"] >= 1
        task_names = [t["task_name"] for t in pending["tasks"]]
        assert "zz test Urgent security patch" in task_names

        urgent_task = next(t for t in pending["tasks"] if t["task_name"] == "zz test Urgent security patch")
        assert urgent_task["priority"] == "urgent"
        assert urgent_task["assignee"] == "zz test Lead Dev"
        assert len(urgent_task["blockers"]) >= 1
        assert "Upstream library break" in urgent_task["blockers"][0]["name"]
    finally:
        driver.close()
