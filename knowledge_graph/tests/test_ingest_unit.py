"""Unit tests for ingestion logic, meeting key rules, aliases, and symmetry (no database)."""

from typing import Any, Dict, List
from unittest.mock import MagicMock
import pytest

from graph_schema.ingest import (
    ALIAS_THRESHOLD,
    ALLOWED_EDGE_PROPS,
    PROVENANCE_CREATED_IN_LABELS,
    IngestResult,
    _resolve_entity_key,
    compute_meeting_key,
)
from graph_schema.models import (
    SINGLE_VALUED_RELATIONSHIPS,
    SYMMETRIC_RELATIONSHIPS,
    canonical_pair,
    normalize_key,
)


def test_meeting_key_computation() -> None:
    """Verify Meeting key calculation rules."""
    # 1. With entity props['date']
    key1 = compute_meeting_key("Sprint 15 Sync", {"date": "2026-10-18"}, None)
    assert key1 == "sprint 15 sync 2026-10-18"

    # 2. With payload timestamp (ISO format) when props['date'] is absent
    key2 = compute_meeting_key("Sprint 15 Sync", {}, "2026-10-18T10:30:00Z")
    assert key2 == "sprint 15 sync 2026-10-18"

    # 3. With payload timestamp (date-only) when props is None
    key3 = compute_meeting_key("Sprint 15 Sync", None, "2026-10-18")
    assert key3 == "sprint 15 sync 2026-10-18"

    # 4. Without any date
    key4 = compute_meeting_key("Sprint 15 Sync", None, None)
    assert key4 == "sprint 15 sync"

    # 5. Entity props['date'] takes precedence over payload.timestamp
    key5 = compute_meeting_key(
        "Architecture Alignment",
        {"date": "2026-10-20"},
        "2026-10-18T12:00:00Z",
    )
    assert key5 == "architecture alignment 2026-10-20"


def test_alias_threshold_constant() -> None:
    """Verify module alias threshold constant."""
    assert ALIAS_THRESHOLD == 90


def test_entity_resolution_exact_and_fuzzy() -> None:
    """Verify entity key resolution with exact, fuzzy (>=90), and non-matching (<90)."""
    mock_tx = MagicMock()
    result = IngestResult()

    # Pre-populate label cache with an existing Person node
    label_cache: Dict[str, Dict[str, Dict[str, Any]]] = {
        "Person": {
            "sarah perera": {
                "name": "Sarah Perera",
                "aliases": ["Saza"],
            }
        },
        "Task": {
            "deploy notification service": {
                "name": "Deploy notification service",
                "aliases": [],
            }
        },
    }

    # Case 1: Exact key match
    key, is_fuzzy = _resolve_entity_key(
        tx=mock_tx,
        label="Person",
        candidate_key="sarah perera",
        display_name="Sarah Perera",
        label_cache=label_cache,
        result=result,
    )
    assert key == "sarah perera"
    assert is_fuzzy is False
    assert result.aliases_added == 0

    # Case 2: Fuzzy match with ratio >= 90 (typo in task name)
    key, is_fuzzy = _resolve_entity_key(
        tx=mock_tx,
        label="Task",
        candidate_key="deploy notification serivce",
        display_name="Deploy notification serivce",
        label_cache=label_cache,
        result=result,
    )
    assert key == "deploy notification service"
    assert is_fuzzy is True
    assert result.aliases_added == 1
    assert "Deploy notification serivce" in label_cache["Task"]["deploy notification service"]["aliases"]
    assert mock_tx.run.called

    # Case 3: Different key with ratio < 90 ("sarah" vs "sarah perera")
    key, is_fuzzy = _resolve_entity_key(
        tx=mock_tx,
        label="Person",
        candidate_key="sarah",
        display_name="Sarah",
        label_cache=label_cache,
        result=result,
    )
    assert key == "sarah"
    assert is_fuzzy is False
    # Candidate should be registered as a separate entry
    assert "sarah" in label_cache["Person"]


def test_symmetric_canonical_ordering() -> None:
    """Verify canonical_pair ordering for symmetric relationships."""
    assert "FRIEND_OF" in SYMMETRIC_RELATIONSHIPS
    assert "PARTNER_OF" in SYMMETRIC_RELATIONSHIPS
    assert "COLLABORATES_WITH" in SYMMETRIC_RELATIONSHIPS

    # Symmetric relationships always sort alphabetically
    assert canonical_pair("FRIEND_OF", "ruwan", "kamal") == ("kamal", "ruwan")
    assert canonical_pair("FRIEND_OF", "kamal", "ruwan") == ("kamal", "ruwan")
    assert canonical_pair("PARTNER_OF", "bob", "alice") == ("alice", "bob")

    # Non-symmetric relationships preserve direction unchanged
    assert canonical_pair("ASSIGNED_TO", "task_1", "person_1") == ("task_1", "person_1")
    assert canonical_pair("DUE_ON", "task_1", "deadline_1") == ("task_1", "deadline_1")
    assert canonical_pair("LEADS", "person_1", "team_1") == ("person_1", "team_1")


def test_single_valued_relationship_constants() -> None:
    """Verify single-valued relationships set."""
    assert SINGLE_VALUED_RELATIONSHIPS == {"DUE_ON", "SCHEDULED_ON", "LIVES_IN"}


def test_allowed_edge_properties() -> None:
    """Verify whitelisted relationship edge properties."""
    assert ALLOWED_EDGE_PROPS == {"confidence", "kind", "label", "quote"}


def test_provenance_labels() -> None:
    """Verify labels routed to CREATED_IN vs MENTIONS."""
    expected = {"Task", "Decision", "Issue", "Question", "Idea", "Note", "Document"}
    assert PROVENANCE_CREATED_IN_LABELS == expected


def test_ingest_result_to_dict() -> None:
    """Verify IngestResult serialization."""
    res = IngestResult(
        nodes_created=2,
        nodes_merged=1,
        edges_created=3,
        edges_merged=0,
        edges_replaced=1,
        aliases_added=1,
        warnings=["DUE_ON: 2026-10-18 -> 2026-10-25"],
        touched={("Task", "task-1"), ("Person", "person-1")},
    )
    d = res.to_dict()
    assert d["nodes_created"] == 2
    assert d["nodes_merged"] == 1
    assert d["edges_created"] == 3
    assert d["edges_merged"] == 0
    assert d["edges_replaced"] == 1
    assert d["aliases_added"] == 1
    assert d["warnings"] == ["DUE_ON: 2026-10-18 -> 2026-10-25"]
    assert len(d["touched"]) == 2
    assert ["Person", "person-1"] in d["touched"]
    assert ["Task", "task-1"] in d["touched"]
