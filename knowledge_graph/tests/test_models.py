"""Tests for knowledge graph data models, open fallback normalization, and validation."""

import pytest
from pydantic import ValidationError
from graph_schema.models import (
    Entity,
    EntityRef,
    Payload,
    Relationship,
    normalize_key,
)


def test_normalize_key():
    """Verify key normalization strips whitespace, lowercases, and collapses inner spaces."""
    assert normalize_key("  Sarah   Perera ") == "sarah perera"
    assert normalize_key("Task:  Prepare   Slides") == "task: prepare slides"
    assert normalize_key("2026-10-12") == "2026-10-12"
    assert normalize_key("   Marketing   ") == "marketing"


def test_valid_core_payload_unchanged():
    """Verify that a standard payload with core and new types passes unchanged."""
    data = {
        "source": "voice_convo_001",
        "entities": [
            {
                "type": "Person",
                "name": "Sarah",
                "props": {"description": "Lead manager"},
            },
            {
                "type": "Organization",
                "name": "Acme Corp",
                "props": {"description": "Engineering company"},
            },
            {
                "type": "Task",
                "name": "Prepare slides",
                "props": {"status": "in_progress", "priority": "high"},
            },
            {
                "type": "Project",
                "name": "Marketing",
                "props": {"status": "active"},
            },
            {
                "type": "Meeting",
                "name": "Sprint Review",
                "props": {"date": "2026-10-10"},
            },
            {
                "type": "Location",
                "name": "Room 101",
                "props": {"description": "1st Floor"},
            },
            {
                "type": "Deadline",
                "name": "2026-10-12",
                "props": {"date": "2026-10-12"},
            },
            {
                "type": "Event",
                "name": "Demo Day",
                "props": {"date": "2026-10-20"},
            },
            {
                "type": "Note",
                "name": "Action items",
                "props": {"kind": "summary"},
            },
            {
                "type": "Concept",
                "name": "Microservices",
                "props": {"kind": "architecture"},
            },
        ],
        "relationships": [
            {
                "from": {"type": "Person", "name": "Sarah"},
                "type": "MEMBER_OF",
                "to": {"type": "Organization", "name": "Acme Corp"},
            },
            {
                "from": {"type": "Task", "name": "Prepare slides"},
                "type": "ASSIGNED_TO",
                "to": {"type": "Person", "name": "Sarah"},
            },
            {
                "from": {"type": "Task", "name": "Prepare slides"},
                "type": "PART_OF",
                "to": {"type": "Project", "name": "Marketing"},
            },
            {
                "from": {"type": "Person", "name": "Sarah"},
                "type": "WORKS_ON",
                "to": {"type": "Project", "name": "Marketing"},
            },
            {
                "from": {"type": "Person", "name": "Sarah"},
                "type": "ATTENDED",
                "to": {"type": "Meeting", "name": "Sprint Review"},
            },
            {
                "from": {"type": "Meeting", "name": "Sprint Review"},
                "type": "LOCATED_AT",
                "to": {"type": "Location", "name": "Room 101"},
            },
            {
                "from": {"type": "Meeting", "name": "Sprint Review"},
                "type": "DISCUSSED",
                "to": {"type": "Task", "name": "Prepare slides"},
            },
            {
                "from": {"type": "Task", "name": "Prepare slides"},
                "type": "DUE_ON",
                "to": {"type": "Deadline", "name": "2026-10-12"},
            },
            {
                "from": {"type": "Note", "name": "Action items"},
                "type": "MENTIONS",
                "to": {"type": "Project", "name": "Marketing"},
            },
            {
                "from": {"type": "Concept", "name": "Microservices"},
                "type": "RELATED_TO",
                "to": {"type": "Project", "name": "Marketing"},
            },
        ],
    }
    payload = Payload.model_validate(data)
    assert payload.source == "voice_convo_001"
    assert len(payload.entities) == 10
    assert len(payload.relationships) == 10
    assert payload.entities[0].type == "Person"
    assert payload.relationships[0].type == "MEMBER_OF"


def test_unknown_entity_type_becomes_concept():
    """Verify that an unknown entity type is normalized to Concept with props['original_type']."""
    entity_data = {
        "type": "HardwareDevice",
        "name": "Microphone",
        "props": {"description": "USB Conference Mic"},
    }
    entity = Entity.model_validate(entity_data)
    assert entity.type == "Concept"
    assert entity.name == "Microphone"
    assert entity.props["original_type"] == "HardwareDevice"
    assert entity.props["description"] == "USB Conference Mic"


def test_wrong_direction_becomes_related_to():
    """Verify that a relationship with an invalid direction is converted to RELATED_TO with props['label']."""
    # ASSIGNED_TO is Task -> Person; Person -> Task is an invalid direction
    rel_data = {
        "from": {"type": "Person", "name": "Sarah"},
        "type": "ASSIGNED_TO",
        "to": {"type": "Task", "name": "Prepare slides"},
    }
    rel = Relationship.model_validate(rel_data)
    assert rel.type == "RELATED_TO"
    assert rel.props["label"] == "ASSIGNED_TO"
    assert rel.from_entity.name == "Sarah"
    assert rel.to_entity.name == "Prepare slides"


def test_unknown_relationship_type_becomes_related_to():
    """Verify that an unknown relationship type is normalized to RELATED_TO with props['label']."""
    rel_data = {
        "from": {"type": "Person", "name": "Sarah"},
        "type": "MANAGES",
        "to": {"type": "Person", "name": "Alex"},
    }
    rel = Relationship.model_validate(rel_data)
    assert rel.type == "RELATED_TO"
    assert rel.props["label"] == "MANAGES"


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
