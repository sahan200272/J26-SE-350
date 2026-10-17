"""Integration tests for Neo4j knowledge graph ingestion.

Runs only when KG_INTEGRATION=1 and Neo4j is reachable.
CRITICAL: These tests MUST NOT wipe the running database. All test entities
use keys/names prefixed with 'zz test' or 'conv_zz_test'.
"""

import os
from typing import Generator
import pytest

from graph_schema.ingest import IngestResult, ingest_payload
from graph_schema.models import Entity, EntityRef, Payload, Relationship
from graph_schema.schema import get_driver


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
def clean_test_nodes() -> Generator[None, None, None]:
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
def test_idempotent_ingestion() -> None:
    """Verify that ingesting the same payload twice leaves identical counts."""
    payload = Payload(
        source="conv_zz_test_idempotent",
        entities=[
            Entity(type="Person", name="zz test Alice"),
            Entity(type="Task", name="zz test Plan sprint"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Plan sprint"),
                type="ASSIGNED_TO",
                to_entity=EntityRef(type="Person", name="zz test Alice"),
            )
        ],
    )

    # First ingestion
    res1: IngestResult = ingest_payload(payload, dry_run=False)
    assert res1.nodes_created >= 2
    assert res1.edges_created >= 2

    driver = get_driver()
    with driver.session() as session:
        r_nodes = session.run(
            "MATCH (n) WHERE n.key STARTS WITH 'zz test' "
            "OR (n:Conversation AND n.key STARTS WITH 'conv_zz_test') "
            "RETURN count(n) AS cnt"
        )
        count_nodes_1 = r_nodes.single()["cnt"]

        r_edges = session.run(
            "MATCH (a)-[r]-(b) WHERE a.key STARTS WITH 'zz test' "
            "OR (a:Conversation AND a.key STARTS WITH 'conv_zz_test') "
            "RETURN count(r) AS cnt"
        )
        count_edges_1 = r_edges.single()["cnt"]

    # Second ingestion with exact same payload
    res2: IngestResult = ingest_payload(payload, dry_run=False)
    assert res2.nodes_created == 0
    assert res2.edges_created == 0
    assert res2.nodes_merged >= 2
    assert res2.edges_merged >= 2

    with driver.session() as session:
        r_nodes = session.run(
            "MATCH (n) WHERE n.key STARTS WITH 'zz test' "
            "OR (n:Conversation AND n.key STARTS WITH 'conv_zz_test') "
            "RETURN count(n) AS cnt"
        )
        count_nodes_2 = r_nodes.single()["cnt"]

        r_edges = session.run(
            "MATCH (a)-[r]-(b) WHERE a.key STARTS WITH 'zz test' "
            "OR (a:Conversation AND a.key STARTS WITH 'conv_zz_test') "
            "RETURN count(r) AS cnt"
        )
        count_edges_2 = r_edges.single()["cnt"]

    driver.close()

    assert count_nodes_1 == count_nodes_2
    assert count_edges_1 == count_edges_2


@pytest.mark.integration
@skip_integration
def test_dry_run_writes_nothing() -> None:
    """Verify that dry_run=True returns simulation result without persisting data."""
    payload = Payload(
        source="conv_zz_test_dryrun",
        entities=[
            Entity(type="Person", name="zz test Bob"),
            Entity(type="Task", name="zz test Build feature"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Build feature"),
                type="ASSIGNED_TO",
                to_entity=EntityRef(type="Person", name="zz test Bob"),
            )
        ],
    )

    res: IngestResult = ingest_payload(payload, dry_run=True)
    assert res.nodes_created >= 2
    assert res.edges_created >= 2

    # Verify database has zero nodes for this test
    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (n) WHERE n.key STARTS WITH 'zz test' "
            "OR (n:Conversation AND n.key STARTS WITH 'conv_zz_test') "
            "RETURN count(n) AS cnt"
        )
        assert r.single()["cnt"] == 0
    driver.close()


