"""Data models and validation for the Knowledge Graph schema."""

import logging
import re
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# Allowed node labels in the Knowledge Graph
NodeLabel = Literal[
    "Person",
    "Task",
    "Project",
    "Meeting",
    "Deadline",
    "Organization",
    "Location",
    "Event",
    "Concept",
    "Note",
]

ALLOWED_NODE_LABELS: Set[str] = {
    "Person",
    "Task",
    "Project",
    "Meeting",
    "Deadline",
    "Organization",
    "Location",
    "Event",
    "Concept",
    "Note",
}

# Allowed relationship types in the Knowledge Graph
RelationshipType = Literal[
    "ASSIGNED_TO",
    "PART_OF",
    "WORKS_ON",
    "ATTENDED",
    "DISCUSSED",
    "DUE_ON",
    "LOCATED_AT",
    "MEMBER_OF",
    "MENTIONS",
    "RELATED_TO",
]

ALLOWED_RELATIONSHIP_TYPES: Set[str] = {
    "ASSIGNED_TO",
    "PART_OF",
    "WORKS_ON",
    "ATTENDED",
    "DISCUSSED",
    "DUE_ON",
    "LOCATED_AT",
    "MEMBER_OF",
    "MENTIONS",
    "RELATED_TO",
}

# Allowed relationship directions: Type -> (FromLabel(s), ToLabel(s))
# None indicates any allowed NodeLabel is permitted.
ALLOWED_DIRECTIONS: Dict[
    str,
    Tuple[
        Optional[Union[str, Tuple[str, ...]]],
        Optional[Union[str, Tuple[str, ...]]],
    ],
] = {
    "ASSIGNED_TO": ("Task", "Person"),
    "PART_OF": ("Task", "Project"),
    "WORKS_ON": ("Person", "Project"),
    "ATTENDED": ("Person", "Meeting"),
    "DISCUSSED": ("Meeting", ("Project", "Task")),
    "DUE_ON": ("Task", "Deadline"),
    "LOCATED_AT": (("Meeting", "Event", "Task"), "Location"),
    "MEMBER_OF": ("Person", "Organization"),
    "MENTIONS": ("Note", None),
    "RELATED_TO": (None, None),
}

# Whitelist of allowed node and relationship property keys
ALLOWED_PROPERTIES: Set[str] = {
    "status",
    "priority",
    "date",
    "description",
    "label",
    "original_type",
    "kind",
}


def normalize_key(name: str) -> str:
    """Normalize an entity name into a unique key: strip, lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def is_valid_direction(rel_type: str, from_type: str, to_type: str) -> bool:
    """Check if the given from/to node types are valid for the relationship type."""
    if rel_type not in ALLOWED_DIRECTIONS:
        return False

    from_rule, to_rule = ALLOWED_DIRECTIONS[rel_type]

    if from_rule is not None:
        if isinstance(from_rule, tuple):
            if from_type not in from_rule:
                return False
        elif from_type != from_rule:
            return False

    if to_rule is not None:
        if isinstance(to_rule, tuple):
            if to_type not in to_rule:
                return False
        elif to_type != to_rule:
            return False

    return True


def validate_props_dict(props: Dict[str, Any]) -> Dict[str, Any]:
    """Validate property keys against whitelist and ensure values are scalar types."""
    invalid_keys = set(props.keys()) - ALLOWED_PROPERTIES
    if invalid_keys:
        raise ValueError(
            f"Invalid property keys: {sorted(invalid_keys)}. "
            f"Allowed properties are: {sorted(ALLOWED_PROPERTIES)}"
        )
    for k, v in props.items():
        if not isinstance(v, (str, int, float, bool)):
            raise ValueError(
                f"Invalid property value type for '{k}': {type(v).__name__}. "
                f"Allowed value types are str, int, float, bool only."
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
            raise ValueError("Entity name must be non-empty")
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


class Relationship(BaseModel):
    """A directed edge between two entities with open fallback normalization."""

    model_config = ConfigDict(populate_by_name=True)

    from_entity: EntityRef = Field(alias="from")
    type: RelationshipType
    to_entity: EntityRef = Field(alias="to")
    props: Dict[str, Any] = Field(default_factory=dict)

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
            elif isinstance(from_data, EntityRef):
                from_type = from_data.type
            elif isinstance(from_data, Entity):
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
            elif isinstance(to_data, EntityRef):
                to_type = to_data.type
            elif isinstance(to_data, Entity):
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
    entities: List[Entity] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
