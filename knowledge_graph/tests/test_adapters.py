"""Unit tests for triple-to-payload adapters (no database required)."""

import logging
from typing import List
import pytest

from graph_schema.adapters import get_inferred_labels, triples_to_payload
from graph_schema.models import Payload


def test_inferred_labels_unambiguous() -> None:
    """Verify that unambiguous predicates return exact (from_label, to_label)."""
    assert get_inferred_labels("ASSIGNED_TO") == ("Task", "Person")
    assert get_inferred_labels("REQUESTED_BY") == ("Task", "Person")
    assert get_inferred_labels("WORKS_ON") == ("Person", "Project")
    assert get_inferred_labels("DECIDED") == ("Person", "Decision")
    assert get_inferred_labels("PROPOSED") == ("Person", "Idea")
    assert get_inferred_labels("SUPERSEDES") == ("Decision", "Decision")
    assert get_inferred_labels("FAMILY_OF") == ("Person", "Person")
    assert get_inferred_labels("PARTNER_OF") == ("Person", "Person")
    assert get_inferred_labels("FRIEND_OF") == ("Person", "Person")
    assert get_inferred_labels("WORKS_AT") == ("Person", "Organization")
    assert get_inferred_labels("LIVES_IN") == ("Person", "Location")
    assert get_inferred_labels("REPORTS_TO") == ("Person", "Person")
    assert get_inferred_labels("COLLABORATES_WITH") == ("Person", "Person")


def test_inferred_labels_ambiguous_and_unknown() -> None:
    """Verify that ambiguous or unknown predicates return None."""
    # Ambiguous from/to rules
    assert get_inferred_labels("PART_OF") is None
    assert get_inferred_labels("DUE_ON") is None
    assert get_inferred_labels("CREATED_IN") is None
    assert get_inferred_labels("MEMBER_OF") is None
    assert get_inferred_labels("DISCUSSED") is None
    assert get_inferred_labels("RELATED_TO") is None
    assert get_inferred_labels("LIKES") is None
    assert get_inferred_labels("ALIAS_OF") is None

    # Unknown predicate
    assert get_inferred_labels("NON_EXISTENT_PREDICATE") is None
    assert get_inferred_labels("") is None


def test_untyped_triples_unambiguous_inference() -> None:
    """Verify label inference for unambiguous untyped triples."""
    triples = [
        ["Implement caching", "ASSIGNED_TO", "Sarah Chen"],
        ["Sarah Chen", "WORKS_AT", "InnoTech Labs"],
        ["Sarah Chen", "FRIEND_OF", "David Miller"],
    ]
    payload = triples_to_payload(triples, source="test_source", timestamp="2026-10-18T12:00:00Z")

    assert isinstance(payload, Payload)
    assert payload.source == "test_source"
    assert payload.timestamp == "2026-10-18T12:00:00Z"

    # Entities should be deduplicated
    entity_names = {e.name: e.type for e in payload.entities}
    assert entity_names["Implement caching"] == "Task"
    assert entity_names["Sarah Chen"] == "Person"
    assert entity_names["InnoTech Labs"] == "Organization"
    assert entity_names["David Miller"] == "Person"
    assert len(payload.entities) == 4

    # Relationships
    assert len(payload.relationships) == 3
    assert payload.relationships[0].type == "ASSIGNED_TO"
    assert payload.relationships[0].from_entity.name == "Implement caching"
    assert payload.relationships[0].from_entity.type == "Task"
    assert payload.relationships[0].to_entity.name == "Sarah Chen"
    assert payload.relationships[0].to_entity.type == "Person"


