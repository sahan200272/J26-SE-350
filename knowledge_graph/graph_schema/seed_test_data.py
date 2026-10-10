"""Seed and clean up sample test data for the Knowledge Graph."""

from datetime import datetime, timezone
from neo4j import Driver
from graph_schema.models import normalize_key
from graph_schema.schema import get_driver

TEST_KEYS = [
    normalize_key("Sarah"),
    normalize_key("Prepare slides"),
    normalize_key("Marketing"),
    normalize_key("2026-10-12"),
]


def seed_data(driver: Driver = None) -> None:
    """Seed sample test nodes and relationships into Neo4j using MERGE."""
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    now = datetime.now(timezone.utc).isoformat()

    query = """
    MERGE (p:Person {key: $person_key})
    ON CREATE SET p.name = $person_name, p.created_at = $now, p.updated_at = $now
    ON MATCH SET p.name = $person_name, p.updated_at = $now

    MERGE (t:Task {key: $task_key})
    ON CREATE SET t.name = $task_name, t.status = 'in_progress', t.priority = 'high', t.created_at = $now, t.updated_at = $now
    ON MATCH SET t.name = $task_name, t.status = 'in_progress', t.priority = 'high', t.updated_at = $now

    MERGE (pr:Project {key: $project_key})
    ON CREATE SET pr.name = $project_name, pr.created_at = $now, pr.updated_at = $now
    ON MATCH SET pr.name = $project_name, pr.updated_at = $now

    MERGE (d:Deadline {key: $deadline_key})
    ON CREATE SET d.name = $deadline_name, d.date = '2026-10-12', d.created_at = $now, d.updated_at = $now
    ON MATCH SET d.name = $deadline_name, d.date = '2026-10-12', d.updated_at = $now

    MERGE (t)-[:ASSIGNED_TO]->(p)
    MERGE (t)-[:PART_OF]->(pr)
    MERGE (t)-[:DUE_ON]->(d)
    """

    params = {
        "person_key": normalize_key("Sarah"),
        "person_name": "Sarah",
        "task_key": normalize_key("Prepare slides"),
        "task_name": "Prepare slides",
        "project_key": normalize_key("Marketing"),
        "project_name": "Marketing",
        "deadline_key": normalize_key("2026-10-12"),
        "deadline_name": "2026-10-12",
        "now": now,
    }

    try:
        with driver.session() as session:
            session.run(query, params)
            print("Successfully seeded test data (Sarah, Prepare slides, Marketing, 2026-10-12).")
    finally:
        if close_driver:
            driver.close()


def clear_test_data(driver: Driver = None) -> None:
    """Remove the sample test data from Neo4j."""
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    query = """
    MATCH (n)
    WHERE n.key IN $test_keys
    DETACH DELETE n
    """

    try:
        with driver.session() as session:
            session.run(query, {"test_keys": TEST_KEYS})
            print("Successfully cleared test data.")
    finally:
        if close_driver:
            driver.close()


if __name__ == "__main__":
    seed_data()
