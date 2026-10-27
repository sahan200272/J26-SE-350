"""Query intent classification and seed anchor entity resolution."""

import re
from typing import Any, Dict, List, Optional, Set
from rapidfuzz.fuzz import token_set_ratio, token_sort_ratio

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
        "LOCATED_AT": 0.95,
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
        "LOCATED_AT": 1.0,
        "LIVES_IN": 1.0,
        "FAMILY_OF": 1.0,
        "FRIEND_OF": 1.0,
        "PARTNER_OF": 1.0,
        "WORKS_AT": 1.0,
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


def classify_query_intent_ml(query: str) -> tuple[QueryIntent, float, Dict[str, float]]:
    """Classify query intent using the trained ML Intent Classifier blended with lexical signals.

    Returns:
        Tuple of (predicted_intent, confidence_score, class_probabilities).
    """
    from graphrag.intent_classifier import get_intent_classifier

    clean_query = query.strip().lower()
    clf = get_intent_classifier()
    ml_intent, ml_conf, ml_probs = clf.predict(query)

    # Check high-precision lexical rule match
    rule_intent: Optional[QueryIntent] = None
    for intent, keywords in INTENT_KEYWORDS.items():
        for kw in keywords:
            pattern = rf"\b{re.escape(kw)}\b"
            if re.search(pattern, clean_query):
                rule_intent = intent
                break
        if rule_intent:
            break

    if rule_intent is not None:
        # Boost probability of the aligned lexical intent and re-normalize
        blended = dict(ml_probs)
        blended[rule_intent] = blended.get(rule_intent, 0.0) + 0.45
        total = sum(blended.values()) or 1.0
        norm_probs = {k: round(v / total, 4) for k, v in blended.items()}
        return rule_intent, round(norm_probs[rule_intent], 4), norm_probs

    # When no explicit rule keyword triggers, use ML prediction if confidence >= 0.55
    if ml_conf >= 0.55:
        return ml_intent, ml_conf, ml_probs

    return "general", round(max(ml_probs.get("general", 0.5), ml_conf), 4), ml_probs


def detect_query_intent(query: str) -> QueryIntent:
    """Detect the primary intent of a user query using the hybrid ML + rule classifier.

    Args:
        query: Raw query text.

    Returns:
        Detected QueryIntent literal.
    """
    intent, _, _ = classify_query_intent_ml(query)
    return intent


def get_relationship_intent_salience(
    rel_type: str,
    intent: QueryIntent,
    query: Optional[str] = None,
) -> float:
    """Calculate the salience score [0.0..1.0] of a relationship type for a given intent.

    Tier-1 edges are preferred over Tier-2 and generic RELATED_TO fallbacks.
    When query text is provided, contextual cues (e.g. location or timing keywords)
    adjust specific edge priorities so paths answering the exact question rank highest.
    """
    if rel_type == "ALIAS_OF":
        return 1.0

    # Query-aware contextual override
    if query:
        clean_q = query.lower()
        # Location queries ("where is", "where does", "location", "venue", "place", "held in")
        if any(w in clean_q for w in ("where", "location", "venue", "place", "where is", "where does")):
            if rel_type in ("LOCATED_AT", "LIVES_IN"):
                return 1.0
            if rel_type == "WORKS_AT" and any(w in clean_q for w in ("work", "job", "office", "company", "firm")):
                return 1.0
            # Non-spatial relations (family, friends, preferences) do not answer a location query
            if rel_type in ("FAMILY_OF", "FRIEND_OF", "PARTNER_OF", "LIKES", "DISLIKES", "PREFERS"):
                return 0.60
        # Time / schedule queries ("when is", "what time", "schedule", "deadline", "due date")
        elif any(w in clean_q for w in ("when", "time", "date", "due", "deadline", "schedule", "scheduled")):
            if rel_type in ("DUE_ON", "SCHEDULED_ON"):
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

    # Stripped possessive variant (e.g. "dilini's party" -> "dilini party")
    depossessive = re.sub(r"'s\b", "", clean)
    if depossessive != clean and len(depossessive.strip()) >= 3:
        phrases.append(depossessive.strip())

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

    # Clean words and depossessive n-grams
    deposs_words = [w.strip() for w in re.split(r"[\s,?!;:]+", depossessive) if w.strip()]
    num_deposs = len(deposs_words)
    for n in range(1, min(5, num_deposs + 1)):
        for i in range(num_deposs - n + 1):
            ngram = " ".join(deposs_words[i : i + n])
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

            # 5. Multi-token / token_set_ratio match for multi-word entities
            clean_p = _clean_text(re.sub(r"'s\b", "", norm_phrase))
            clean_k = _clean_text(re.sub(r"'s\b", "", node_key))
            clean_n = _clean_text(re.sub(r"'s\b", "", norm_name))
            p_words = set(w for w in clean_p.split() if w not in ANCHOR_STOPWORDS and len(w) >= 3)
            n_words = set(w for w in clean_n.split() if w not in ANCHOR_STOPWORDS and len(w) >= 3)
            k_words = set(w for w in clean_k.split() if w not in ANCHOR_STOPWORDS and len(w) >= 3)

            if len(p_words) >= 2 and (p_words.issubset(n_words) or p_words.issubset(k_words)):
                if 0.95 > best_score:
                    best_score = 0.95
                    best_match_type = "multi_token_match"
            elif len(p_words) >= 2:
                ts_ratio = max(
                    float(token_set_ratio(clean_p, clean_n)),
                    float(token_set_ratio(clean_p, clean_k)),
                )
                if ts_ratio >= 90.0:
                    score = min(0.92, round(ts_ratio / 100.0, 4))
                    if score > best_score:
                        best_score = score
                        best_match_type = "fuzzy_name"

        if best_score > 0.0:
            matches_by_key[node_key] = AnchorMatch(
                key=node_key,
                name=node_name,
                type=node_type,
                match_type=best_match_type,  # type: ignore[arg-type]
                score=round(best_score, 4),
            )

    # Category-to-Label Fallback: if no specific entity name matched (e.g., "When is the meeting?"),
    # anchor on nodes whose Neo4j label matches the category asked in the query.
    if not matches_by_key:
        lower_q = query.strip().lower()
        category_label_map = {
            "Meeting": ["meeting", "meetings", "sync", "standup", "call"],
            "Deadline": ["deadline", "deadlines", "due date", "due on", "schedule", "scheduled"],
            "Event": ["event", "events", "trip", "dinner", "party"],
            "Task": ["task", "tasks", "todo", "todos", "action item", "assigned"],
            "Issue": ["issue", "issues", "blocker", "blockers", "bug", "problem"],
            "Decision": ["decision", "decisions", "decided", "agreed"],
        }
        target_labels: Set[str] = set()
        for label_name, triggers in category_label_map.items():
            if any(re.search(rf"\b{re.escape(t)}\b", lower_q) for t in triggers):
                target_labels.add(label_name)
                if label_name == "Deadline":
                    target_labels.add("Meeting")
                    target_labels.add("Event")

        if target_labels:
            for node in nodes:
                if node["type"] in target_labels:
                    matches_by_key[node["key"]] = AnchorMatch(
                        key=node["key"],
                        name=node["name"],
                        type=node["type"],
                        match_type="substring",
                        score=0.85,
                    )

    sorted_anchors = sorted(matches_by_key.values(), key=lambda m: m.score, reverse=True)
    return sorted_anchors
