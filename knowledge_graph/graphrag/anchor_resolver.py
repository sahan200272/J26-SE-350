"""Query intent classification and seed anchor entity resolution."""

import re
from typing import Any, Dict, List, Optional, Set
from rapidfuzz.fuzz import token_sort_ratio

from graph_schema.definitions import TIER_1_RELATIONSHIPS
from graph_schema.models import normalize_key
from graphrag.models import AnchorMatch, QueryIntent

# Intent detection keyword rules
INTENT_KEYWORDS: Dict[QueryIntent, List[str]] = {
    "blocker_chain": [
        "block",
        "blocked",
        "blocker",
        "blockers",
        "blocking",
        "issue",
        "issues",
        "obstacle",
        "obstacles",
        "impediment",
        "impediments",
        "stuck",
        "trouble",
        "bug",
        "bugs",
        "problem",
        "problems",
        "failing",
        "preventing",
        "bottleneck",
        "bottlenecks",
        "why is",
        "what's blocking",
        "what is blocking",
    ],
    "deadline_schedule": [
        "deadline",
        "deadlines",
        "due date",
        "due dates",
        "due on",
        "due",
        "schedule",
        "schedules",
        "scheduled",
        "when is",
        "calendar",
        "timeline",
        "target date",
        "target dates",
        "by when",
        "eta",
    ],
    "task_status": [
        "task",
        "tasks",
        "status",
        "progress",
        "assigned",
        "in progress",
        "in-progress",
        "todo",
        "to-do",
        "todos",
        "backlog",
        "doing",
        "working on",
        "work item",
        "work items",
        "work on",
        "action item",
        "action items",
        "deliverable",
        "deliverables",
    ],
    "meeting_summary": [
        "meeting",
        "meetings",
        "sync",
        "syncs",
        "standup",
        "standups",
        "discussion",
        "discussions",
        "discuss",
        "attended",
        "absent",
        "agenda",
        "call",
        "calls",
        "notes",
        "conference",
        "minutes",
    ],
    "person_context": [
        "who is",
        "who are",
        "person",
        "people",
        "colleague",
        "colleagues",
        "coworker",
        "coworkers",
        "friend",
        "friends",
        "family",
        "works at",
        "lives in",
        "live in",
        "live",
        "lives",
        "team member",
        "team members",
        "role",
        "title",
        "contact",
        "profile",
        "about him",
        "about her",
        "where does",
    ],
}

# Relationship type salience boosts by query intent
INTENT_RELATIONSHIP_BOOSTS: Dict[QueryIntent, Dict[str, float]] = {
    "blocker_chain": {
        "BLOCKED_BY": 1.0,
        "HAS_ISSUE": 1.0,
        "RESOLVES": 1.0,
        "DEPENDS_ON": 0.90,
        "RAISED": 0.85,
        "ANSWERS": 0.80,
    },
    "task_status": {
        "ASSIGNED_TO": 1.0,
        "WORKS_ON": 0.95,
        "PART_OF": 0.90,
        "REQUESTED_BY": 0.85,
        "SUPPORTS": 0.85,
        "DUE_ON": 0.80,
        "BLOCKED_BY": 0.80,
    },
    "deadline_schedule": {
        "DUE_ON": 1.0,
        "SCHEDULED_ON": 1.0,
        "PLANS": 0.90,
        "PART_OF": 0.75,
        "ASSIGNED_TO": 0.70,
    },
    "meeting_summary": {
        "ATTENDED": 1.0,
        "ABSENT_FROM": 0.95,
        "DISCUSSED": 0.95,
        "DECIDED": 0.90,
        "LOCATED_AT": 0.85,
        "CREATED_IN": 0.80,
        "ABOUT": 0.80,
        "LEADS": 0.80,
    },
    "person_context": {
        "FAMILY_OF": 1.0,
        "FRIEND_OF": 1.0,
        "PARTNER_OF": 1.0,
        "WORKS_AT": 1.0,
        "LIVES_IN": 1.0,
        "MEMBER_OF": 0.95,
        "REPORTS_TO": 0.90,
        "COLLABORATES_WITH": 0.90,
        "LEADS": 0.90,
        "PREFERS": 0.85,
        "LIKES": 0.80,
        "DISLIKES": 0.80,
        "OWNS": 0.80,
    },
    "general": {},
}


