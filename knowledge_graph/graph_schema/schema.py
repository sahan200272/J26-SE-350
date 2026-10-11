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
from typing import List, Tuple, get_args
from dotenv import load_dotenv
from neo4j import GraphDatabase, Driver
from graph_schema.models import NodeLabel

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


# Generate constraints dynamically from NodeLabel to prevent schema drift
CONSTRAINTS: List[Tuple[str, str]] = [
    (
        f"{label.lower()}_key",
        f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.key IS UNIQUE",
    )
    for label in get_args(NodeLabel)
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
