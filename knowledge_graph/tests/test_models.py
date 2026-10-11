"""Tests for knowledge graph data models, open fallback normalization, directions, and schema constraints."""

import json
from pathlib import Path
from typing import get_args
import pytest
from pydantic import ValidationError
from graph_schema.models import (
    ALLOWED_NODE_LABELS,
    ALLOWED_RELATIONSHIP_TYPES,
    Entity,
    EntityRef,
    NodeLabel,
    Payload,
    Relationship,
    RelationshipType,
    normalize_key,
)
from graph_schema.schema import CONSTRAINTS

# Direction test cases covering all 35 relationship types:
# (rel_type, valid_from, valid_to, invalid_from, invalid_to)
RELATIONSHIP_TEST_CASES = [
    ("MEMBER_OF", "Person", "Team", "Task", "Team"),
    ("LEADS", "Person", "Project", "Document", "Project"),
    ("REPORTS_TO", "Person", "Person", "Project", "Person"),
    ("COLLABORATES_WITH", "Person", "Person", "Task", "Person"),
    ("ATTENDED", "Person", "Meeting", "Meeting", "Person"),
    ("ABSENT_FROM", "Person", "Meeting", "Task", "Meeting"),
    ("ASSIGNED_TO", "Task", "Person", "Person", "Task"),
    ("REQUESTED_BY", "Task", "Person", "Meeting", "Person"),
    ("WORKS_ON", "Person", "Project", "Project", "Person"),
    ("PART_OF", "Task", "Project", "Person", "Project"),
    ("DEPENDS_ON", "Task", "Task", "Person", "Task"),
    ("BLOCKED_BY", "Task", "Issue", "Person", "Issue"),
    ("FOLLOW_UP_OF", "Task", "Meeting", "Person", "Meeting"),
    ("SUPPORTS", "Project", "Goal", "Goal", "Project"),
    ("DUE_ON", "Task", "Deadline", "Person", "Deadline"),
    ("SCHEDULED_ON", "Meeting", "Deadline", "Task", "Deadline"),
    ("LOCATED_AT", "Meeting", "Location", "Person", "Location"),
    ("CREATED_IN", "Decision", "Meeting", "Person", "Meeting"),
    ("DISCUSSED", "Meeting", "Topic", "Person", "Topic"),
    ("DECIDED", "Person", "Decision", "Decision", "Person"),
    ("RAISED", "Person", "Question", "Task", "Question"),
    ("PROPOSED", "Person", "Idea", "Idea", "Person"),
    ("HAS_ISSUE", "Project", "Issue", "Person", "Issue"),
    ("RESOLVES", "Decision", "Issue", "Person", "Issue"),
    ("ANSWERS", "Decision", "Question", "Person", "Question"),
    ("SUPERSEDES", "Decision", "Decision", "Person", "Decision"),
    ("AGREES_WITH", "Person", "Idea", "Task", "Idea"),
    ("DISAGREES_WITH", "Person", "Decision", "Task", "Decision"),
    ("REFERENCES", "Decision", "Document", "Person", "Document"),
    ("USES", "Project", "Tool", "Person", "Tool"),
    ("HAS_METRIC", "Project", "Metric", "Person", "Metric"),
    ("ABOUT", "Meeting", "Topic", "Person", "Topic"),
    ("PREFERS", "Person", "Preference", "Task", "Preference"),
    ("MENTIONS", "Note", "Person", "Person", "Person"),
    ("RELATED_TO", "Person", "Task", None, None),
]


def test_normalize_key():
    """Verify key normalization strips whitespace, lowercases, and collapses inner spaces."""
    assert normalize_key("  Sarah   Perera ") == "sarah perera"
    assert normalize_key("Task:  Prepare   Slides") == "task: prepare slides"
    assert normalize_key("2026-10-12") == "2026-10-12"
    assert normalize_key("   Marketing   ") == "marketing"


def test_constraints_match_node_labels():
    """Verify that generated constraints match NodeLabel dynamically without drift."""
    node_labels = list(get_args(NodeLabel))
    assert len(node_labels) == 22
    assert len(CONSTRAINTS) == 22

    constraint_names = [c[0] for c in CONSTRAINTS]
    for label in node_labels:
        expected_name = f"{label.lower()}_key"
        assert expected_name in constraint_names
        # Ensure query format references label correctly
        matching = [c[1] for c in CONSTRAINTS if c[0] == expected_name][0]
        assert f"FOR (n:{label})" in matching
        assert "REQUIRE n.key IS UNIQUE" in matching


