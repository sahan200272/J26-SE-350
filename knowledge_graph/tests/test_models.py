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

# Direction test cases covering all 45 relationship types:
# (rel_type, valid_from, valid_to, invalid_from, invalid_to)
RELATIONSHIP_TEST_CASES = [
    # Layer A (35)
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
    # Layer B (10 new types)
    ("FAMILY_OF", "Person", "Person", "Task", "Person"),
    ("PARTNER_OF", "Person", "Person", "Meeting", "Person"),
    ("FRIEND_OF", "Person", "Person", "Project", "Person"),
    ("WORKS_AT", "Person", "Organization", "Task", "Organization"),
    ("LIVES_IN", "Person", "Location", "Organization", "Location"),
    ("LIKES", "Person", "Item", "Task", "Item"),
    ("DISLIKES", "Person", "Topic", "Project", "Topic"),
    ("ALIAS_OF", "Person", "Person", "Person", "Organization"),
    ("OWNS", "Person", "Item", "Location", "Item"),
    ("PLANS", "Person", "Event", "Task", "Event"),
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
    assert len(node_labels) == 23
    assert len(CONSTRAINTS) == 23

    constraint_names = [c[0] for c in CONSTRAINTS]
    for label in node_labels:
        expected_name = f"{label.lower()}_key"
        assert expected_name in constraint_names
        matching = [c[1] for c in CONSTRAINTS if c[0] == expected_name][0]
        assert f"FOR (n:{label})" in matching
        assert "REQUIRE n.key IS UNIQUE" in matching

    assert "item_key" in constraint_names


@pytest.mark.parametrize(
    "rel_type,valid_from,valid_to,invalid_from,invalid_to",
    RELATIONSHIP_TEST_CASES,
)
def test_relationship_valid_and_invalid_directions(
    rel_type, valid_from, valid_to, invalid_from, invalid_to
):
    """Test valid and invalid directions for each of the 45 relationship types."""
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
        unknown_data = {
            "from": {"type": "Person", "name": "SourceEntity"},
            "type": "CUSTOM_UNKNOWN_EDGE",
            "to": {"type": "Task", "name": "TargetEntity"},
        }
        rel_unknown = Relationship.model_validate(unknown_data)
        assert rel_unknown.type == "RELATED_TO"
        assert rel_unknown.props.get("label") == "CUSTOM_UNKNOWN_EDGE"


def test_attended_and_absent_from_with_event():
    """Verify ATTENDED and ABSENT_FROM accept Person -> Event."""
    att = Relationship.model_validate({
        "from": {"type": "Person", "name": "Sarah"},
        "type": "ATTENDED",
        "to": {"type": "Event", "name": "Company Gala"},
    })
    assert att.type == "ATTENDED"

    absent = Relationship.model_validate({
        "from": {"type": "Person", "name": "David"},
        "type": "ABSENT_FROM",
        "to": {"type": "Event", "name": "Company Gala"},
    })
    assert absent.type == "ABSENT_FROM"


def test_alias_of_same_and_different_labels():
    """Verify ALIAS_OF with same label passes; different labels fall back to RELATED_TO."""
    # Same label (Person -> Person)
    rel_same = Relationship.model_validate({
        "from": {"type": "Person", "name": "Sarah"},
        "type": "ALIAS_OF",
        "to": {"type": "Person", "name": "Sarah Perera"},
    })
    assert rel_same.type == "ALIAS_OF"

    # Same label (Item -> Item)
    rel_item = Relationship.model_validate({
        "from": {"type": "Item", "name": "MacBook"},
        "type": "ALIAS_OF",
        "to": {"type": "Item", "name": "Apple MacBook Pro 16"},
    })
    assert rel_item.type == "ALIAS_OF"

    # Different label (Person -> Organization)
    rel_diff = Relationship.model_validate({
        "from": {"type": "Person", "name": "Sarah"},
        "type": "ALIAS_OF",
        "to": {"type": "Organization", "name": "Acme"},
    })
    assert rel_diff.type == "RELATED_TO"
    assert rel_diff.props.get("label") == "ALIAS_OF"


def test_aliases_property_list_validation():
    """Verify aliases accepts list of non-empty strings, rejects empty strings or lists in other props."""
    # Valid aliases list
    e_valid = Entity.model_validate({
        "type": "Person",
        "name": "Sarah",
        "props": {"aliases": ["Sarah P", "Saza"]},
    })
    assert e_valid.props["aliases"] == ["Sarah P", "Saza"]

    # Empty string in aliases list rejected
    with pytest.raises(ValidationError) as exc1:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"aliases": ["Sarah P", "   "]},
        })
    assert "Invalid alias" in str(exc1.value)

    # List in other props rejected
    with pytest.raises(ValidationError) as exc2:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"description": ["A description in a list"]},
        })
    assert "Invalid property value type for 'description'" in str(exc2.value)


