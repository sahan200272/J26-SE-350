"""Adapters for ingesting entity and relationship triples into Payload format."""

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from graph_schema.models import (
    ALLOWED_DIRECTIONS,
    ALLOWED_NODE_LABELS,
    Entity,
    EntityRef,
    Payload,
    Relationship,
    normalize_key,
)

logger = logging.getLogger(__name__)


def get_inferred_labels(predicate: str) -> Optional[Tuple[str, str]]:
    """Infer (from_label, to_label) when predicate direction is unambiguous.

    Returns:
        Tuple of (from_label, to_label) if exactly one from_label and one to_label
        are allowed by ALLOWED_DIRECTIONS, otherwise None.
    """
    if predicate not in ALLOWED_DIRECTIONS:
        return None

    from_rule, to_rule = ALLOWED_DIRECTIONS[predicate]
    if (
        isinstance(from_rule, (set, tuple, list))
        and len(from_rule) == 1
        and isinstance(to_rule, (set, tuple, list))
        and len(to_rule) == 1
    ):
        from_label = next(iter(from_rule))
        to_label = next(iter(to_rule))
        return (from_label, to_label)

    return None


def triples_to_payload(
    triples: Sequence[Any],
    source: str,
    timestamp: Optional[str] = None,
) -> Payload:
    """Convert a sequence of triples into a validated Payload.

    Each triple may be:
    (a) a typed dict:
        {"subject": {"name": ..., "type": ...}, "predicate": ..., "object": {"name": ..., "type": ...}}
        with optional "op", "confidence", "props" on the triple or endpoints.
    (b) an untyped list/tuple:
        [subject_name, predicate, object_name]

    For untyped triples, node labels are inferred from ALLOWED_DIRECTIONS when unambiguous.
    If ambiguous or unknown, both endpoints fall back to 'Concept' and the relationship
    falls back to 'RELATED_TO' with props["label"] = original predicate.

    Entities from endpoints are deduplicated, preserving optional properties and ops.
    """
    entities_map: Dict[Tuple[str, str], Entity] = {}
    relationships: List[Relationship] = []

    for item in triples:
        if isinstance(item, (list, tuple)):
            if len(item) < 3:
                logger.warning("Skipping malformed untyped triple (length < 3): %s", item)
                continue
            subj_name = str(item[0]).strip()
            predicate = str(item[1]).strip()
            obj_name = str(item[2]).strip()

            inferred = get_inferred_labels(predicate)
            if inferred is not None:
                subj_type, obj_type = inferred
                rel_type = predicate
                rel_props: Dict[str, Any] = {}
            else:
                logger.warning(
                    "Predicate '%s' is ambiguous or unknown; falling back to Concept nodes and RELATED_TO.",
                    predicate,
                )
                subj_type = "Concept"
                obj_type = "Concept"
                rel_type = "RELATED_TO"
                rel_props = {"label": predicate}

            subj_entity = Entity(type=subj_type, name=subj_name)
            obj_entity = Entity(type=obj_type, name=obj_name)

            rel = Relationship(
                from_entity=EntityRef(type=subj_entity.type, name=subj_entity.name),
                type=rel_type,
                to_entity=EntityRef(type=obj_entity.type, name=obj_entity.name),
                props=rel_props,
                op="add",
            )
            relationships.append(rel)

        elif isinstance(item, dict):
            subj_data = item.get("subject")
            predicate = str(item.get("predicate", "")).strip()
            obj_data = item.get("object")

            if not isinstance(subj_data, dict) or not isinstance(obj_data, dict):
                logger.warning("Skipping malformed typed triple: %s", item)
                continue

            subj_name = str(subj_data.get("name", "")).strip()
            subj_type = str(subj_data.get("type", "Concept")).strip()
            subj_props = dict(subj_data.get("props") or {})
            subj_op = subj_data.get("op", "add")

            obj_name = str(obj_data.get("name", "")).strip()
            obj_type = str(obj_data.get("type", "Concept")).strip()
            obj_props = dict(obj_data.get("props") or {})
            obj_op = obj_data.get("op", "add")

            rel_props = dict(item.get("props") or {})
            if "confidence" in item and item["confidence"] is not None:
                rel_props["confidence"] = item["confidence"]
            rel_op = item.get("op", "add")

            subj_entity = Entity(
                type=subj_type,
                name=subj_name,
                props=subj_props,
                op=subj_op,
            )
            obj_entity = Entity(
                type=obj_type,
                name=obj_name,
                props=obj_props,
                op=obj_op,
            )

            rel = Relationship(
                from_entity=EntityRef(type=subj_entity.type, name=subj_entity.name),
                type=predicate,
                to_entity=EntityRef(type=obj_entity.type, name=obj_entity.name),
                props=rel_props,
                op=rel_op,
            )
            relationships.append(rel)
        else:
            logger.warning("Skipping unsupported triple item type '%s': %s", type(item).__name__, item)
            continue

        # Deduplicate and register endpoints
        for entity in (subj_entity, obj_entity):
            entity_key = (entity.type, normalize_key(entity.name))
            if entity_key in entities_map:
                existing = entities_map[entity_key]
                if entity.props:
                    merged_props = dict(existing.props)
                    merged_props.update(entity.props)
                    existing.props = merged_props
                if entity.op != "add":
                    existing.op = entity.op
            else:
                entities_map[entity_key] = entity

    return Payload(
        source=source,
        timestamp=timestamp,
        entities=list(entities_map.values()),
        relationships=relationships,
    )