@pytest.mark.parametrize(
    "rel_type,valid_from,valid_to,invalid_from,invalid_to",
    RELATIONSHIP_TEST_CASES,
)
def test_relationship_valid_and_invalid_directions(
    rel_type, valid_from, valid_to, invalid_from, invalid_to
):
    """Test valid and invalid directions for each relationship type."""
    # 1. Valid direction passes unchanged
    valid_data = {
        "from": {"type": valid_from, "name": "SourceEntity"},
        "type": rel_type,
        "to": {"type": valid_to, "name": "TargetEntity"},
    }
    rel = Relationship.model_validate(valid_data)
    assert rel.type == rel_type
    assert rel.props.get("label") is None

    # 2. Invalid direction falls back to RELATED_TO with props['label']
    if invalid_from is not None and invalid_to is not None:
        invalid_data = {
            "from": {"type": invalid_from, "name": "SourceEntity"},
            "type": rel_type,
            "to": {"type": invalid_to, "name": "TargetEntity"},
        }
        rel_invalid = Relationship.model_validate(invalid_data)
        assert rel_invalid.type == "RELATED_TO"
        assert rel_invalid.props.get("label") == rel_type
    elif rel_type == "RELATED_TO":
        # RELATED_TO accepts any direction, test an unknown type fallback to RELATED_TO
        unknown_data = {
            "from": {"type": "Person", "name": "SourceEntity"},
            "type": "CUSTOM_UNKNOWN_EDGE",
            "to": {"type": "Task", "name": "TargetEntity"},
        }
        rel_unknown = Relationship.model_validate(unknown_data)
        assert rel_unknown.type == "RELATED_TO"
        assert rel_unknown.props.get("label") == "CUSTOM_UNKNOWN_EDGE"


def test_unknown_entity_type_fallback():
    """Verify that an unknown entity type falls back to Concept with original_type."""
    data = {
        "type": "NovelDeviceType",
        "name": "Smart Speaker V2",
        "props": {"description": "Hardware voice peripheral"},
    }
    entity = Entity.model_validate(data)
    assert entity.type == "Concept"
    assert entity.name == "Smart Speaker V2"
    assert entity.props["original_type"] == "NovelDeviceType"
    assert entity.props["description"] == "Hardware voice peripheral"


def test_office_meeting_example_payload_passes():
    """Verify that the office meeting example with Question/Decision/Task/Issue parses cleanly."""
    example_path = (
        Path(__file__).resolve().parent.parent
        / "contracts"
        / "graph_payload.example.json"
    )
    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    payload = Payload.model_validate(data)
    assert payload.source.startswith("voice_convo")
    assert len(payload.entities) >= 10
    assert len(payload.relationships) >= 10

    types = {e.type for e in payload.entities}
    assert "Meeting" in types
    assert "Decision" in types
    assert "Question" in types
    assert "Task" in types
    assert "Issue" in types
    assert "Person" in types
    assert "Idea" in types


def test_empty_entity_name_rejected():
    """Verify that empty or whitespace-only entity names are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Entity.model_validate({"type": "Person", "name": "   ", "props": {}})
    assert "Entity name must be non-empty" in str(exc_info.value)

    with pytest.raises(ValidationError):
        EntityRef.model_validate({"type": "Person", "name": ""})


def test_nested_prop_value_rejected():
    """Verify that nested dicts or lists in props are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"description": {"nested": "value"}},
        })
    assert "Invalid property value type" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"description": ["list", "value"]},
        })
    assert "Invalid property value type" in str(exc_info.value)


def test_invalid_property_key_rejected():
    """Verify that property keys outside the allowed whitelist are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"unauthorized_key": "val"},
        })
    assert "Invalid property keys" in str(exc_info.value)


def test_populate_by_name_and_alias():
    """Verify relationship model supports both 'from' alias and 'from_entity' field name."""
    rel = Relationship(
        from_entity=EntityRef(type="Task", name="Slides"),
        type="ASSIGNED_TO",
        to_entity=EntityRef(type="Person", name="Sarah"),
    )
    dumped = rel.model_dump(by_alias=True)
    assert "from" in dumped
    assert dumped["from"]["name"] == "Slides"
