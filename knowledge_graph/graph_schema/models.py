"""Data models and validation for the Knowledge Graph schema."""

import logging
import re
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Tuple,
    Union,
    get_args,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Node labels (23)
NodeLabel = Literal[
    "Person",
    "Team",
    "Organization",
    "Project",
    "Task",
    "Goal",
    "Meeting",
    "Decision",
    "Issue",
    "Question",
    "Idea",
    "Document",
    "Tool",
    "Metric",
    "Deadline",
    "Event",
    "Location",
    "Topic",
    "Concept",
    "Preference",
    "Note",
    "Conversation",
    "Item",
]

ALLOWED_NODE_LABELS: Set[str] = set(get_args(NodeLabel))

# Relationship types (45)
RelationshipType = Literal[
    # Work & Meeting Layer (35)
    "MEMBER_OF",
    "LEADS",
    "REPORTS_TO",
    "COLLABORATES_WITH",
    "ATTENDED",
    "ABSENT_FROM",
    "ASSIGNED_TO",
    "REQUESTED_BY",
    "WORKS_ON",
    "PART_OF",
    "DEPENDS_ON",
    "BLOCKED_BY",
    "FOLLOW_UP_OF",
    "SUPPORTS",
    "DUE_ON",
    "SCHEDULED_ON",
    "LOCATED_AT",
    "CREATED_IN",
    "DISCUSSED",
    "DECIDED",
    "RAISED",
    "PROPOSED",
    "HAS_ISSUE",
    "RESOLVES",
    "ANSWERS",
    "SUPERSEDES",
    "AGREES_WITH",
    "DISAGREES_WITH",
    "REFERENCES",
    "USES",
    "HAS_METRIC",
    "ABOUT",
    "PREFERS",
    "MENTIONS",
    "RELATED_TO",
    # Personal & Everyday Layer (10)
    "FAMILY_OF",
    "PARTNER_OF",
    "FRIEND_OF",
    "WORKS_AT",
    "LIVES_IN",
    "LIKES",
    "DISLIKES",
    "ALIAS_OF",
    "OWNS",
    "PLANS",
]

ALLOWED_RELATIONSHIP_TYPES: Set[str] = set(get_args(RelationshipType))

# Operation types for Layer C conversation signals
OpType = Literal["add", "update", "retract"]

# Allowed relationship directions: Type -> (FromLabel(s), ToLabel(s))
# A rule can be a set of allowed NodeLabels, or "any" allowing any NodeLabel.
ALLOWED_DIRECTIONS: Dict[
    str,
    Tuple[
        Union[Set[str], Literal["any"]],
        Union[Set[str], Literal["any"]],
    ],
] = {
    # Layer A: Work & Meeting
    "MEMBER_OF": ({"Person"}, {"Team", "Organization"}),
    "LEADS": ({"Person"}, {"Team", "Project", "Meeting"}),
    "REPORTS_TO": ({"Person"}, {"Person"}),
    "COLLABORATES_WITH": ({"Person"}, {"Person"}),
    "ATTENDED": ({"Person"}, {"Meeting", "Event"}),
    "ABSENT_FROM": ({"Person"}, {"Meeting", "Event"}),
    "ASSIGNED_TO": ({"Task"}, {"Person"}),
    "REQUESTED_BY": ({"Task"}, {"Person"}),
    "WORKS_ON": ({"Person"}, {"Project"}),
    "PART_OF": ({"Task", "Project"}, {"Project", "Task"}),
    "DEPENDS_ON": ({"Task", "Project"}, {"Task", "Project"}),
    "BLOCKED_BY": ({"Task", "Project"}, {"Issue", "Task"}),
    "FOLLOW_UP_OF": ({"Task", "Meeting"}, {"Task", "Meeting"}),
    "SUPPORTS": ({"Task", "Project"}, {"Goal"}),
    "DUE_ON": ({"Task", "Project", "Goal"}, {"Deadline"}),
    "SCHEDULED_ON": ({"Meeting", "Event"}, {"Deadline"}),
    "LOCATED_AT": ({"Meeting", "Event", "Task"}, {"Location"}),
    "CREATED_IN": (
        {"Task", "Decision", "Issue", "Question", "Idea", "Note", "Document"},
        {"Meeting", "Conversation"},
    ),
    "DISCUSSED": ({"Meeting"}, "any"),
    "DECIDED": ({"Person"}, {"Decision"}),
    "RAISED": ({"Person"}, {"Issue", "Question"}),
    "PROPOSED": ({"Person"}, {"Idea"}),
    "HAS_ISSUE": ({"Project", "Task"}, {"Issue"}),
    "RESOLVES": ({"Task", "Decision"}, {"Issue"}),
    "ANSWERS": ({"Decision", "Note"}, {"Question"}),
    "SUPERSEDES": ({"Decision"}, {"Decision"}),
    "AGREES_WITH": ({"Person"}, {"Idea", "Decision", "Person"}),
    "DISAGREES_WITH": ({"Person"}, {"Idea", "Decision", "Person"}),
    "REFERENCES": (
        {"Meeting", "Task", "Project", "Note", "Decision"},
        {"Document"},
    ),
    "USES": ({"Project", "Task", "Team"}, {"Tool"}),
    "HAS_METRIC": (
        {"Project", "Task", "Goal", "Meeting", "Decision"},
        {"Metric"},
    ),
    "ABOUT": (
        {"Note", "Decision", "Idea", "Meeting", "Conversation"},
        {"Topic"},
    ),
    "PREFERS": ({"Person"}, {"Preference", "Concept"}),
    "MENTIONS": ({"Note", "Conversation"}, "any"),
    "RELATED_TO": ("any", "any"),
    # Layer B: Personal & Social Life
    "FAMILY_OF": ({"Person"}, {"Person"}),
    "PARTNER_OF": ({"Person"}, {"Person"}),
    "FRIEND_OF": ({"Person"}, {"Person"}),
    "WORKS_AT": ({"Person"}, {"Organization"}),
    "LIVES_IN": ({"Person"}, {"Location"}),
    "LIKES": ({"Person"}, "any"),
    "DISLIKES": ({"Person"}, "any"),
    "ALIAS_OF": ("any", "any"),  # Must match same label on both ends
    "OWNS": ({"Person", "Team", "Organization"}, {"Item", "Document", "Tool"}),
    "PLANS": ({"Person"}, {"Event", "Task", "Meeting"}),
}

