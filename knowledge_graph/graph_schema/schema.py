"""Knowledge graph schema definitions and database constraint management.

Node structure convention:
  Every node in the graph contains:
    - key: Normalized unique identifier string (via normalize_key)
    - name: Human-readable display name string
    - created_at: ISO-8601 UTC timestamp of node creation
    - updated_at: ISO-8601 UTC timestamp of last node update

Note on future conflict resolution (RP-29):
  A `Change` label (with properties: field, old, new, source, at) will be used
  later for tracking property changes and conflict history.
  Conflict resolution logic is planned for a subsequent phase and not implemented here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver

# Load environment variables from knowledge_graph/.env
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme123")


def get_driver(
    uri: str = NEO4J_URI,
    user: str = NEO4J_USER,
    password: str = NEO4J_PASSWORD,
) -> Driver:
    """Create and return a Neo4j driver instance."""
    return GraphDatabase.driver(uri, auth=(user, password))


CONSTRAINTS = [
    ("person_key", "CREATE CONSTRAINT person_key IF NOT EXISTS FOR (p:Person) REQUIRE p.key IS UNIQUE"),
    ("task_key", "CREATE CONSTRAINT task_key IF NOT EXISTS FOR (t:Task) REQUIRE t.key IS UNIQUE"),
    ("project_key", "CREATE CONSTRAINT project_key IF NOT EXISTS FOR (pr:Project) REQUIRE pr.key IS UNIQUE"),
    ("meeting_key", "CREATE CONSTRAINT meeting_key IF NOT EXISTS FOR (m:Meeting) REQUIRE m.key IS UNIQUE"),
    ("deadline_key", "CREATE CONSTRAINT deadline_key IF NOT EXISTS FOR (d:Deadline) REQUIRE d.key IS UNIQUE"),
    ("organization_key", "CREATE CONSTRAINT organization_key IF NOT EXISTS FOR (o:Organization) REQUIRE o.key IS UNIQUE"),
    ("location_key", "CREATE CONSTRAINT location_key IF NOT EXISTS FOR (l:Location) REQUIRE l.key IS UNIQUE"),
    ("event_key", "CREATE CONSTRAINT event_key IF NOT EXISTS FOR (e:Event) REQUIRE e.key IS UNIQUE"),
    ("concept_key", "CREATE CONSTRAINT concept_key IF NOT EXISTS FOR (c:Concept) REQUIRE c.key IS UNIQUE"),
    ("note_key", "CREATE CONSTRAINT note_key IF NOT EXISTS FOR (n:Note) REQUIRE n.key IS UNIQUE"),
]


def create_schema(driver: Driver = None) -> None:
    """Ensure all required uniqueness constraints exist in Neo4j."""
    close_driver = False
    if driver is None:
        driver = get_driver()
        close_driver = True

    try:
        with driver.session() as session:
            for name, query in CONSTRAINTS:
                session.run(query)
                print(f"Verified constraint: {name}")
    finally:
        if close_driver:
            driver.close()


if __name__ == "__main__":
    create_schema()
