"""Tests validating all sample payload fixtures against Payload model and JSON schema."""

import json
from pathlib import Path
from typing import Any, Dict, List
import pytest

from graph_schema.adapters import triples_to_payload
from graph_schema.models import Payload

try:
    import jsonschema

    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

PAYLOADS_DIR = Path(__file__).resolve().parent.parent / "sample_data" / "payloads"
SCHEMA_FILE = Path(__file__).resolve().parent.parent / "contracts" / "graph_payload.schema.json"

PAYLOAD_FILES = sorted(
    [p for p in PAYLOADS_DIR.glob("*.json") if p.name != "triples_example.json"],
    key=lambda p: p.name,
)


@pytest.fixture(scope="session")
def json_schema() -> Dict[str, Any]:
    """Load the JSON schema contract."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("file_path", PAYLOAD_FILES, ids=lambda p: p.name)
def test_payload_fixture_validates_pydantic(file_path: Path) -> None:
    """Verify that every fixture parses and validates against the Pydantic Payload model."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    payload = Payload.model_validate(data)
    assert isinstance(payload, Payload)
    assert payload.source
    assert len(payload.entities) > 0


@pytest.mark.parametrize("file_path", PAYLOAD_FILES, ids=lambda p: p.name)
def test_payload_fixture_validates_jsonschema(
    file_path: Path,
    json_schema: Dict[str, Any],
) -> None:
    """Verify that every fixture conforms to the contracts/graph_payload.schema.json."""
    if not HAS_JSONSCHEMA:
        pytest.skip("jsonschema package is not installed")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validates without raising jsonschema.ValidationError
    jsonschema.validate(instance=data, schema=json_schema)


def test_triples_example_fixture_via_adapter() -> None:
    """Verify that triples_example.json processes into a valid Payload via the adapter."""
    triples_file = PAYLOADS_DIR / "triples_example.json"
    assert triples_file.exists(), "triples_example.json must exist in sample_data/payloads"

    with open(triples_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "triples" in data
    assert "source" in data

    payload = triples_to_payload(
        triples=data["triples"],
        source=data["source"],
        timestamp=data.get("timestamp"),
    )
    assert isinstance(payload, Payload)
    assert payload.source == data["source"]
    assert len(payload.entities) > 0
    assert len(payload.relationships) > 0
