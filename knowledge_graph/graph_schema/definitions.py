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

TIER_1_RELATIONSHIPS = {
    "ASSIGNED_TO",
    "PART_OF",
    "DUE_ON",
    "ATTENDED",
    "ABSENT_FROM",
    "DECIDED",
    "RAISED",
    "BLOCKED_BY",
    "DISCUSSED",
    "WORKS_ON",
    "MEMBER_OF",
    "REQUESTED_BY",
    "LOCATED_AT",
    "FRIEND_OF",
    "FAMILY_OF",
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
        "definition": "A physical room, office, city, or virtual platform where an event or person resides.",
        "example": "Conference Room A / Brooklyn, NY",
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
        "definition": "A calendar occurrence, party, public demo, release date, or personal milestone event.",
        "example": "Birthday Party / Private Beta Release Demo",
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
    "Item": {
        "tier": 2,
        "definition": "A physical product, grocery, purchased good, device, or tangible physical object.",
        "example": "Oat milk / MacBook Pro / Sony WH-1000XM5 headphones",
    },
}

RELATIONSHIP_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Tier 1 Relationships (15 most common for Agentic Core)
    "ASSIGNED_TO": {
        "tier": 1,
        "definition": "Assigns responsibility for completing a task to a person.",
        "example": "Benchmark Ollama ASSIGNED_TO David",
    },
    "PART_OF": {
        "tier": 1,
        "definition": "Subsumption link between tasks or projects.",
        "example": "Benchmark Ollama PART_OF Local Voice AI Assistant",
    },
    "DUE_ON": {
        "tier": 1,
        "definition": "Associates a task, project, or goal with its target deadline.",
        "example": "Benchmark Ollama DUE_ON 2026-10-18",
    },
    "ATTENDED": {
        "tier": 1,
        "definition": "Records that a person was present at a meeting or event.",
        "example": "Sarah ATTENDED Sprint 14 Architecture Sync",
    },
    "ABSENT_FROM": {
        "tier": 1,
        "definition": "Records that an expected person was absent from a meeting or event.",
        "example": "Alex ABSENT_FROM Sprint 14 Architecture Sync",
    },
    "DECIDED": {
        "tier": 1,
        "definition": "Connects a person to a formal decision they made or championed.",
        "example": "Sarah DECIDED Adopt Neo4j 5",
    },
    "RAISED": {
        "tier": 1,
        "definition": "Connects a person to an issue, blocker, or open question they voiced.",
        "example": "David RAISED Whisper OOM Crash Issue",
    },
    "BLOCKED_BY": {
        "tier": 1,
        "definition": "Indicates a task or project is actively blocked by an issue or task.",
        "example": "Benchmark Ollama BLOCKED_BY OOM Crash Issue",
    },
    "DISCUSSED": {
        "tier": 1,
        "definition": "Broad link from a meeting to any entity or topic brought up in conversation.",
        "example": "Architecture Sync Meeting DISCUSSED Ollama Memory Consumption",
    },
    "WORKS_ON": {
        "tier": 1,
        "definition": "Associates a person with a project they contribute to.",
        "example": "David WORKS_ON Local Voice AI Assistant",
    },
    "MEMBER_OF": {
        "tier": 1,
        "definition": "Indicates a person belongs to a team or organization.",
        "example": "Sarah MEMBER_OF Core AI Pipeline Team",
    },
    "REQUESTED_BY": {
        "tier": 1,
        "definition": "Identifies the person who asked for or requested a task.",
        "example": "Benchmark Ollama REQUESTED_BY Sarah",
    },
    "LOCATED_AT": {
        "tier": 1,
        "definition": "Associates a meeting, event, or task with its physical or virtual location.",
        "example": "Architecture Sync LOCATED_AT Conference Room A",
    },
    "FRIEND_OF": {
        "tier": 1,
        "definition": "Indicates interpersonal friendship between two people.",
        "example": "David FRIEND_OF Alex",
    },
    "FAMILY_OF": {
        "tier": 1,
        "definition": "Indicates familial kinship relationship between two people (e.g. parent, sibling).",
        "example": "Sarah FAMILY_OF Maya (kind='sister')",
    },
    # Tier 2 Relationships (30 supporting/extended types)
    "LEADS": {
        "tier": 2,
        "definition": "Indicates a person directs, facilitates, or leads a team, project, or meeting.",
        "example": "Sarah LEADS Sprint 14 Architecture Sync",
    },
    "REPORTS_TO": {
        "tier": 2,
        "definition": "Indicates an organizational reporting relationship between people.",
        "example": "David REPORTS_TO Sarah",
    },
    "COLLABORATES_WITH": {
        "tier": 2,
        "definition": "Indicates direct working partnership between two people.",
        "example": "Sarah COLLABORATES_WITH David",
    },
    "DEPENDS_ON": {
        "tier": 2,
        "definition": "Indicates a task or project requires another task or project to complete first.",
        "example": "Integration Testing DEPENDS_ON Benchmark Ollama",
    },
    "FOLLOW_UP_OF": {
        "tier": 2,
        "definition": "Indicates a task or meeting was created as a direct next step from a prior item.",
        "example": "Memory Tuning Task FOLLOW_UP_OF Architecture Sync Meeting",
    },
    "SUPPORTS": {
        "tier": 2,
        "definition": "Connects an actionable task or project to the strategic goal it advances.",
        "example": "Benchmark Ollama SUPPORTS Sub-500ms Latency Goal",
    },
    "SCHEDULED_ON": {
        "tier": 2,
        "definition": "Specifies the scheduled date or deadline for a meeting or event.",
        "example": "Architecture Sync SCHEDULED_ON 2026-10-18",
    },
    "CREATED_IN": {
        "tier": 2,
        "definition": "Records the meeting or conversation context in which an item or decision originated.",
        "example": "Adopt Neo4j Decision CREATED_IN Architecture Sync Meeting",
    },
    "PROPOSED": {
        "tier": 2,
        "definition": "Connects a person to an idea or exploratory suggestion they submitted.",
        "example": "David PROPOSED SQLite Caching Idea",
    },
    "HAS_ISSUE": {
        "tier": 2,
        "definition": "Links a project or task directly to an identified issue or blocker.",
        "example": "Voice Assistant Project HAS_ISSUE Whisper OOM Crash",
    },
    "RESOLVES": {
        "tier": 2,
        "definition": "Indicates that completing a task or executing a decision resolves an issue.",
        "example": "Adopt Quantized Model Decision RESOLVES Whisper OOM Crash",
    },
    "ANSWERS": {
        "tier": 2,
        "definition": "Links a decision or note that answers an open question.",
        "example": "Adopt Quantized Model Decision ANSWERS Which LLM Model Question",
    },
    "SUPERSEDES": {
        "tier": 2,
        "definition": "Indicates a new decision replaces, updates, or invalidates an earlier decision.",
        "example": "Adopt Neo4j Decision SUPERSEDES Use Raw SQLite Decision",
    },
    "AGREES_WITH": {
        "tier": 2,
        "definition": "Records agreement by a person with an idea, decision, or colleague.",
        "example": "Sarah AGREES_WITH SQLite Caching Proposal",
    },
    "DISAGREES_WITH": {
        "tier": 2,
        "definition": "Records dissent or objection by a person to an idea, decision, or colleague.",
        "example": "Sarah DISAGREES_WITH Cloud Sync Idea",
    },
    "REFERENCES": {
        "tier": 2,
        "definition": "Cites or refers to an external document, specification, or PRD.",
        "example": "Adopt Neo4j Decision REFERENCES RFC-204 Document",
    },
    "USES": {
        "tier": 2,
        "definition": "Associates a project, task, or team with a software tool or platform.",
        "example": "Core AI Pipeline Team USES Neo4j 5",
    },
    "HAS_METRIC": {
        "tier": 2,
        "definition": "Connects an entity to an observed or target quantitative metric.",
        "example": "Voice Assistant Project HAS_METRIC Sub-500ms Latency Metric",
    },
    "ABOUT": {
        "tier": 2,
        "definition": "Specifies the subject matter topic of a note, decision, idea, or meeting.",
        "example": "Architecture Sync Meeting ABOUT Memory Optimization Topic",
    },
    "PREFERS": {
        "tier": 2,
        "definition": "Associates a person with their personal preference or favored concept.",
        "example": "David PREFERS Fully Local Execution Concept",
    },
    "MENTIONS": {
        "tier": 2,
        "definition": "Broad link indicating a note or conversation transcript references an entity.",
        "example": "Architecture Notes MENTIONS David",
    },
    "RELATED_TO": {
        "tier": 2,
        "definition": "Generic associative fallback edge between any two entities.",
        "example": "Benchmark Ollama Task RELATED_TO Whisper OOM Issue",
    },
    "PARTNER_OF": {
        "tier": 2,
        "definition": "Indicates a romantic, marital, or domestic partnership between two people.",
        "example": "Sarah PARTNER_OF John",
    },
    "WORKS_AT": {
        "tier": 2,
        "definition": "Associates an employed person with their workplace or employer organization.",
        "example": "David WORKS_AT InnoTech Labs",
    },
    "LIVES_IN": {
        "tier": 2,
        "definition": "Indicates the home city, neighborhood, or residential location of a person.",
        "example": "Sarah LIVES_IN Brooklyn",
    },
    "LIKES": {
        "tier": 2,
        "definition": "Expresses a positive opinion, affinity, or interest of a person toward any entity.",
        "example": "Sarah LIKES Sony Headphones",
    },
    "DISLIKES": {
        "tier": 2,
        "definition": "Expresses a negative opinion, aversion, or disinterest of a person toward any entity.",
        "example": "David DISLIKES Loud Offices",
    },
    "ALIAS_OF": {
        "tier": 2,
        "definition": "Links an entity variant or nickname to its canonical entity of the SAME label.",
        "example": "Sarah ALIAS_OF Sarah Perera",
    },
    "OWNS": {
        "tier": 2,
        "definition": "Indicates ownership or possession of an item, document, or tool.",
        "example": "David OWNS MacBook Pro (Item)",
    },
    "PLANS": {
        "tier": 2,
        "definition": "Indicates an intended future commitment, activity, or personal schedule of a person.",
        "example": "Sarah PLANS Birthday Party (Event)",
    },
}

