"""Tests for knowledge graph data models, open fallback normalization, directions, and schema constraints."""

import json
from pathlib import Path
from typing import get_args
import pytest
from pydantic import ValidationError
from graph_schema.models import (
    ALLOWED_NODE_LABELS,
    ALLOWED_PRIORITIES,
    ALLOWED_RELATIONSHIP_TYPES,
    ALLOWED_SEVERITIES,
    ALLOWED_STATUSES,
    PRIORITY_SYNONYMS,
    SEVERITY_SYNONYMS,
    SINGLE_VALUED_RELATIONSHIPS,
    STATUS_SYNONYMS,
    SYMMETRIC_RELATIONSHIPS,
    Entity,
    EntityRef,
    NodeLabel,
    Payload,
    Relationship,
    RelationshipType,
    canonical_pair,
    normalize_key,
)
from graph_schema.schema import CONSTRAINTS, INDEXES

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


@pytest.mark.parametrize(
    "raw_val,expected",
    [
        ("critical", "urgent"),
        ("asap", "urgent"),
        ("immediately", "urgent"),
        ("important", "high"),
        ("normal", "medium"),
        ("ok", "medium"),
        ("moderate", "medium"),
        ("minor", "low"),
        ("whenever", "low"),
        ("optional", "low"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("urgent", "urgent"),
    ],
)
def test_priority_synonyms_mapping(raw_val, expected):
    """Verify all priority synonyms map to their canonical target values."""
    entity = Entity.model_validate({
        "type": "Task",
        "name": "Test Priority",
        "props": {"priority": raw_val},
    })
    assert entity.props["priority"] == expected

    rel = Relationship.model_validate({
        "from": {"type": "Task", "name": "TaskA"},
        "type": "ASSIGNED_TO",
        "to": {"type": "Person", "name": "Sarah"},
        "props": {"priority": raw_val},
    })
    assert rel.props["priority"] == expected


@pytest.mark.parametrize(
    "raw_val,expected",
    [
        ("blocker", "critical"),
        ("major", "high"),
        ("minor", "low"),
        ("normal", "medium"),
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("critical", "critical"),
    ],
)
def test_severity_synonyms_mapping(raw_val, expected):
    """Verify all severity synonyms map to their canonical target values."""
    entity = Entity.model_validate({
        "type": "Issue",
        "name": "Test Severity",
        "props": {"severity": raw_val},
    })
    assert entity.props["severity"] == expected

    rel = Relationship.model_validate({
        "from": {"type": "Task", "name": "TaskA"},
        "type": "BLOCKED_BY",
        "to": {"type": "Issue", "name": "IssueB"},
        "props": {"severity": raw_val},
    })
    assert rel.props["severity"] == expected


@pytest.mark.parametrize(
    "raw_val,expected",
    [
        ("completed", "done"),
        ("complete", "done"),
        ("finished", "done"),
        ("in-progress", "in progress"),
        ("in_progress", "in progress"),
        ("ongoing", "in progress"),
        ("started", "in progress"),
        ("wip", "in progress"),
        ("canceled", "cancelled"),
        ("dropped", "cancelled"),
        ("called off", "cancelled"),
        ("pending", "open"),
        ("todo", "open"),
        ("to do", "open"),
        ("new", "open"),
        ("waiting", "blocked"),
        ("stuck", "blocked"),
        ("open", "open"),
        ("in progress", "in progress"),
        ("blocked", "blocked"),
        ("done", "done"),
        ("cancelled", "cancelled"),
        ("planned", "planned"),
        ("active", "active"),
        ("agreed", "agreed"),
        ("superseded", "superseded"),
        ("answered", "answered"),
    ],
)
def test_status_synonyms_mapping(raw_val, expected):
    """Verify all status synonyms map to their canonical target values."""
    entity = Entity.model_validate({
        "type": "Task",
        "name": "Test Status",
        "props": {"status": raw_val},
    })
    assert entity.props["status"] == expected

    rel = Relationship.model_validate({
        "from": {"type": "Task", "name": "TaskA"},
        "type": "ASSIGNED_TO",
        "to": {"type": "Person", "name": "Sarah"},
        "props": {"status": raw_val},
    })
    assert rel.props["status"] == expected


def test_prop_synonyms_case_insensitivity_and_whitespace():
    """Verify case-insensitivity and surrounding whitespace normalization for priority, severity, and status."""
    e = Entity.model_validate({
        "type": "Task",
        "name": "Test Case Insensitivity",
        "props": {
            "priority": "  CRITICAL  ",
            "severity": "Blocker",
            "status": "In-Progress",
        },
    })
    assert e.props["priority"] == "urgent"
    assert e.props["severity"] == "critical"
    assert e.props["status"] == "in progress"

    e2 = Entity.model_validate({
        "type": "Task",
        "name": "Test More Casing",
        "props": {
            "priority": "IMPORTANT",
            "severity": "MAJOR",
            "status": "TO DO",
        },
    })
    assert e2.props["priority"] == "high"
    assert e2.props["severity"] == "high"
    assert e2.props["status"] == "open"


def test_unknown_prop_value_dropped_with_warning(caplog):
    """Verify unknown priority, severity, or status values are dropped with a warning, keeping the payload valid."""
    import logging

    with caplog.at_level(logging.WARNING):
        # 1. Entity with unknown values
        entity = Entity.model_validate({
            "type": "Task",
            "name": "Deploy Service",
            "props": {
                "priority": "unrecognized_priority",
                "severity": "extreme_severity",
                "status": "in_limbo",
                "title": "Keep Valid Title",
            },
        })
        # Unknown values should be dropped
        assert "priority" not in entity.props
        assert "severity" not in entity.props
        assert "status" not in entity.props
        # Valid property retained
        assert entity.props["title"] == "Keep Valid Title"

        # 2. Non-string unknown values dropped without raising exception
        entity_non_str = Entity.model_validate({
            "type": "Task",
            "name": "Non String Prop",
            "props": {
                "priority": 9999,
                "status": True,
            },
        })
        assert "priority" not in entity_non_str.props
        assert "status" not in entity_non_str.props

        # 3. Relationship with unknown values dropped
        rel = Relationship.model_validate({
            "from": {"type": "Task", "name": "TaskA"},
            "type": "ASSIGNED_TO",
            "to": {"type": "Person", "name": "Sarah"},
            "props": {
                "priority": "bad_priority",
                "status": "bad_status",
            },
        })
        assert "priority" not in rel.props
        assert "status" not in rel.props

        # 4. Full payload containing unknown values stays valid
        payload = Payload.model_validate({
            "source": "test_voice_session",
            "entities": [
                {
                    "type": "Task",
                    "name": "Task in Payload",
                    "props": {"priority": "invalid_val", "status": "wip"},
                }
            ],
            "relationships": [
                {
                    "from": {"type": "Task", "name": "Task in Payload"},
                    "type": "ASSIGNED_TO",
                    "to": {"type": "Person", "name": "Sarah"},
                    "props": {"severity": "unknown_sev"},
                }
            ],
        })
        assert len(payload.entities) == 1
        assert "priority" not in payload.entities[0].props
        assert payload.entities[0].props["status"] == "in progress"
        assert len(payload.relationships) == 1
        assert "severity" not in payload.relationships[0].props

    # Verify warnings were recorded in log
    assert any("Unknown priority" in record.message for record in caplog.records)
    assert any("Unknown severity" in record.message for record in caplog.records)
    assert any("Unknown status" in record.message for record in caplog.records)


def test_canonical_pair():
    """Verify canonical_pair sorts keys for symmetric relationships and leaves non-symmetric types unchanged."""
    assert SINGLE_VALUED_RELATIONSHIPS == {"DUE_ON", "SCHEDULED_ON", "LIVES_IN"}
    assert SYMMETRIC_RELATIONSHIPS == {"FRIEND_OF", "PARTNER_OF", "COLLABORATES_WITH"}

    # Symmetric relationships return keys in sorted order
    assert canonical_pair("FRIEND_OF", "bob", "alice") == ("alice", "bob")
    assert canonical_pair("FRIEND_OF", "alice", "bob") == ("alice", "bob")
    assert canonical_pair("PARTNER_OF", "zara", "alex") == ("alex", "zara")
    assert canonical_pair("COLLABORATES_WITH", "sarah", "david") == ("david", "sarah")

    # Non-symmetric relationships return unchanged keys
    assert canonical_pair("ASSIGNED_TO", "task_key", "person_key") == ("task_key", "person_key")
    assert canonical_pair("ASSIGNED_TO", "person_key", "task_key") == ("person_key", "task_key")
    assert canonical_pair("DUE_ON", "task_1", "deadline_1") == ("task_1", "deadline_1")
    assert canonical_pair("REPORTS_TO", "david", "sarah") == ("david", "sarah")
    assert canonical_pair("LIVES_IN", "sarah", "brooklyn") == ("sarah", "brooklyn")


def test_schema_version_default_and_mismatch_warning(caplog):
    """Verify schema_version defaults to 1.0, and logs warning on major version mismatch."""
    import logging

    # 1. Default schema_version when omitted
    p_default = Payload.model_validate({"source": "voice_1"})
    assert p_default.schema_version == "1.0"

    # 2. Matching schema_version 1.0 or minor bump 1.1 produces no warning
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        p_10 = Payload.model_validate({"source": "voice_1", "schema_version": "1.0"})
        assert p_10.schema_version == "1.0"
        p_11 = Payload.model_validate({"source": "voice_1", "schema_version": "1.1"})
        assert p_11.schema_version == "1.1"
        assert not any("schema_version" in r.message for r in caplog.records)

    # 3. Differing major version logs a warning but payload is kept
    with caplog.at_level(logging.WARNING):
        caplog.clear()
        p_mismatch = Payload.model_validate({"source": "voice_1", "schema_version": "2.0"})
        assert p_mismatch.schema_version == "2.0"
        assert any("schema_version '2.0' has major version '2'" in r.message for r in caplog.records)


def test_deadline_name_warning(caplog):
    """Verify Deadline entities whose name is not YYYY-MM-DD log a warning but are kept."""
    import logging

    with caplog.at_level(logging.WARNING):
        caplog.clear()
        # Valid ISO date produces no warning
        d_valid = Entity.model_validate({"type": "Deadline", "name": "2026-10-18"})
        assert d_valid.type == "Deadline"
        assert d_valid.name == "2026-10-18"
        assert not any("Deadline" in r.message for r in caplog.records)

        # Non-ISO date name logs a warning but entity is kept
        d_invalid = Entity.model_validate({"type": "Deadline", "name": "End of Sprint 14"})
        assert d_invalid.type == "Deadline"
        assert d_invalid.name == "End of Sprint 14"
        assert any(
            "Deadline entity name 'End of Sprint 14' is not an ISO date" in r.message
            for r in caplog.records
        )

        caplog.clear()
        # Invalid date like 2026-02-31 logs a warning
        d_bad_date = Entity.model_validate({"type": "Deadline", "name": "2026-02-31"})
        assert d_bad_date.name == "2026-02-31"
        assert any("Deadline entity name '2026-02-31' is not an ISO date" in r.message for r in caplog.records)

        caplog.clear()
        # Non-Deadline entity does not trigger deadline warning
        p = Entity.model_validate({"type": "Person", "name": "End of Sprint 14"})
        assert not any("Deadline" in r.message for r in caplog.records)


def test_schema_range_indexes():
    """Verify range indexes on Task(priority), Task(status), Issue(severity) exist in schema."""
    assert len(INDEXES) == 3
    index_names = [idx[0] for idx in INDEXES]
    assert "task_priority" in index_names
    assert "task_status" in index_names
    assert "issue_severity" in index_names

    queries = {name: q for name, q in INDEXES}
    assert "FOR (n:Task) ON (n.priority)" in queries["task_priority"]
    assert "FOR (n:Task) ON (n.status)" in queries["task_status"]
    assert "FOR (n:Issue) ON (n.severity)" in queries["issue_severity"]
    for q in queries.values():
        assert "CREATE INDEX" in q
        assert "IF NOT EXISTS" in q
