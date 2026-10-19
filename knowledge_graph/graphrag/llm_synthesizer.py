"""Local Ollama LLaMA 3 (8B) Graph-Grounded Answer Synthesizer for GraphRAG.

Connects the custom mathematical multi-hop GraphRAG retrieval engine (Steps 1-3)
to a locally hosted Ollama LLaMA 3 8B model (Step 4) to synthesize natural-language
answers grounded strictly in the retrieved subgraph and provenance records.

If the local Ollama daemon is offline or unreachable, falls back gracefully to a
deterministic graph-path narrative summary so offline execution never fails.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

import ollama

from graphrag.models import RetrievalResult

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3:8b")

GRAPH_GROUNDED_SYSTEM_PROMPT: str = (
    "You are a helpful, privacy-preserving Voice AI Assistant answering questions from a personal Knowledge Graph. "
    "Answer the user's question directly and naturally in 1 to 2 simple sentences using ONLY the provided "
    "[Multi-Hop Relational Paths with Scores] and [Entity Details & Properties]. "
    "Rules:\n"
    "1. Give a clean, human-friendly direct answer (for example: 'You have the Sprint Planning Meeting scheduled on 2026-10-18 at 10:00.' or 'Kamal Perera's friends are Ruwan Silva and Ruwan Fernando.').\n"
    "2. Include specific dates, times, statuses, or roles from [Entity Details & Properties] when relevant.\n"
    "3. Do NOT output raw graph syntax like '--[FRIEND_OF]-->', node labels in parentheses, or numerical scores like '0.9400', and do NOT start with 'Based on the provided graph context'.\n"
    "4. Do NOT hallucinate or invent any facts outside the provided context."
)


def deterministic_fallback_synthesis(result: RetrievalResult) -> str:
    """Produce a deterministic, rule-based natural language answer from top-ranked paths when Ollama is offline."""
    if not result.anchors or not result.ranked_paths:
        return f"No connected knowledge graph paths were found for query: '{result.query}'."

    top_anchors = ", ".join(f"{a.name} ({a.type})" for a in result.anchors[:3])
    statements: List[str] = []

    for path in result.ranked_paths[:5]:
        hop_descriptions: List[str] = []
        for hop in path.hops:
            rel_label = hop.relationship_type
            orig_label = hop.props.get("label") if hop.props else None
            if rel_label == "RELATED_TO" and orig_label:
                rel_display = f"{rel_label} ({orig_label})"
            else:
                rel_display = rel_label
            hop_descriptions.append(
                f"{hop.from_node['name']} ({hop.from_node['type']}) "
                f"--[{rel_display}]--> "
                f"{hop.to_node['name']} ({hop.to_node['type']})"
            )
        statements.append(f"{' ; '.join(hop_descriptions)} [score: {path.final_score:.2f}]")

    summary = (
        f"Based on {len(result.ranked_paths)} multi-hop graph paths anchored at {top_anchors}: "
        + " | ".join(statements)
    )
    return summary


def synthesize_grounded_answer(
    result: RetrievalResult,
    model: Optional[str] = None,
    host: Optional[str] = None,
    temperature: float = 0.0,
    num_ctx: int = 4096,
    num_predict: int = 256,
) -> Dict[str, Any]:
    """Synthesize a natural-language answer grounded in the retrieved GraphRAG subgraph using local Ollama.

    Args:
        result: Populated RetrievalResult containing ranked_paths and formatted_context.
        model: Ollama model identifier (defaults to 'llama3:8b').
        host: Local Ollama server URL (defaults to 'http://127.0.0.1:11434').
        temperature: Sampling temperature (0.0 for deterministic research reproducibility).
        num_ctx: Context window size (4096).
        num_predict: Maximum generated tokens (256).

    Returns:
        Dictionary with keys: 'answer', 'model_used', 'latency_ms', 'used_fallback'.
    """
    start_time = time.perf_counter()
    target_model = model or DEFAULT_OLLAMA_MODEL
    target_host = host or DEFAULT_OLLAMA_HOST

    if not result.anchors and not result.ranked_paths:
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return {
            "answer": f"No matching entities or relational paths were found in the knowledge graph for '{result.query}'.",
            "model_used": "none (empty subgraph)",
            "latency_ms": latency_ms,
            "used_fallback": True,
        }

    user_prompt = (
        f"User Question: {result.query}\n\n"
        f"Retrieved Knowledge Graph Context:\n{result.formatted_context}\n\n"
        f"Answer the question simply and directly in 1-2 natural sentences (include dates/times if relevant, and do not mention graph scores or arrow syntax):"
    )

    try:
        client = ollama.Client(host=target_host)
        response = client.chat(
            model=target_model,
            messages=[
                {"role": "system", "content": GRAPH_GROUNDED_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            options={
                "num_ctx": num_ctx,
                "temperature": temperature,
                "num_predict": num_predict,
            },
        )
        # Extract content from either object attribute or dict response
        if hasattr(response, "message") and hasattr(response.message, "content"):
            answer_text = str(response.message.content).strip()
        elif isinstance(response, dict):
            answer_text = str(response.get("message", {}).get("content", "")).strip()
        else:
            answer_text = str(response).strip()

        if not answer_text:
            raise ValueError("Empty response received from Ollama model.")

        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return {
            "answer": answer_text,
            "model_used": target_model,
            "latency_ms": latency_ms,
            "used_fallback": False,
        }
    except Exception as exc:
        logger.warning(
            "Local Ollama model '%s' at %s unavailable (%s); using deterministic graph synthesis fallback.",
            target_model,
            target_host,
            exc,
        )
        fallback_text = deterministic_fallback_synthesis(result)
        latency_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
        return {
            "answer": fallback_text,
            "model_used": f"deterministic_fallback ({target_model} offline)",
            "latency_ms": latency_ms,
            "used_fallback": True,
        }
