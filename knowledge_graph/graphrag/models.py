"""Data models for GraphRAG retrieval, scoring, and context synthesis."""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Supported Query Intents (RP-27)
QueryIntent = Literal[
    "task_status",
    "blocker_chain",
    "deadline_schedule",
    "meeting_summary",
    "person_context",
    "general",
]


class RetrievalRequest(BaseModel):
    """Input request for GraphRAG multi-hop retrieval."""

    model_config = ConfigDict(populate_by_name=True)

    query: str = Field(..., description="Natural language search query or prompt.")
    seed_entities: List[str] = Field(
        default_factory=list,
        description="Optional explicit seed entity names or keys.",
    )
    max_hops: int = Field(
        default=2,
        description="Maximum traversal depth (clamped strictly to 1..3).",
    )
    top_k: int = Field(
        default=15,
        ge=1,
        description="Maximum number of ranked paths and subgraph elements to return.",
    )
    include_private: bool = Field(
        default=False,
        description="Whether to include entities marked sensitivity='private'.",
    )
    intent: Optional[QueryIntent] = Field(
        default=None,
        description="Optional forced query intent; detected automatically if None.",
    )

    @field_validator("max_hops", mode="before")
    @classmethod
    def clamp_max_hops(cls, v: Any) -> int:
        """Clamp max_hops between 1 and 3 to ensure bounded graph traversal."""
        try:
            val = int(v)
            return max(1, min(3, val))
        except (ValueError, TypeError):
            return 2


class AnchorMatch(BaseModel):
    """Seed entity resolved in the knowledge graph."""

    key: str = Field(..., description="Normalized node key.")
    name: str = Field(..., description="Human readable entity name.")
    type: str = Field(..., description="Primary node label.")
    match_type: Literal[
        "exact_key", "exact_alias", "fuzzy_alias", "fuzzy_name", "substring", "seed_explicit"
    ] = Field(..., description="Technique used to match the anchor node.")
    score: float = Field(..., ge=0.0, le=1.0, description="Match confidence score [0.0..1.0].")


class PathHop(BaseModel):
    """A single relational edge hop within a multi-hop path."""

    from_node: Dict[str, Any] = Field(..., description="Source node summary (key, name, type).")
    relationship_type: str = Field(..., description="Relationship type connecting the nodes.")
    to_node: Dict[str, Any] = Field(..., description="Target node summary (key, name, type).")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Edge extraction certainty [0.0..1.0]."
    )
    props: Dict[str, Any] = Field(
        default_factory=dict, description="Edge properties (kind, quote, source, etc.)."
    )


class ScoredPath(BaseModel):
    """A multi-hop relational path traversed from an anchor node, with mathematical scoring."""

    nodes: List[Dict[str, Any]] = Field(..., description="Sequence of nodes along the path.")
    relationships: List[str] = Field(..., description="Sequence of relationship types traversed.")
    hops: List[PathHop] = Field(
        default_factory=list, description="Detailed hop objects with per-edge properties."
    )
    length: int = Field(..., ge=1, description="Path length (number of relationship hops d).")

    # Explicit mathematical score breakdown
    hop_decay: float = Field(
        ..., description="Decay factor based on path length: 0.75 ** (d - 1)."
    )
    confidence_score: float = Field(
        ..., description="Mean extraction confidence across path edges [0.0..1.0]."
    )
    intent_salience: float = Field(
        ..., description="Mean intent-aligned salience weight across edges [0.0..1.0]."
    )
    recency_score: float = Field(
        ..., description="Recency score based on timestamp properties [0.0..1.0]."
    )
    final_score: float = Field(
        ..., description="Composite path score: 0.35*hop_decay + 0.25*conf + 0.25*intent + 0.15*recency."
    )


class ProvenanceRef(BaseModel):
    """Audio session or conversation source linking back to raw interaction transcripts."""

    conversation_key: str = Field(..., description="Conversation node key.")
    conversation_name: str = Field(..., description="Conversation session display name or audio ID.")
    relationship: str = Field(..., description="Provenance edge type ('CREATED_IN' or 'MENTIONS').")
    entity_key: str = Field(..., description="Key of the entity connected to this conversation.")
    source: Optional[str] = Field(default=None, description="Original source transcript identifier.")
    timestamp: Optional[str] = Field(default=None, description="Session recorded timestamp.")


class RetrievalResult(BaseModel):
    """Complete response payload for a GraphRAG retrieval query."""

    query: str = Field(..., description="Original user query.")
    detected_intent: QueryIntent = Field(..., description="Detected or requested query intent.")
    anchors: List[AnchorMatch] = Field(
        default_factory=list, description="Resolved seed anchor nodes."
    )
    nodes: List[Dict[str, Any]] = Field(
        default_factory=list, description="All unique subgraph entity nodes traversed."
    )
    edges: List[Dict[str, Any]] = Field(
        default_factory=list, description="All unique relationship edges traversed."
    )
    ranked_paths: List[ScoredPath] = Field(
        default_factory=list, description="Top-k multi-hop relational paths ranked by final_score."
    )
    provenance: List[ProvenanceRef] = Field(
        default_factory=list, description="Linked conversation sources (hub-suppressed)."
    )
    formatted_context: str = Field(
        default="", description="Structured Markdown block formatted for downstream LLM synthesis."
    )
    latency_ms: float = Field(
        default=0.0, description="Retrieval and ranking execution latency in milliseconds."
    )