PROPERTY_DOCUMENTATION: Dict[str, Dict[str, Any]] = {
    "status": {"type": "scalar", "description": "Lifecycle state (e.g. open, in_progress, resolved)."},
    "priority": {"type": "scalar", "description": "Priority ranking (low, medium, high, critical)."},
    "progress": {"type": "scalar", "description": "Completion indicator or percentage."},
    "date": {"type": "scalar", "description": "ISO date string (YYYY-MM-DD)."},
    "time": {"type": "scalar", "description": "Time string (HH:MM:SS)."},
    "duration": {"type": "scalar", "description": "Meeting or activity duration string."},
    "recurrence": {"type": "scalar", "description": "Recurrence frequency string."},
    "value": {"type": "scalar", "description": "Numeric parameter or score."},
    "unit": {"type": "scalar", "description": "Measurement unit string."},
    "title": {"type": "scalar", "description": "Formal document or role title."},
    "severity": {"type": "scalar", "description": "Severity assessment (e.g. blocker)."},
    "kind": {"type": "scalar", "description": "Kinship or sub-category classifier (e.g. 'sister', 'mother')."},
    "description": {"type": "scalar", "description": "Detailed explanation or text description."},
    "rationale": {"type": "scalar", "description": "Reasoning behind a decision."},
    "quote": {"type": "scalar", "description": "Verbatim quote excerpt."},
    "timestamp": {"type": "scalar", "description": "ISO timestamp of statement."},
    "confidence": {"type": "float [0.0 - 1.0]", "description": "Extraction certainty score (e.g. 'Maybe Friday' -> confidence: 0.5)."},
    "label": {"type": "scalar", "description": "Original relationship type when converted to RELATED_TO."},
    "original_type": {"type": "scalar", "description": "Original entity type when converted to Concept."},
    "age": {"type": "int/scalar", "description": "Age of a person in years."},
    "aliases": {"type": "list[str]", "description": "List of alternate names or nicknames."},
    "email": {"type": "str", "description": "Email address string."},
    "phone": {"type": "str", "description": "Phone number string."},
    "birthday": {"type": "str", "description": "Birth date stored as ISO string (do not parse)."},
    "sensitivity": {"type": "str ('normal' | 'private')", "description": "Privacy classification flag."},
    "speaker": {"type": "str", "description": "Speaker identity in multi-speaker audio."},
}