@pytest.mark.integration
@skip_integration
def test_fuzzy_alias_merge() -> None:
    """Verify that a typo duplicate with ratio >= 90 is merged and alias is added."""
    payload1 = Payload(
        source="conv_zz_test_fuzzy_1",
        entities=[
            Entity(type="Task", name="zz test Deploy notification service"),
        ],
    )
    ingest_payload(payload1, dry_run=False)

    # Ingest typo variant
    payload2 = Payload(
        source="conv_zz_test_fuzzy_2",
        entities=[
            Entity(type="Task", name="zz test Deploy notification serivce"),
        ],
    )
    res2 = ingest_payload(payload2, dry_run=False)
    assert res2.nodes_merged >= 1
    assert res2.aliases_added == 1

    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (t:Task {key: 'zz test deploy notification service'}) "
            "RETURN t.name AS name, t.aliases AS aliases"
        )
        rec = r.single()
        assert rec is not None
        assert "zz test Deploy notification serivce" in rec["aliases"]

        # Ensure only one task node exists
        r_all = session.run(
            "MATCH (t:Task) WHERE t.key STARTS WITH 'zz test deploy notification' RETURN count(t) AS cnt"
        )
        assert r_all.single()["cnt"] == 1
    driver.close()


@pytest.mark.integration
@skip_integration
def test_provenance_edges_exist_and_no_self_link() -> None:
    """Verify CREATED_IN for work items, MENTIONS for others, and no self-link."""
    payload = Payload(
        source="conv_zz_test_prov",
        entities=[
            Entity(type="Task", name="zz test Task item"),
            Entity(type="Person", name="zz test Person item"),
            Entity(type="Decision", name="zz test Decision item"),
            Entity(type="Issue", name="zz test Issue item"),
        ],
    )
    res = ingest_payload(payload, dry_run=False)
    assert res.nodes_created >= 4

    driver = get_driver()
    with driver.session() as session:
        # Conversation node exists
        r_conv = session.run(
            "MATCH (c:Conversation {key: 'conv_zz_test_prov'}) RETURN c"
        )
        assert r_conv.single() is not None

        # CREATED_IN edges for Task, Decision, Issue
        r_created = session.run(
            "MATCH (e)-[:CREATED_IN]->(c:Conversation {key: 'conv_zz_test_prov'}) "
            "RETURN e.key AS k"
        )
        created_keys = {rec["k"] for rec in r_created}
        assert "zz test task item" in created_keys
        assert "zz test decision item" in created_keys
        assert "zz test issue item" in created_keys

        # MENTIONS edge for Person
        r_mentions = session.run(
            "MATCH (c:Conversation {key: 'conv_zz_test_prov'})-[:MENTIONS]->(e:Person) "
            "RETURN e.key AS k"
        )
        mentioned_keys = {rec["k"] for rec in r_mentions}
        assert "zz test person item" in mentioned_keys

        # Ensure Conversation never links to itself
        r_self = session.run(
            "MATCH (c:Conversation {key: 'conv_zz_test_prov'})-[r]-(c) RETURN count(r) AS cnt"
        )
        assert r_self.single()["cnt"] == 0
    driver.close()


@pytest.mark.integration
@skip_integration
def test_symmetric_friend_of_creates_one_edge() -> None:
    """Verify FRIEND_OF Ruwan->Kamal and Kamal->Ruwan produce exactly 1 edge."""
    payload1 = Payload(
        source="conv_zz_test_sym_1",
        entities=[
            Entity(type="Person", name="zz test Ruwan"),
            Entity(type="Person", name="zz test Kamal"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Person", name="zz test Ruwan"),
                type="FRIEND_OF",
                to_entity=EntityRef(type="Person", name="zz test Kamal"),
            )
        ],
    )
    ingest_payload(payload1, dry_run=False)

    payload2 = Payload(
        source="conv_zz_test_sym_2",
        entities=[
            Entity(type="Person", name="zz test Kamal"),
            Entity(type="Person", name="zz test Ruwan"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Person", name="zz test Kamal"),
                type="FRIEND_OF",
                to_entity=EntityRef(type="Person", name="zz test Ruwan"),
            )
        ],
    )
    res2 = ingest_payload(payload2, dry_run=False)
    assert res2.edges_merged >= 1

    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (a:Person)-[r:FRIEND_OF]-(b:Person) "
            "WHERE a.key STARTS WITH 'zz test' AND b.key STARTS WITH 'zz test' "
            "RETURN count(r) AS cnt"
        )
        # Undirected match counts each edge twice (from each end) or 1 edge if directed
        r_dir = session.run(
            "MATCH (a:Person)-[r:FRIEND_OF]->(b:Person) "
            "WHERE a.key STARTS WITH 'zz test' AND b.key STARTS WITH 'zz test' "
            "RETURN count(r) AS cnt"
        )
        assert r_dir.single()["cnt"] == 1
    driver.close()


