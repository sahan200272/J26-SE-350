"""Definitions, disambiguations, and schema metadata for Knowledge Graph types."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from graph_schema.models import (
    ALLOWED_DIRECTIONS,
    ALLOWED_NODE_LABELS,
    ALLOWED_PROPERTIES,
    ALLOWED_RELATIONSHIP_TYPES,
)

TIER_1_LABELS = {
    "Person",
    "Team",
    "Organization",
    "Project",
    "Task",
    "Meeting",
    "Decision",
    "Issue",
    "Question",
    "Deadline",
    "Location",
    "Document",
}

NODE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "Person": {
        "tier": 1,
        "definition": "An individual participant, employee, or stakeholder mentioned in conversations.",
        "example": "Sarah Chen, Staff AI Engineer",
    },
    "Team": {
        "tier": 1,
        "definition": "A formal or informal group of people working together within an organization.",
        "example": "Core AI Pipeline Team",
    },
    "Organization": {
        "tier": 1,
        "definition": "A company, institution, partner, or enterprise entity.",
        "example": "InnoTech Labs",
    },
    "Project": {
        "tier": 1,
        "definition": "A coordinated workstream or initiative with defined deliverables.",
        "example": "Local Voice AI Assistant",
    },
    "Task": {
        "tier": 1,
        "definition": "An actionable work item that someone must do (distinguished from an Idea or Decision).",
        "example": "Benchmark Ollama 8B inference latency on M2 Mac",
    },
    "Meeting": {
        "tier": 1,
        "definition": "A scheduled or ad-hoc gathering where people discuss topics and align on work.",
        "example": "Sprint 14 Architecture Sync",
    },
    "Decision": {
        "tier": 1,
        "definition": "An agreed-upon conclusion, policy, or choice that has already been decided.",
        "example": "Adopt Neo4j 5 as the single source of truth for graph memory",
    },
    "Issue": {
        "tier": 1,
        "definition": "A problem, bug, risk, obstacle, or blocker hindering progress that needs resolution.",
        "example": "Whisper transcription runs out of memory on 8GB machines",
    },
    "Question": {
        "tier": 1,
        "definition": "An open, unresolved question or inquiry raised in discussion that requires an answer.",
        "example": "Can we offload embedding calculation to the Apple Neural Engine?",
    },
    "Deadline": {
        "tier": 1,
        "definition": "A specific date, time, or target milestone by which something must finish.",
        "example": "2026-10-18T18:00:00Z",
    },
    "Location": {
        "tier": 1,
        "definition": "A physical room, office, or virtual platform where an event or meeting occurs.",
        "example": "Conference Room A / Zoom Room 4",
    },
    "Document": {
        "tier": 1,
        "definition": "A written file, specification, design doc, PRD, or meeting agenda.",
        "example": "RFC-204 Local Graph Storage Architecture",
    },
    "Goal": {
        "tier": 2,
        "definition": "A high-level strategic objective or outcome that projects and tasks support.",
        "example": "Achieve sub-500ms voice response latency",
    },
    "Idea": {
        "tier": 2,
        "definition": "A proposed suggestion or possibility put forward for consideration that is not yet decided.",
        "example": "Cache acoustic embeddings in SQLite for instant repeat lookups",
    },
    "Tool": {
        "tier": 2,
        "definition": "A software tool, runtime, framework, library, or platform used by teams or projects.",
        "example": "Neo4j 5, Docker Compose, PyTorch",
    },
    "Metric": {
        "tier": 2,
        "definition": "A quantitative benchmark, measurement, or key performance indicator.",
        "example": "P99 Response Latency: 120ms",
    },
    "Event": {
        "tier": 2,
        "definition": "A calendar occurrence, public demo, release date, or milestone event.",
        "example": "Private Beta Release Demo",
    },
    "Topic": {
        "tier": 2,
        "definition": "A subject area, domain, or theme discussed in meetings, notes, or decisions.",
        "example": "Memory Optimization and Quantization",
    },
    "Concept": {
        "tier": 2,
        "definition": "A domain concept, entity, or fallback node for unrecognized entity types.",
        "example": "Zero-Knowledge Proofs",
    },
    "Preference": {
        "tier": 2,
        "definition": "A stated user preference, constraint, or work habit.",
        "example": "Prefers asynchronous meeting updates",
    },
    "Note": {
        "tier": 2,
        "definition": "A freeform text note, memo, or excerpt.",
        "example": "Quick takeaway notes from retrospective",
    },
    "Conversation": {
        "tier": 2,
        "definition": "A recorded speech interaction, dialogue, or voice session transcript.",
        "example": "voice_convo_20261011_1430",
    },
}

RELATIONSHIP_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "MEMBER_OF": {
        "definition": "Indicates a person belongs to a team or organization.",
        "example": "Sarah MEMBER_OF Core AI Pipeline Team",
    },
    "LEADS": {
        "definition": "Indicates a person directs, facilitates, or leads a team, project, or meeting.",
        "example": "Sarah LEADS Sprint 14 Architecture Sync",
    },
    "REPORTS_TO": {
        "definition": "Indicates an organizational reporting relationship between people.",
        "example": "David REPORTS_TO Sarah",
    },
    "COLLABORATES_WITH": {
        "definition": "Indicates direct working partnership between two people.",
        "example": "Sarah COLLABORATES_WITH David",
    },
    "ATTENDED": {
        "definition": "Records that a person was present at a meeting.",
        "example": "Sarah ATTENDED Sprint 14 Architecture Sync",
    },
    "ABSENT_FROM": {
        "definition": "Records that an expected person was absent from a meeting.",
        "example": "Alex ABSENT_FROM Sprint 14 Architecture Sync",
    },
    "ASSIGNED_TO": {
        "definition": "Assigns responsibility for completing a task to a person.",
        "example": "Benchmark Ollama ASSIGNED_TO David",
    },
    "REQUESTED_BY": {
        "definition": "Identifies the person who asked for or requested a task.",
        "example": "Benchmark Ollama REQUESTED_BY Sarah",
    },
    "WORKS_ON": {
        "definition": "Associates a person with a project they contribute to.",
        "example": "David WORKS_ON Local Voice AI Assistant",
    },
    "PART_OF": {
        "definition": "Subsumption link between tasks or projects.",
        "example": "Benchmark Ollama PART_OF Local Voice AI Assistant",
    },
    "DEPENDS_ON": {
        "definition": "Indicates a task or project requires another task or project to complete first.",
        "example": "Integration Testing DEPENDS_ON Benchmark Ollama",
    },
    "BLOCKED_BY": {
        "definition": "Indicates a task or project is actively blocked by an issue or task.",
        "example": "Benchmark Ollama BLOCKED_BY OOM Crash Issue",
    },
    "FOLLOW_UP_OF": {
        "definition": "Indicates a task or meeting was created as a direct next step from a prior item.",
        "example": "Memory Tuning Task FOLLOW_UP_OF Architecture Sync Meeting",
    },
    "SUPPORTS": {
        "definition": "Connects an actionable task or project to the strategic goal it advances.",
        "example": "Benchmark Ollama SUPPORTS Sub-500ms Latency Goal",
    },
    "DUE_ON": {
        "definition": "Associates a task, project, or goal with its target deadline.",
        "example": "Benchmark Ollama DUE_ON 2026-10-18",
    },
    "SCHEDULED_ON": {
        "definition": "Specifies the scheduled date or deadline for a meeting or event.",
        "example": "Architecture Sync SCHEDULED_ON 2026-10-18",
    },
    "LOCATED_AT": {
        "definition": "Associates a meeting, event, or task with its physical or virtual location.",
        "example": "Architecture Sync LOCATED_AT Conference Room A",
    },
    "CREATED_IN": {
        "definition": "Records the meeting or conversation context in which an item or decision originated.",
        "example": "Adopt Neo4j Decision CREATED_IN Architecture Sync Meeting",
    },
    "DISCUSSED": {
        "definition": "Broad link from a meeting to any entity or topic brought up in conversation.",
        "example": "Architecture Sync Meeting DISCUSSED Ollama Memory Consumption",
    },
    "DECIDED": {
        "definition": "Connects a person to a formal decision they made or championed.",
        "example": "Sarah DECIDED Adopt Neo4j 5",
    },
    "RAISED": {
        "definition": "Connects a person to an issue, blocker, or open question they voiced.",
        "example": "David RAISED Whisper OOM Crash Issue",
    },
    "PROPOSED": {
        "definition": "Connects a person to an idea or exploratory suggestion they submitted.",
        "example": "David PROPOSED SQLite Caching Idea",
    },
    "HAS_ISSUE": {
        "definition": "Links a project or task directly to an identified issue or blocker.",
        "example": "Voice Assistant Project HAS_ISSUE Whisper OOM Crash",
    },
    "RESOLVES": {
        "definition": "Indicates that completing a task or executing a decision resolves an issue.",
        "example": "Adopt Quantized Model Decision RESOLVES Whisper OOM Crash",
    },
    "ANSWERS": {
        "definition": "Links a decision or note that answers an open question.",
        "example": "Adopt Quantized Model Decision ANSWERS Which LLM Model Question",
    },
    "SUPERSEDES": {
        "definition": "Indicates a new decision replaces, updates, or invalidates an earlier decision.",
        "example": "Adopt Neo4j Decision SUPERSEDES Use Raw SQLite Decision",
    },
    "AGREES_WITH": {
        "definition": "Records agreement by a person with an idea, decision, or colleague.",
        "example": "Sarah AGREES_WITH SQLite Caching Proposal",
    },
    "DISAGREES_WITH": {
        "definition": "Records dissent or objection by a person to an idea, decision, or colleague.",
        "example": "Sarah DISAGREES_WITH Cloud Sync Idea",
    },
    "REFERENCES": {
        "definition": "Cites or refers to an external document, specification, or PRD.",
        "example": "Adopt Neo4j Decision REFERENCES RFC-204 Document",
    },
    "USES": {
        "definition": "Associates a project, task, or team with a software tool or platform.",
        "example": "Core AI Pipeline Team USES Neo4j 5",
    },
    "HAS_METRIC": {
        "definition": "Connects an entity to an observed or target quantitative metric.",
        "example": "Voice Assistant Project HAS_METRIC Sub-500ms Latency Metric",
    },
    "ABOUT": {
        "definition": "Specifies the subject matter topic of a note, decision, idea, or meeting.",
        "example": "Architecture Sync Meeting ABOUT Memory Optimization Topic",
    },
    "PREFERS": {
        "definition": "Associates a person with their personal preference or favored concept.",
        "example": "David PREFERS Fully Local Execution Concept",
    },
    "MENTIONS": {
        "definition": "Broad link indicating a note or conversation transcript references an entity.",
        "example": "Architecture Notes MENTIONS David",
    },
    "RELATED_TO": {
        "definition": "Generic associative fallback edge between any two entities.",
        "example": "Benchmark Ollama Task RELATED_TO Whisper OOM Issue",
    },
}


def serialize_type_definitions() -> Dict[str, Any]:
    """Serialize all node and relationship definitions into a structured dictionary."""
    node_labels = {}
    for label in sorted(ALLOWED_NODE_LABELS):
        info = NODE_DEFINITIONS.get(label, {})
        node_labels[label] = {
            "tier": info.get("tier", 2),
            "definition": info.get("definition", f"Entity node representing a {label}."),
            "example": info.get("example", ""),
        }

    rel_types = {}
    for rel_type in sorted(ALLOWED_RELATIONSHIP_TYPES):
        info = RELATIONSHIP_DEFINITIONS.get(rel_type, {})
        from_rule, to_rule = ALLOWED_DIRECTIONS.get(rel_type, ("any", "any"))
        rel_types[rel_type] = {
            "definition": info.get("definition", f"Relationship of type {rel_type}."),
            "example": info.get("example", ""),
            "allowed_directions": {
                "from": list(sorted(from_rule)) if isinstance(from_rule, (set, tuple, list)) else from_rule,
                "to": list(sorted(to_rule)) if isinstance(to_rule, (set, tuple, list)) else to_rule,
            },
        }

    return {
        "version": "1.0.0",
        "node_labels": node_labels,
        "relationship_types": rel_types,
        "properties_whitelist": sorted(ALLOWED_PROPERTIES),
    }


def export_type_definitions(target_path: Optional[Path] = None) -> Path:
    """Export type definitions JSON to knowledge_graph/contracts/type_definitions.json."""
    if target_path is None:
        target_path = Path(__file__).resolve().parent.parent / "contracts" / "type_definitions.json"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    data = serialize_type_definitions()
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return target_path


if __name__ == "__main__":
    out_file = export_type_definitions()
    print(f"Exported type definitions to {out_file}")