def test_untyped_triples_ambiguous_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """Verify fallback to Concept and RELATED_TO with original predicate as label."""
    triples = [
        ["Subtask A", "PART_OF", "Main Project"],
    ]
    with caplog.at_level(logging.WARNING):
        payload = triples_to_payload(triples, source="test_ambiguous")

    assert any("PART_OF" in record.message and "ambiguous" in record.message for record in caplog.records)

    assert len(payload.entities) == 2
    for entity in payload.entities:
        assert entity.type == "Concept"

    assert len(payload.relationships) == 1
    rel = payload.relationships[0]
    assert rel.type == "RELATED_TO"
    assert rel.props.get("label") == "PART_OF"
    assert rel.from_entity.type == "Concept"
    assert rel.to_entity.type == "Concept"


def test_untyped_triples_unknown_predicate_fallback(caplog: pytest.LogCaptureFixture) -> None:
    """Verify fallback when an unknown predicate is encountered."""
    triples = [
        ["Alice", "ENJOYS_EATING", "Pizza"],
    ]
    with caplog.at_level(logging.WARNING):
        payload = triples_to_payload(triples, source="test_unknown")

    assert any("ENJOYS_EATING" in record.message for record in caplog.records)

    assert len(payload.entities) == 2
    assert len(payload.relationships) == 1
    rel = payload.relationships[0]
    assert rel.type == "RELATED_TO"
    assert rel.props.get("label") == "ENJOYS_EATING"


def test_typed_triples_full_fields() -> None:
    """Verify parsing typed triples with optional fields preserved."""
    triples = [
        {
            "subject": {
                "name": "Sarah Chen",
                "type": "Person",
                "props": {"title": "Staff Engineer"},
                "op": "update",
            },
            "predicate": "WORKS_ON",
            "object": {
                "name": "Core Pipeline",
                "type": "Project",
                "props": {"description": "Speech ingestion core"},
            },
            "confidence": 0.85,
            "op": "add",
            "props": {"quote": "Sarah is currently focusing on Core Pipeline."},
        }
    ]
    payload = triples_to_payload(triples, source="typed_convo", timestamp="2026-10-18T10:00:00Z")

    assert len(payload.entities) == 2
    sarah = next(e for e in payload.entities if e.name == "Sarah Chen")
    assert sarah.type == "Person"
    assert sarah.props["title"] == "Staff Engineer"
    assert sarah.op == "update"

    project = next(e for e in payload.entities if e.name == "Core Pipeline")
    assert project.type == "Project"
    assert project.props["description"] == "Speech ingestion core"
    assert project.op == "add"

    assert len(payload.relationships) == 1
    rel = payload.relationships[0]
    assert rel.type == "WORKS_ON"
    assert rel.props.get("confidence") == 0.85
    assert rel.props.get("quote") == "Sarah is currently focusing on Core Pipeline."
    assert rel.op == "add"


def test_typed_triples_endpoint_deduplication_and_prop_merge() -> None:
    """Verify that multiple occurrences of an entity merge properties without loss."""
    triples = [
        {
            "subject": {"name": "Sarah Chen", "type": "Person", "props": {"title": "Lead"}},
            "predicate": "WORKS_ON",
            "object": {"name": "Project Alpha", "type": "Project"},
        },
        {
            "subject": {"name": "Sarah Chen", "type": "Person", "props": {"email": "sarah@example.com"}},
            "predicate": "LEADS",
            "object": {"name": "Project Alpha", "type": "Project"},
        },
    ]
    payload = triples_to_payload(triples, source="merge_test")

    # Should have 2 unique entities
    assert len(payload.entities) == 2
    sarah = next(e for e in payload.entities if e.name == "Sarah Chen")
    assert sarah.props["title"] == "Lead"
    assert sarah.props["email"] == "sarah@example.com"


def test_malformed_triples_skipped(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that invalid triple entries are logged and skipped gracefully."""
    triples = [
        ["Short list"],
        {"subject": "Not a dict", "predicate": "TEST", "object": {}},
        42,
    ]
    with caplog.at_level(logging.WARNING):
        payload = triples_to_payload(triples, source="malformed_test")

    assert len(payload.entities) == 0
    assert len(payload.relationships) == 0
    assert len(caplog.records) >= 3
