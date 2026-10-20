"""Unit tests for GraphRAG retrieval data models, intent detection, scoring, and context builder."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from graphrag.anchor_resolver import (
    detect_query_intent,
    get_relationship_intent_salience,
    resolve_seed_anchors,
)
from graphrag.baseline_keyword import _extract_query_keywords, compare_retrieval, keyword_baseline_search
from graphrag.context_builder import build_formatted_context, get_pending_items_context
from graphrag.models import (
    AnchorMatch,
    PathHop,
    ProvenanceRef,
    RetrievalRequest,
    RetrievalResult,
    ScoredPath,
)
from graphrag.retriever import compute_recency_score, retrieve_subgraph, score_path
from main import app


def test_retrieval_request_max_hops_clamping() -> None:
    """Verify max_hops is clamped strictly between 1 and 3."""
    req_low = RetrievalRequest(query="test", max_hops=0)
    assert req_low.max_hops == 1

    req_high = RetrievalRequest(query="test", max_hops=5)
    assert req_high.max_hops == 3

    req_valid = RetrievalRequest(query="test", max_hops=2)
    assert req_valid.max_hops == 2


@pytest.mark.parametrize(
    "query, expected_intent",
    [
        ("What is blocking the benchmark task?", "blocker_chain"),
        ("Are there any issues or obstacles on whisper transcription?", "blocker_chain"),
        ("When is the deployment deadline?", "deadline_schedule"),
        ("What is on the calendar schedule for Friday?", "deadline_schedule"),
        ("What is David working on?", "task_status"),
        ("Show me all in progress tasks and action items", "task_status"),
        ("Summarize the Sprint 14 Architecture Sync meeting", "meeting_summary"),
        ("Who attended the discussion call yesterday?", "meeting_summary"),
        ("Who is Sarah Chen?", "person_context"),
        ("Where does Elena live and who are her friends?", "person_context"),
        ("Ollama quantization details", "general"),
    ],
)
def test_detect_query_intent(query: str, expected_intent: str) -> None:
    """Verify rule/keyword intent detector classifies query types accurately."""
    detected = detect_query_intent(query)
    assert detected == expected_intent


def test_intent_salience_boosts() -> None:
    """Verify relationship intent salience maps according to RP-27 requirements."""
    # Blocker queries boost BLOCKED_BY, HAS_ISSUE, RESOLVES
    assert get_relationship_intent_salience("BLOCKED_BY", "blocker_chain") == 1.0
    assert get_relationship_intent_salience("HAS_ISSUE", "blocker_chain") == 1.0
    assert get_relationship_intent_salience("RESOLVES", "blocker_chain") == 1.0
    assert get_relationship_intent_salience("RELATED_TO", "blocker_chain") == 0.30

    # Task queries boost ASSIGNED_TO, WORKS_ON, PART_OF, DUE_ON
    assert get_relationship_intent_salience("ASSIGNED_TO", "task_status") == 1.0
    assert get_relationship_intent_salience("WORKS_ON", "task_status") == 0.95
    assert get_relationship_intent_salience("DUE_ON", "task_status") == 0.80

    # Deadline queries boost DUE_ON, SCHEDULED_ON
    assert get_relationship_intent_salience("DUE_ON", "deadline_schedule") == 1.0
    assert get_relationship_intent_salience("SCHEDULED_ON", "deadline_schedule") == 1.0

    # Person queries boost FAMILY_OF, FRIEND_OF, LIVES_IN, WORKS_AT
    assert get_relationship_intent_salience("FAMILY_OF", "person_context") == 1.0
    assert get_relationship_intent_salience("FRIEND_OF", "person_context") == 1.0
    assert get_relationship_intent_salience("LIVES_IN", "person_context") == 1.0
    assert get_relationship_intent_salience("WORKS_AT", "person_context") == 1.0

    # ALIAS_OF is always 1.0
    assert get_relationship_intent_salience("ALIAS_OF", "general") == 1.0

    # Tier-1 edges preferred over Tier-2 and RELATED_TO fallback
    assert get_relationship_intent_salience("ASSIGNED_TO", "general") > get_relationship_intent_salience(
        "USES", "general"
    )
    assert get_relationship_intent_salience("USES", "general") > get_relationship_intent_salience(
        "RELATED_TO", "general"
    )


def test_composite_path_scoring_formula() -> None:
    """Verify exact composite score: 0.35*(0.75**(d-1)) + 0.25*conf + 0.25*intent + 0.15*recency."""
    nodes_1 = [
        {"key": "sarah chen", "name": "Sarah Chen", "type": "Person", "props": {}},
        {"key": "benchmark", "name": "Benchmark", "type": "Task", "props": {}},
    ]
    hops_1 = [
        PathHop(
            from_node={"key": "benchmark", "name": "Benchmark", "type": "Task"},
            relationship_type="ASSIGNED_TO",
            to_node={"key": "sarah chen", "name": "Sarah Chen", "type": "Person"},
            confidence=1.0,
        )
    ]
    # d = 1: decay = 1.0, conf = 1.0, intent = 1.0 (for task_status), recency = 0.60
    # final_score = 0.35 * 1.0 + 0.25 * 1.0 + 0.25 * 1.0 + 0.15 * 0.60 = 0.35 + 0.25 + 0.25 + 0.09 = 0.94
    scored_1 = score_path(nodes_1, hops_1, intent="task_status")
    assert scored_1.length == 1
    assert scored_1.hop_decay == 1.0
    assert scored_1.confidence_score == 1.0
    assert scored_1.intent_salience == 1.0
    assert scored_1.recency_score == 0.60
    assert scored_1.final_score == 0.94

    # d = 2: decay = 0.75
    nodes_2 = nodes_1 + [{"key": "oct 21", "name": "2026-10-21", "type": "Deadline", "props": {}}]
    hops_2 = hops_1 + [
        PathHop(
            from_node={"key": "benchmark", "name": "Benchmark", "type": "Task"},
            relationship_type="DUE_ON",
            to_node={"key": "oct 21", "name": "2026-10-21", "type": "Deadline"},
            confidence=0.8,
        )
    ]
    # mean_conf = (1.0 + 0.8) / 2 = 0.90
    # salience = (1.0 + 0.80) / 2 = 0.90
    # recency = 0.60
    # final_score = 0.35 * 0.75 + 0.25 * 0.90 + 0.25 * 0.90 + 0.15 * 0.60
    #              = 0.2625 + 0.225 + 0.225 + 0.09 = 0.8025
    scored_2 = score_path(nodes_2, hops_2, intent="task_status")
    assert scored_2.length == 2
    assert scored_2.hop_decay == 0.75
    assert scored_2.confidence_score == 0.90
    assert scored_2.intent_salience == 0.90
    assert scored_2.final_score == 0.8025


def test_recency_score_decay() -> None:
    """Verify recency scoring computes expected decay values."""
    ref = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)

    # 2 days old -> 1.00
    assert compute_recency_score({"updated_at": "2026-10-16T10:00:00Z"}, reference_time=ref) == 1.00

    # 20 days old -> 0.85
    assert compute_recency_score({"date": "2026-09-28"}, reference_time=ref) == 0.85

    # 60 days old -> 0.70
    assert compute_recency_score({"created_at": "2026-08-15T00:00:00Z"}, reference_time=ref) == 0.70

    # No timestamp -> 0.60 default
    assert compute_recency_score({}, reference_time=ref) == 0.60


def test_resolve_seed_anchors_matching_hierarchy() -> None:
    """Verify exact key (1.0), alias (0.95), and substring/fuzzy matches."""
    mock_session = MagicMock()
    mock_records = [
        {
            "key": "sarah chen",
            "name": "Sarah Chen",
            "type": "Person",
            "aliases": ["Dr. Chen", "Sarah C."],
            "sensitivity": "normal",
        },
        {
            "key": "whisper memory limit exceeded",
            "name": "Whisper Memory Limit Exceeded",
            "type": "Issue",
            "aliases": ["OOM Whisper"],
            "sensitivity": "normal",
        },
    ]
    mock_session.run.return_value = mock_records

    # 1. Exact key match
    res_exact = resolve_seed_anchors(mock_session, query="Who is Sarah Chen?")
    assert len(res_exact) >= 1
    sarah = next(a for a in res_exact if a.key == "sarah chen")
    assert sarah.score == 1.0
    assert sarah.match_type in ("exact_key", "seed_explicit")

    # 2. Alias match
    res_alias = resolve_seed_anchors(mock_session, query="What did Dr. Chen propose?")
    assert len(res_alias) >= 1
    sarah_alias = next(a for a in res_alias if a.key == "sarah chen")
    assert sarah_alias.score == 0.95
    assert sarah_alias.match_type == "exact_alias"

    # 3. Fuzzy match
    res_fuzzy = resolve_seed_anchors(mock_session, query="Whisper Memroy Limit")
    assert len(res_fuzzy) >= 1
    issue = next(a for a in res_fuzzy if a.key == "whisper memory limit exceeded")
    assert issue.score >= 0.80


def test_resolve_seed_anchors_private_filtering() -> None:
    """Verify private nodes are excluded when include_private=False."""
    mock_session = MagicMock()
    mock_session.run.return_value = []

    resolve_seed_anchors(mock_session, query="Test", include_private=False)
    args, kwargs = mock_session.run.call_args
    assert kwargs["include_private"] is False


def test_context_builder_markdown_structure() -> None:
    """Verify build_formatted_context includes all 4 structured Markdown sections."""
    result = RetrievalResult(
        query="What is blocking the benchmark task?",
        detected_intent="blocker_chain",
        anchors=[
            AnchorMatch(
                key="benchmark",
                name="Benchmark Ollama 8B",
                type="Task",
                match_type="exact_key",
                score=1.0,
            )
        ],
        nodes=[
            {
                "key": "benchmark",
                "name": "Benchmark Ollama 8B",
                "type": "Task",
                "props": {"status": "in progress", "priority": "high"},
            },
            {
                "key": "whisper oom",
                "name": "Whisper Memory Crash",
                "type": "Issue",
                "props": {"status": "open", "severity": "high"},
            },
        ],
        edges=[],
        ranked_paths=[
            ScoredPath(
                nodes=[
                    {"key": "benchmark", "name": "Benchmark Ollama 8B", "type": "Task"},
                    {"key": "whisper oom", "name": "Whisper Memory Crash", "type": "Issue"},
                ],
                relationships=["BLOCKED_BY"],
                hops=[
                    PathHop(
                        from_node={"key": "benchmark", "name": "Benchmark Ollama 8B", "type": "Task"},
                        relationship_type="BLOCKED_BY",
                        to_node={"key": "whisper oom", "name": "Whisper Memory Crash", "type": "Issue"},
                        confidence=1.0,
                    )
                ],
                length=1,
                hop_decay=1.0,
                confidence_score=1.0,
                intent_salience=1.0,
                recency_score=0.7,
                final_score=0.955,
            )
        ],
        provenance=[
            ProvenanceRef(
                conversation_key="voice_sync_1",
                conversation_name="Voice Sync 1",
                relationship="CREATED_IN",
                entity_key="benchmark",
                source="audio_01",
            )
        ],
        formatted_context="",
        latency_ms=12.5,
    )

    ctx = build_formatted_context(result)
    assert "### [Seed Entities]" in ctx
    assert "**Benchmark Ollama 8B** (Task)" in ctx
    assert "### [Multi-Hop Relational Paths with Scores]" in ctx
    assert "--[BLOCKED_BY]--> (Issue: Whisper Memory Crash)" in ctx
    assert "### [Entity Details & Properties]" in ctx
    assert '**Task**: "Benchmark Ollama 8B" {priority: high, status: in progress}' in ctx
    assert "### [Conversation Provenance]" in ctx
    assert "Session **Voice Sync 1** -[:CREATED_IN]-> Entity `benchmark`" in ctx


def test_keyword_baseline_tokenization() -> None:
    """Verify stop words are filtered from keyword baseline search."""
    tokens = _extract_query_keywords("Why is the benchmark task blocked?")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "benchmark" in tokens
    assert "task" in tokens
    assert "blocked" in tokens


def test_compare_retrieval_multi_hop_gain() -> None:
    """Verify compare_retrieval calculates multi_hop_entity_gain correctly."""
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    req = RetrievalRequest(query="benchmark task", max_hops=2)

    sample_path = ScoredPath(
        nodes=[
            {"key": "benchmark", "name": "Benchmark Task", "type": "Task"},
            {"key": "whisper oom", "name": "Whisper Memory Limit", "type": "Issue"},
        ],
        relationships=["BLOCKED_BY"],
        hops=[
            PathHop(
                from_node={"key": "benchmark", "name": "Benchmark Task", "type": "Task"},
                relationship_type="BLOCKED_BY",
                to_node={"key": "whisper oom", "name": "Whisper Memory Limit", "type": "Issue"},
                confidence=1.0,
            )
        ],
        length=1,
        hop_decay=1.0,
        confidence_score=1.0,
        intent_salience=1.0,
        recency_score=0.6,
        final_score=0.94,
    )

    # Mock retrieve_subgraph to return 2 entities: Benchmark (seed) and Whisper OOM (via hop)
    with patch("graphrag.baseline_keyword.retrieve_subgraph") as mock_retriever, \
         patch("graphrag.baseline_keyword.keyword_baseline_search") as mock_baseline:

        mock_retriever.return_value = RetrievalResult(
            query="benchmark task",
            detected_intent="task_status",
            anchors=[],
            nodes=[
                {"key": "benchmark", "name": "Benchmark Task", "type": "Task"},
                {"key": "whisper oom", "name": "Whisper Memory Limit", "type": "Issue"},
            ],
            edges=[],
            ranked_paths=[sample_path],
            provenance=[],
            latency_ms=10.0,
        )

        # Baseline only matched the literal "Benchmark Task" node
        mock_baseline.return_value = {
            "query": "benchmark task",
            "terms": ["benchmark", "task"],
            "nodes": [{"key": "benchmark", "name": "Benchmark Task", "type": "Task"}],
            "count": 1,
            "latency_ms": 5.0,
        }

        comparison = compare_retrieval(req, driver=mock_driver)
        assert comparison["metrics"]["graphrag_entity_count"] == 2
        assert comparison["metrics"]["keyword_entity_count"] == 1
        assert comparison["metrics"]["multi_hop_gain_count"] == 1
        assert len(comparison["multi_hop_entity_gain"]) == 1
        assert comparison["multi_hop_entity_gain"][0]["key"] == "whisper oom"
        assert "Whisper Memory Limit" in comparison["summary"]


def test_fastapi_endpoints_with_test_client() -> None:
    """Verify FastAPI /retrieve, /retrieve/compare, and /retrieve/pending routes."""
    client = TestClient(app)

    # 1. /retrieve
    with patch("main.retrieve_subgraph") as mock_subgraph:
        mock_subgraph.return_value = RetrievalResult(
            query="Sarah Chen",
            detected_intent="person_context",
            anchors=[],
            nodes=[],
            edges=[],
            ranked_paths=[],
            provenance=[],
            formatted_context="formatted markdown",
            latency_ms=15.0,
        )
        res = client.post("/retrieve", json={"query": "Sarah Chen", "max_hops": 2})
        assert res.status_code == 200
        data = res.json()
        assert data["detected_intent"] == "person_context"
        assert data["formatted_context"] == "formatted markdown"

    # 2. /retrieve/compare
    with patch("main.compare_retrieval") as mock_compare:
        mock_compare.return_value = {
            "query": "Benchmark",
            "detected_intent": "task_status",
            "max_hops": 2,
            "metrics": {"multi_hop_gain_count": 2},
            "multi_hop_entity_gain": [],
            "summary": "gain summary",
        }
        res2 = client.post("/retrieve/compare", json={"query": "Benchmark"})
        assert res2.status_code == 200
        assert res2.json()["metrics"]["multi_hop_gain_count"] == 2

    # 3. /retrieve/pending
    with patch("main.get_pending_items_context") as mock_pending:
        mock_pending.return_value = {
            "tasks": [{"task_name": "Fix crash", "status": "blocked"}],
            "count": 1,
            "formatted_context": "### [Pending Tasks]",
        }
        res3 = client.get("/retrieve/pending")
        assert res3.status_code == 200
        assert res3.json()["count"] == 1


def test_llm_synthesizer_with_mocked_ollama_and_fallback() -> None:
    """Verify local Ollama LLaMA 3 8B answer synthesis and offline deterministic fallback."""
    from graphrag.llm_synthesizer import synthesize_grounded_answer

    sample_result = RetrievalResult(
        query="What is blocking the payment flow task?",
        detected_intent="blocker_chain",
        anchors=[
            AnchorMatch(
                key="test payment flow",
                name="Test payment flow",
                type="Task",
                match_type="exact_key",
                score=1.0,
            )
        ],
        ranked_paths=[
            ScoredPath(
                nodes=[
                    {"key": "test payment flow", "name": "Test payment flow", "type": "Task"},
                    {"key": "payment api not available", "name": "Payment API not available", "type": "Issue"},
                ],
                relationships=["BLOCKED_BY"],
                hops=[
                    PathHop(
                        from_node={"key": "test payment flow", "name": "Test payment flow", "type": "Task"},
                        relationship_type="BLOCKED_BY",
                        to_node={"key": "payment api not available", "name": "Payment API not available", "type": "Issue"},
                        confidence=0.95,
                    )
                ],
                length=1,
                hop_decay=1.0,
                confidence_score=0.95,
                intent_salience=1.0,
                recency_score=0.85,
                final_score=0.965,
            )
        ],
        formatted_context="### [Multi-Hop Relational Paths with Scores]\n1. (Task: Test payment flow) --[BLOCKED_BY]--> (Issue: Payment API not available)",
    )

    # 1. Mocked Ollama LLaMA 3 8B online response
    with patch("graphrag.llm_synthesizer.ollama.Client") as mock_ollama_cls:
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.content = "The 'Test payment flow' task is BLOCKED_BY the issue 'Payment API not available'."
        mock_resp = MagicMock()
        mock_resp.message = mock_msg
        mock_client.chat.return_value = mock_resp
        mock_ollama_cls.return_value = mock_client

        syn = synthesize_grounded_answer(sample_result, model="llama3:8b")
        assert syn["used_fallback"] is False
        assert syn["model_used"] == "llama3:8b"
        assert "BLOCKED_BY" in syn["answer"]

    # 2. Offline Ollama fallback
    with patch("graphrag.llm_synthesizer.ollama.Client", side_effect=ConnectionError("Ollama offline")):
        syn_fb = synthesize_grounded_answer(sample_result, model="llama3:8b")
        assert syn_fb["used_fallback"] is True
        assert "deterministic_fallback" in syn_fb["model_used"]
        assert "Test payment flow (Task) --[BLOCKED_BY]--> Payment API not available (Issue)" in syn_fb["answer"]


def test_location_query_intent_salience_and_path_ranking() -> None:
    """Verify that location-seeking queries prioritize LOCATED_AT and demote non-spatial edges."""
    query = "where is the dilini's party?"

    # Baseline intent salience
    assert get_relationship_intent_salience("LOCATED_AT", "person_context") == 1.0
    assert get_relationship_intent_salience("LOCATED_AT", "deadline_schedule") == 0.95

    # Query-aware contextual salience
    assert get_relationship_intent_salience("LOCATED_AT", "person_context", query=query) == 1.0
    assert get_relationship_intent_salience("LIVES_IN", "person_context", query=query) == 1.0
    assert get_relationship_intent_salience("FAMILY_OF", "person_context", query=query) == 0.60
    assert get_relationship_intent_salience("FRIEND_OF", "person_context", query=query) == 0.60

    # Score Path 1: Dilini surprise party -[LOCATED_AT]-> Kandy
    party_path = score_path(
        path_nodes=[
            {"key": "dilini surprise party", "name": "Dilini surprise party", "type": "Event"},
            {"key": "kandy", "name": "Kandy", "type": "Location"},
        ],
        path_hops=[
            PathHop(
                from_node={"key": "dilini surprise party", "name": "Dilini surprise party", "type": "Event"},
                relationship_type="LOCATED_AT",
                to_node={"key": "kandy", "name": "Kandy", "type": "Location"},
                confidence=1.0,
            )
        ],
        intent="person_context",
        query=query,
    )

    # Score Path 2: Dilini -[FAMILY_OF]-> Ruwan
    family_path = score_path(
        path_nodes=[
            {"key": "dilini", "name": "Dilini", "type": "Person"},
            {"key": "ruwan", "name": "Ruwan", "type": "Person"},
        ],
        path_hops=[
            PathHop(
                from_node={"key": "dilini", "name": "Dilini", "type": "Person"},
                relationship_type="FAMILY_OF",
                to_node={"key": "ruwan", "name": "Ruwan", "type": "Person"},
                confidence=1.0,
            )
        ],
        intent="person_context",
        query=query,
    )

    # The location path must decisively outrank the family path
    assert party_path.intent_salience == 1.0
    assert family_path.intent_salience == 0.60
    assert party_path.final_score > family_path.final_score
    assert party_path.final_score == pytest.approx(0.94, abs=0.01)
    assert family_path.final_score == pytest.approx(0.84, abs=0.01)


def test_multi_token_anchor_resolution() -> None:
    """Verify that multi-word query phrases match multi-word entities (e.g. 'dilini surprise party')."""
    mock_session = MagicMock()
    mock_records = [
        {
            "key": "dilini",
            "name": "Dilini",
            "type": "Person",
            "aliases": [],
            "sensitivity": "normal",
        },
        {
            "key": "dilini surprise party",
            "name": "Dilini surprise party",
            "type": "Event",
            "aliases": ["dilini party"],
            "sensitivity": "normal",
        },
    ]
    mock_session.run.return_value = mock_records

    anchors = resolve_seed_anchors(mock_session, query="where is the dilini's party?")
    anchor_keys = [a.key for a in anchors]

    assert "dilini surprise party" in anchor_keys
    party_anchor = next(a for a in anchors if a.key == "dilini surprise party")
    assert party_anchor.score >= 0.92
    assert party_anchor.match_type in ("multi_token_match", "exact_alias", "fuzzy_name")

