"""Command-line interface for GraphRAG retrieval and baseline evaluation.

Usage examples:
    python -m graphrag.retrieve_cli --query "What is blocking the benchmark task?"
    python -m graphrag.retrieve_cli --query "Sarah Chen" --hops 3 --format
    python -m graphrag.retrieve_cli --query "Ollama latency" --compare-baseline
    python -m graphrag.retrieve_cli --pending
"""

import argparse
import json
import sys
from typing import List, Optional

from graph_schema.schema import get_driver
from graphrag.baseline_keyword import compare_retrieval
from graphrag.context_builder import get_pending_items_context
from graphrag.models import RetrievalRequest, RetrievalResult
from graphrag.retriever import retrieve_subgraph


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="GraphRAG Constrained Multi-Hop Retrieval CLI (Jira RP-27)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Natural language search query.",
    )
    parser.add_argument(
        "--seed",
        action="append",
        dest="seeds",
        default=[],
        help="Explicit seed entity name or key (can be specified multiple times).",
    )
    parser.add_argument(
        "--hops",
        type=int,
        default=2,
        help="Maximum multi-hop depth (clamped strictly to 1..3, default 2).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=15,
        help="Maximum ranked paths and subgraph items to return (default 15).",
    )
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Include nodes marked with sensitivity='private'.",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Execute side-by-side comparison against flat keyword baseline.",
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Retrieve active pending tasks, blockers, deadlines, and assignees for Proactive Notifications.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Print raw JSON response instead of human-readable Markdown.",
    )
    parser.add_argument(
        "--format",
        action="store_true",
        dest="formatted",
        help="Print formatted Markdown context block ready for LLM synthesis.",
    )

    args = parser.parse_args(argv)

    try:
        driver = get_driver()
        driver.verify_connectivity()
    except Exception as exc:
        print(f"Error connecting to Neo4j database: {exc}", file=sys.stderr)
        return 1

    try:
        # 1. Pending tasks context for Proactive Notification Engine
        if args.pending:
            pending_res = get_pending_items_context(
                driver=driver,
                include_private=args.include_private,
            )
            if args.output_json:
                print(json.dumps(pending_res, indent=2))
            else:
                print(pending_res["formatted_context"])
            return 0

        # Validate query requirement
        if not args.query:
            print("Error: --query is required when not using --pending.", file=sys.stderr)
            parser.print_usage(file=sys.stderr)
            return 2

        req = RetrievalRequest(
            query=args.query,
            seed_entities=args.seeds,
            max_hops=args.hops,
            top_k=args.top_k,
            include_private=args.include_private,
        )

        # 2. Side-by-side comparison against flat keyword baseline
        if args.compare_baseline:
            comparison = compare_retrieval(req, driver=driver)
            if args.output_json:
                print(json.dumps(comparison, indent=2))
            else:
                print("=" * 70)
                print("GRAPHRAG vs FLAT KEYWORD BASELINE COMPARISON")
                print("=" * 70)
                print(f"Query: \"{args.query}\"")
                print(f"Detected Intent: {comparison['detected_intent']}")
                print(f"Max Hops: {comparison['max_hops']}")
                print("-" * 70)
                print("METRICS:")
                metrics = comparison["metrics"]
                print(f"  GraphRAG Discovered Entities: {metrics['graphrag_entity_count']}")
                print(f"  Flat Keyword Matched Entities: {metrics['keyword_entity_count']}")
                print(f"  Multi-Hop Entity Gain:         {metrics['multi_hop_gain_count']}")
                print(f"  GraphRAG Relational Paths:     {metrics['graphrag_paths_found']}")
                print(f"  GraphRAG Latency:              {metrics['graphrag_latency_ms']} ms")
                print(f"  Keyword Latency:               {metrics['keyword_latency_ms']} ms")
                print("-" * 70)
                print("SUMMARY:")
                print(comparison["summary"])
                print("-" * 70)
                if comparison["multi_hop_entity_gain"]:
                    print("ENTITIES GAINED VIA MULTI-HOP RELATIONAL PATHS:")
                    for g in comparison["multi_hop_entity_gain"]:
                        print(f"  + [{g['type']}] {g['name']}")
                print("=" * 70)
            return 0

        # 3. Standard GraphRAG Subgraph Retrieval
        result: RetrievalResult = retrieve_subgraph(req, driver=driver)

        if args.output_json:
            print(result.model_dump_json(indent=2))
        else:
            print(result.formatted_context)

        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