def test_sensitivity_and_confidence_validation():
    """Verify sensitivity must be normal/private and confidence between 0 and 1."""
    # Sensitivity normal and private pass
    e1 = Entity.model_validate({
        "type": "Person",
        "name": "Sarah",
        "props": {"sensitivity": "private", "confidence": 0.5},
    })
    assert e1.props["sensitivity"] == "private"
    assert e1.props["confidence"] == 0.5

    e2 = Entity.model_validate({
        "type": "Person",
        "name": "Sarah",
        "props": {"sensitivity": "normal", "confidence": 1.0},
    })
    assert e2.props["sensitivity"] == "normal"

    # Invalid sensitivity rejected
    with pytest.raises(ValidationError) as exc_sens:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"sensitivity": "secret"},
        })
    assert "Invalid sensitivity 'secret'" in str(exc_sens.value)

    # Invalid confidence rejected (> 1.0)
    with pytest.raises(ValidationError) as exc_conf:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"confidence": 1.5},
        })
    assert "Invalid confidence '1.5'" in str(exc_conf.value)

    # Invalid confidence rejected (< 0.0)
    with pytest.raises(ValidationError):
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"confidence": -0.1},
        })


def test_op_field_lifecycle_signals():
    """Verify op defaults to 'add', supports 'update'/'retract', and rejects unknown op."""
    e_default = Entity.model_validate({"type": "Person", "name": "Sarah"})
    assert e_default.op == "add"

    e_update = Entity.model_validate({"type": "Task", "name": "Sync", "op": "update"})
    assert e_update.op == "update"

    e_retract = Entity.model_validate({"type": "Meeting", "name": "Catchup", "op": "retract"})
    assert e_retract.op == "retract"

    rel = Relationship.model_validate({
        "from": {"type": "Person", "name": "Sarah"},
        "type": "WORKS_AT",
        "to": {"type": "Organization", "name": "Acme"},
        "op": "update",
    })
    assert rel.op == "update"

    with pytest.raises(ValidationError):
        Entity.model_validate({"type": "Person", "name": "Sarah", "op": "delete"})


def test_item_label_accepted():
    """Verify Item label parses as valid NodeLabel."""
    item = Entity.model_validate({
        "type": "Item",
        "name": "Sony Headphones",
        "props": {"kind": "electronics"},
    })
    assert item.type == "Item"
    assert item.name == "Sony Headphones"


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


def test_personal_example_payload_passes():
    """Verify that the personal everyday conversation payload parses cleanly."""
    example_path = (
        Path(__file__).resolve().parent.parent
        / "contracts"
        / "graph_payload.personal.example.json"
    )
    with open(example_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    payload = Payload.model_validate(data)
    assert payload.source.startswith("voice_convo")
    assert payload.timestamp == "2026-10-11T19:00:00Z"
    assert len(payload.entities) == 9
    assert len(payload.relationships) == 9

    types = {e.type for e in payload.entities}
    assert "Person" in types
    assert "Organization" in types
    assert "Location" in types
    assert "Item" in types
    assert "Event" in types

    rel_types = {r.type for r in payload.relationships}
    assert "FAMILY_OF" in rel_types
    assert "FRIEND_OF" in rel_types
    assert "WORKS_AT" in rel_types
    assert "LIVES_IN" in rel_types
    assert "LIKES" in rel_types
    assert "OWNS" in rel_types
    assert "PLANS" in rel_types
    assert "ALIAS_OF" in rel_types

    ops = {r.op for r in payload.relationships}
    assert "add" in ops
    assert "update" in ops
    assert "retract" in ops


def test_empty_entity_name_rejected():
    """Verify that empty or whitespace-only entity names are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Entity.model_validate({"type": "Person", "name": "   ", "props": {}})
    assert "Entity name must be non-empty" in str(exc_info.value)

    with pytest.raises(ValidationError):
        EntityRef.model_validate({"type": "Person", "name": ""})


def test_nested_prop_value_rejected():
    """Verify that nested dicts in props are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Entity.model_validate({
            "type": "Person",
            "name": "Sarah",
            "props": {"description": {"nested": "value"}},
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