@pytest.mark.integration
@skip_integration
def test_single_valued_due_on_replacement() -> None:
    """Verify that updating DUE_ON deletes the old edge and creates the new one."""
    payload1 = Payload(
        source="conv_zz_test_sv_1",
        entities=[
            Entity(type="Task", name="zz test Fix security issue"),
            Entity(type="Deadline", name="zz test 2026-10-20"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Fix security issue"),
                type="DUE_ON",
                to_entity=EntityRef(type="Deadline", name="zz test 2026-10-20"),
            )
        ],
    )
    ingest_payload(payload1, dry_run=False)

    # Ingest new deadline for the same task
    payload2 = Payload(
        source="conv_zz_test_sv_2",
        entities=[
            Entity(type="Task", name="zz test Fix security issue"),
            Entity(type="Deadline", name="zz test 2026-10-25"),
        ],
        relationships=[
            Relationship(
                from_entity=EntityRef(type="Task", name="zz test Fix security issue"),
                type="DUE_ON",
                to_entity=EntityRef(type="Deadline", name="zz test 2026-10-25"),
            )
        ],
    )
    res2 = ingest_payload(payload2, dry_run=False)
    assert res2.edges_replaced == 1
    assert any("DUE_ON" in w for w in res2.warnings)

    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (t:Task {key: 'zz test fix security issue'})-[r:DUE_ON]->(d) "
            "RETURN d.name AS dname"
        )
        records = list(r)
        assert len(records) == 1
        assert records[0]["dname"] == "zz test 2026-10-25"
    driver.close()


@pytest.mark.integration
@skip_integration
def test_unknown_type_falls_back_to_concept() -> None:
    """Verify that an unknown entity type falls back to Concept in Neo4j."""
    payload = Payload(
        source="conv_zz_test_unknown",
        entities=[
            Entity(type="Hobby", name="zz test Gardening"),  # type: ignore[arg-type]
        ],
    )
    ingest_payload(payload, dry_run=False)

    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (n:Concept {key: 'zz test gardening'}) "
            "RETURN n.name AS name, n.original_type AS otype"
        )
        rec = r.single()
        assert rec is not None
        assert rec["name"] == "zz test Gardening"
        assert rec["otype"] == "Hobby"
    driver.close()


@pytest.mark.integration
@skip_integration
def test_retract_operation_warning_and_no_deletion() -> None:
    """Verify that op='retract' logs warning, records in warnings, and deletes nothing."""
    payload1 = Payload(
        source="conv_zz_test_retract_1",
        entities=[
            Entity(type="Task", name="zz test Retract target task"),
        ],
    )
    ingest_payload(payload1, dry_run=False)

    # Attempt retract
    payload2 = Payload(
        source="conv_zz_test_retract_2",
        entities=[
            Entity(type="Task", name="zz test Retract target task", op="retract"),
        ],
    )
    res2 = ingest_payload(payload2, dry_run=False)
    assert any("retract" in w.lower() for w in res2.warnings)

    driver = get_driver()
    with driver.session() as session:
        r = session.run(
            "MATCH (t:Task {key: 'zz test retract target task'}) RETURN count(t) AS cnt"
        )
        assert r.single()["cnt"] == 1
    driver.close()