def detect_query_intent(query: str) -> QueryIntent:
    """Detect the primary intent of a user query using rule/keyword matching.

    Args:
        query: Raw query text.

    Returns:
        Detected QueryIntent literal.
    """
    clean_query = query.strip().lower()

    # Priority check for intent triggers
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            # Word boundary regex or direct phrase match
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, clean_query):
                return intent

    return "general"


def get_relationship_intent_salience(rel_type: str, intent: QueryIntent) -> float:
    """Calculate the salience score [0.0..1.0] of a relationship type for a given intent.

    Tier-1 edges are preferred over Tier-2 and generic RELATED_TO fallbacks.
    """
    if rel_type == "ALIAS_OF":
        return 1.0

    # Explicit intent-boosted mapping
    boosts = INTENT_RELATIONSHIP_BOOSTS.get(intent, {})
    if rel_type in boosts:
        return boosts[rel_type]

    # Baseline defaults
    if rel_type == "RELATED_TO":
        return 0.30

    if rel_type in TIER_1_RELATIONSHIPS:
        return 0.70

    return 0.50


def _clean_text(s: str) -> str:
    """Strip punctuation and collapse whitespace for resilient matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip().lower()


ANCHOR_STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "what", "who", "whom", "whose", "when", "where", "why", "how", "which",
    "that", "this", "these", "those", "they", "them", "their", "there", "here",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "not", "no", "nor", "any", "all", "some", "such", "than", "too", "very",
    "issues", "issue", "task", "tasks", "project", "projects", "meeting", "meetings",
    "person", "people", "deadline", "deadlines", "blocking", "blocked", "assigned",
    "raise", "raised", "resolved", "resolve",
}


def _extract_query_phrases(query: str) -> List[str]:
    """Extract candidate phrases and n-grams from a query for entity matching."""
    clean = query.strip()
    phrases: List[str] = [clean]

    # Quoted strings
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', clean)
    for q1, q2 in quoted:
        q = q1 or q2
        if q.strip():
            phrases.append(q.strip())

    # Token-based n-grams (1 to 4 grams) preserving original words
    raw_words = [w.strip() for w in re.split(r"[\s,?!;:]+", clean) if w.strip()]
    num_raw = len(raw_words)
    for n in range(1, min(5, num_raw + 1)):
        for i in range(num_raw - n + 1):
            ngram = " ".join(raw_words[i : i + n])
            if n == 1 and ngram.lower() in ANCHOR_STOPWORDS:
                continue
            if len(ngram) >= 3:
                phrases.append(ngram)

    # Clean words
    words = re.findall(r"\b[\w\-']+\b", clean)
    num_words = len(words)
    for n in range(1, min(5, num_words + 1)):
        for i in range(num_words - n + 1):
            ngram = " ".join(words[i : i + n])
            if n == 1 and ngram.lower() in ANCHOR_STOPWORDS:
                continue
            if len(ngram) >= 3:
                phrases.append(ngram)

    return list(dict.fromkeys(phrases))


def resolve_seed_anchors(
    session: Any,
    query: str,
    seed_entities: Optional[List[str]] = None,
    include_private: bool = False,
) -> List[AnchorMatch]:
    """Resolve query phrases and explicit seed entities against Neo4j nodes.

    Matching hierarchy:
      1) Exact normalized key match (score = 1.0)
      2) Exact match in n.aliases (score = 0.95)
      3) Substring / RapidFuzz token_sort_ratio >= 80 (score = ratio / 100.0)

    Args:
        session: Active Neo4j session or transaction.
        query: User search query.
        seed_entities: Optional explicit entity names or keys provided by caller.
        include_private: If False, exclude nodes where sensitivity = 'private'.

    Returns:
        List of unique AnchorMatch objects sorted by descending match score.
    """
    # Fetch eligible nodes from Neo4j (suppressing Conversation hubs and private nodes)
    cypher = """
    MATCH (n)
    WHERE NOT n:Conversation
      AND n.key IS NOT NULL
      AND ($include_private OR coalesce(n['sensitivity'], 'normal') <> 'private')
    RETURN n.key AS key,
           n.name AS name,
           labels(n)[0] AS type,
           n['aliases'] AS aliases,
           n['sensitivity'] AS sensitivity
    """
    records = session.run(cypher, include_private=include_private)

    nodes = []
    for rec in records:
        key_val = rec.get("key")
        if not key_val:
            continue
        name_val = rec.get("name") or str(key_val)
        node_type = rec.get("type") or "Concept"
        aliases = rec.get("aliases") or []
        if not isinstance(aliases, list):
            aliases = []
        nodes.append({
            "key": str(key_val),
            "name": str(name_val),
            "type": node_type,
            "aliases": aliases,
        })

    candidate_phrases = _extract_query_phrases(query)
    explicit_seeds = [s.strip() for s in (seed_entities or []) if s.strip()]

    # Collect best match per node key
    matches_by_key: Dict[str, AnchorMatch] = {}

    for node in nodes:
        node_key = node["key"]
        node_name = node["name"]
        node_type = node["type"]
        node_aliases = [str(a).strip() for a in node["aliases"]]

        best_score = 0.0
        best_match_type = ""

        # Check explicit seeds first
        for seed in explicit_seeds:
            norm_seed = normalize_key(seed)
            if norm_seed == node_key:
                if 1.0 > best_score:
                    best_score = 1.0
                    best_match_type = "seed_explicit"
            elif any(norm_seed == normalize_key(a) for a in node_aliases):
                if 0.95 > best_score:
                    best_score = 0.95
                    best_match_type = "exact_alias"
            else:
                ratio = float(token_sort_ratio(norm_seed, node_key))
                if ratio >= 80.0 and (ratio / 100.0) > best_score:
                    best_score = ratio / 100.0
                    best_match_type = "fuzzy_name"

        # Check query phrases
        for phrase in candidate_phrases:
            norm_phrase = normalize_key(phrase)
            if norm_phrase in ANCHOR_STOPWORDS:
                continue

            # 1. Exact normalized key match
            if norm_phrase == node_key:
                if 1.0 > best_score:
                    best_score = 1.0
                    best_match_type = "exact_key"
                break

            # 2. Exact match in aliases (score = 0.95)
            if any(
                norm_phrase == normalize_key(a)
                or _clean_text(norm_phrase) == _clean_text(a)
                for a in node_aliases
            ):
                if 0.95 >= best_score:
                    best_score = 0.95
                    best_match_type = "exact_alias"

            # 3. Substring match on meaningful word boundaries (min 4 chars)
            norm_name = normalize_key(node_name)
            if len(norm_name) >= 4 and len(norm_phrase) >= 4:
                is_word_sub = bool(
                    re.search(rf"\b{re.escape(norm_name)}\b", norm_phrase)
                    or re.search(rf"\b{re.escape(norm_phrase)}\b", norm_name)
                )
                if is_word_sub:
                    sub_score = min(0.90, max(0.85, float(token_sort_ratio(norm_phrase, norm_name)) / 100.0))
                    if sub_score > best_score:
                        best_score = sub_score
                        best_match_type = "substring"

            # 4. RapidFuzz token_sort_ratio >= 80
            ratio = float(token_sort_ratio(norm_phrase, node_key))
            if ratio >= 80.0:
                score = min(0.95, ratio / 100.0) if ratio < 100.0 else 1.0
                if score > best_score:
                    best_score = score
                    best_match_type = "exact_key" if ratio == 100.0 else "fuzzy_name"

            for alias in node_aliases:
                alias_ratio = float(token_sort_ratio(norm_phrase, normalize_key(alias)))
                if alias_ratio >= 80.0:
                    # Alias match score is capped at 0.95
                    score = 0.95 if alias_ratio == 100.0 else round(0.95 * (alias_ratio / 100.0), 4)
                    if score > best_score:
                        best_score = score
                        best_match_type = "exact_alias" if alias_ratio == 100.0 else "fuzzy_alias"

        if best_score > 0.0:
            matches_by_key[node_key] = AnchorMatch(
                key=node_key,
                name=node_name,
                type=node_type,
                match_type=best_match_type,  # type: ignore[arg-type]
                score=round(best_score, 4),
            )

    sorted_anchors = sorted(matches_by_key.values(), key=lambda m: m.score, reverse=True)
    return sorted_anchors