LAYER_C_SIGNALS: Dict[str, Dict[str, Any]] = {
    "op": {
        "values": ["add", "update", "retract"],
        "default": "add",
        "description": "Operation flag indicating lifecycle signal from conversation.",
        "examples": {
            "add": "Create entity or relationship if missing (default behavior).",
            "update": "'No, I meant Tuesday' -> op: update (correction trigger for conflict resolution).",
            "retract": "'Cancel the meeting' -> op: retract (cancellation / removal trigger).",
        },
    },
    "confidence": {
        "description": "Uncertainty quantification.",
        "example": "'Maybe Friday' -> confidence: 0.5",
    },
    "alias_disambiguation": {
        "description": "Entity resolution via ALIAS_OF edge.",
        "example": "'Sarah is also called Sarah Perera' -> Person('Sarah') -[:ALIAS_OF]-> Person('Sarah Perera')",
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
            "tier": info.get("tier", 1 if rel_type in TIER_1_RELATIONSHIPS else 2),
            "definition": info.get("definition", f"Relationship of type {rel_type}."),
            "example": info.get("example", ""),
            "allowed_directions": {
                "from": list(sorted(from_rule)) if isinstance(from_rule, (set, tuple, list)) else from_rule,
                "to": list(sorted(to_rule)) if isinstance(to_rule, (set, tuple, list)) else to_rule,
            },
        }

    return {
        "version": "1.1.0",
        "node_labels": node_labels,
        "relationship_types": rel_types,
        "properties": PROPERTY_DOCUMENTATION,
        "layer_c_signals": LAYER_C_SIGNALS,
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