# Whitelist of allowed node and relationship property keys
ALLOWED_PROPERTIES: Set[str] = {
    "status",
    "priority",
    "progress",
    "date",
    "time",
    "duration",
    "recurrence",
    "value",
    "unit",
    "title",
    "severity",
    "kind",
    "description",
    "rationale",
    "quote",
    "timestamp",
    "confidence",
    "label",
    "original_type",
    "age",
    "aliases",
    "email",
    "phone",
    "birthday",
    "sensitivity",
    "speaker",
}

# Property value constraints & case-insensitive synonyms (RP-25)
ALLOWED_PRIORITIES: Set[str] = {"low", "medium", "high", "urgent"}
PRIORITY_SYNONYMS: Dict[str, str] = {
    "critical": "urgent",
    "asap": "urgent",
    "immediately": "urgent",
    "important": "high",
    "normal": "medium",
    "ok": "medium",
    "moderate": "medium",
    "minor": "low",
    "whenever": "low",
    "optional": "low",
}

ALLOWED_SEVERITIES: Set[str] = {"low", "medium", "high", "critical"}
SEVERITY_SYNONYMS: Dict[str, str] = {
    "blocker": "critical",
    "major": "high",
    "minor": "low",
    "normal": "medium",
}

ALLOWED_STATUSES: Set[str] = {
    "open",
    "in progress",
    "blocked",
    "done",
    "cancelled",
    "planned",
    "active",
    "agreed",
    "superseded",
    "answered",
}
STATUS_SYNONYMS: Dict[str, str] = {
    "completed": "done",
    "complete": "done",
    "finished": "done",
    "in-progress": "in progress",
    "in_progress": "in progress",
    "ongoing": "in progress",
    "started": "in progress",
    "wip": "in progress",
    "canceled": "cancelled",
    "dropped": "cancelled",
    "called off": "cancelled",
    "pending": "open",
    "todo": "open",
    "to do": "open",
    "new": "open",
    "waiting": "blocked",
    "stuck": "blocked",
    "decided": "agreed",
    "approved": "agreed",
    "confirmed": "agreed",
    "accepted": "agreed",
    "resolved": "done",
    "closed": "done",
    "solved": "done",
}

# Relationship cardinality & symmetry constants (RP-25)
SINGLE_VALUED_RELATIONSHIPS: Set[str] = {"DUE_ON", "SCHEDULED_ON", "LIVES_IN"}
SYMMETRIC_RELATIONSHIPS: Set[str] = {"FRIEND_OF", "PARTNER_OF", "COLLABORATES_WITH"}

SUPPORTED_SCHEMA_VERSION: str = "1.0"


def canonical_pair(rel_type: str, key_a: str, key_b: str) -> Tuple[str, str]:
    """Return keys in sorted order for symmetric relationship types, unchanged otherwise."""
    if rel_type in SYMMETRIC_RELATIONSHIPS:
        return tuple(sorted((key_a, key_b)))
    return (key_a, key_b)


def is_iso_date(value: str) -> bool:
    """Check if value is an ISO date formatted as YYYY-MM-DD."""
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", stripped):
        return False
    try:
        from datetime import date
        date.fromisoformat(stripped)
        return True
    except ValueError:
        return False


def normalize_key(name: str) -> str:
    """Normalize an entity name into a unique key: strip, lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def is_valid_direction(rel_type: str, from_type: str, to_type: str) -> bool:
    """Check if the given from/to node types are valid for the relationship type."""
    if rel_type not in ALLOWED_RELATIONSHIP_TYPES:
        return False

    if rel_type == "ALIAS_OF":
        # ALIAS_OF requires both ends to have the exact same label
        return from_type in ALLOWED_NODE_LABELS and from_type == to_type

    if rel_type not in ALLOWED_DIRECTIONS:
        return False

    from_rule, to_rule = ALLOWED_DIRECTIONS[rel_type]

    # Validate from_type
    if from_rule != "any":
        if isinstance(from_rule, (set, tuple, list)):
            if from_type not in from_rule:
                return False
        elif from_type != from_rule:
            return False

    # Validate to_type
    if to_rule != "any":
        if isinstance(to_rule, (set, tuple, list)):
            if to_type not in to_rule:
                return False
        elif to_type != to_rule:
            return False

    return True


def validate_props_dict(props: Dict[str, Any]) -> Dict[str, Any]:
    """Validate property keys against whitelist and ensure values meet type constraints."""
    props = dict(props)
    invalid_keys = set(props.keys()) - ALLOWED_PROPERTIES
    if invalid_keys:
        raise ValueError(
            f"Invalid property keys: {sorted(invalid_keys)}. "
            f"Allowed properties are: {sorted(ALLOWED_PROPERTIES)}"
        )

    # Normalize or drop priority, severity, status
    property_mappings = [
        ("priority", ALLOWED_PRIORITIES, PRIORITY_SYNONYMS),
        ("severity", ALLOWED_SEVERITIES, SEVERITY_SYNONYMS),
        ("status", ALLOWED_STATUSES, STATUS_SYNONYMS),
    ]
    for prop_key, allowed_vals, synonyms in property_mappings:
        if prop_key in props:
            val = props[prop_key]
            if isinstance(val, str):
                normalized = val.strip().lower()
                if normalized in allowed_vals:
                    props[prop_key] = normalized
                elif normalized in synonyms:
                    props[prop_key] = synonyms[normalized]
                else:
                    logger.warning(
                        "Unknown %s '%s' dropped.",
                        prop_key,
                        val,
                    )
                    props.pop(prop_key)
            else:
                logger.warning(
                    "Unknown %s '%s' dropped.",
                    prop_key,
                    val,
                )
                props.pop(prop_key)

    for k, v in props.items():
        if k == "aliases":
            if not isinstance(v, list):
                raise ValueError(
                    "Invalid property value for 'aliases': must be a list of non-empty strings."
                )
            for item in v:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"Invalid alias '{item}' in 'aliases': must be a non-empty string."
                    )
        else:
            if not isinstance(v, (str, int, float, bool)):
                raise ValueError(
                    f"Invalid property value type for '{k}': {type(v).__name__}. "
                    f"Allowed value types are str, int, float, bool only."
                )

        if k == "sensitivity":
            if v not in ("normal", "private"):
                raise ValueError(
                    f"Invalid sensitivity '{v}'. Must be 'normal' or 'private'."
                )

        if k == "confidence":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not (0.0 <= float(v) <= 1.0):
                raise ValueError(
                    f"Invalid confidence '{v}'. Must be a number between 0.0 and 1.0."
                )

    return props


class EntityRef(BaseModel):
    """Reference to a node entity by its type and display name."""

    type: NodeLabel
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("EntityRef name must be non-empty")
        return stripped

    @model_validator(mode="before")
    @classmethod
    def normalize_ref(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_type = data.get("type")
            if raw_type is not None and raw_type not in ALLOWED_NODE_LABELS:
                logger.warning(
                    "Unknown entity reference type '%s' normalized to 'Concept'.",
                    raw_type,
                )
                data["type"] = "Concept"
        return data


class Entity(BaseModel):
    """A graph entity node definition with optional whitelisted properties."""

    type: NodeLabel
    name: str
    props: Dict[str, Any] = Field(default_factory=dict)
    op: OpType = "add"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Entity name must be non-empty")
        return stripped

    @field_validator("props")
    @classmethod
    def validate_props(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return validate_props_dict(v)

    @model_validator(mode="before")
    @classmethod
    def normalize_entity(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_type = data.get("type")
            if raw_type is not None and raw_type not in ALLOWED_NODE_LABELS:
                logger.warning(
                    "Unknown entity type '%s' normalized to 'Concept'.",
                    raw_type,
                )
                props = data.get("props")
                if props is None or not isinstance(props, dict):
                    props = {}
                else:
                    props = dict(props)
                props["original_type"] = str(raw_type)
                data["type"] = "Concept"
                data["props"] = props
        return data

    @model_validator(mode="after")
    def validate_deadline_entity(self) -> "Entity":
        if self.type == "Deadline" and not is_iso_date(self.name):
            logger.warning(
                "Deadline entity name '%s' is not an ISO date (YYYY-MM-DD).",
                self.name,
            )
        return self


class Relationship(BaseModel):
    """A directed edge between two entities with open fallback normalization."""

    model_config = ConfigDict(populate_by_name=True)

    from_entity: EntityRef = Field(alias="from")
    type: RelationshipType
    to_entity: EntityRef = Field(alias="to")
    props: Dict[str, Any] = Field(default_factory=dict)
    op: OpType = "add"

    @field_validator("props")
    @classmethod
    def validate_props(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        return validate_props_dict(v)

    @model_validator(mode="before")
    @classmethod
    def normalize_relationship(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            from_data = data.get("from") if "from" in data else data.get("from_entity")
            to_data = data.get("to") if "to" in data else data.get("to_entity")
            raw_type = data.get("type")
            props = data.get("props")
            if props is None or not isinstance(props, dict):
                props = {}
            else:
                props = dict(props)

            # Determine from_type
            if isinstance(from_data, dict):
                from_type = from_data.get("type")
                if from_type not in ALLOWED_NODE_LABELS:
                    from_data = dict(from_data)
                    from_data["type"] = "Concept"
                    if "from" in data:
                        data["from"] = from_data
                    else:
                        data["from_entity"] = from_data
                    from_type = "Concept"
            elif isinstance(from_data, (EntityRef, Entity)):
                from_type = from_data.type
            else:
                from_type = None

            # Determine to_type
            if isinstance(to_data, dict):
                to_type = to_data.get("type")
                if to_type not in ALLOWED_NODE_LABELS:
                    to_data = dict(to_data)
                    to_data["type"] = "Concept"
                    if "to" in data:
                        data["to"] = to_data
                    else:
                        data["to_entity"] = to_data
                    to_type = "Concept"
            elif isinstance(to_data, (EntityRef, Entity)):
                to_type = to_data.type
            else:
                to_type = None

            # Check if relationship type is unknown or direction is invalid
            if raw_type is not None and from_type is not None and to_type is not None:
                if raw_type not in ALLOWED_RELATIONSHIP_TYPES or not is_valid_direction(
                    raw_type, from_type, to_type
                ):
                    logger.warning(
                        "Relationship type '%s' with direction '%s' -> '%s' normalized to 'RELATED_TO'.",
                        raw_type,
                        from_type,
                        to_type,
                    )
                    props["label"] = str(raw_type)
                    data["type"] = "RELATED_TO"
                    data["props"] = props
            elif raw_type is not None and raw_type not in ALLOWED_RELATIONSHIP_TYPES:
                logger.warning(
                    "Unknown relationship type '%s' normalized to 'RELATED_TO'.",
                    raw_type,
                )
                props["label"] = str(raw_type)
                data["type"] = "RELATED_TO"
                data["props"] = props

        return data


class Payload(BaseModel):
    """Input payload containing extracted entities and relationships from voice conversations."""

    source: str
    schema_version: Optional[str] = "1.0"
    timestamp: Optional[str] = None
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, v: Optional[str]) -> str:
        if v is None:
            return "1.0"
        v_str = str(v).strip()
        major = v_str.split(".")[0]
        supported_major = SUPPORTED_SCHEMA_VERSION.split(".")[0]
        if major != supported_major:
            logger.warning(
                "Payload schema_version '%s' has major version '%s' differing from supported version '%s'.",
                v_str,
                major,
                SUPPORTED_SCHEMA_VERSION,
            )
        return v_str
