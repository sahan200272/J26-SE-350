"""Command-line interface for ingesting payload or triple JSON files into Neo4j."""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List

from graph_schema.adapters import triples_to_payload
from graph_schema.ingest import IngestResult, ingest_payload
from graph_schema.models import Payload

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger("ingest_cli")


def process_file(
    file_path: Path,
    dry_run: bool = False,
    is_triples: bool = False,
) -> IngestResult:
    """Load and ingest a single JSON payload or triples file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if is_triples:
        if isinstance(data, dict) and "triples" in data:
            triples = data["triples"]
            source = data.get("source", file_path.stem)
            timestamp = data.get("timestamp")
        elif isinstance(data, list):
            triples = data
            source = file_path.stem
            timestamp = None
        else:
            raise ValueError(f"Unexpected JSON format in triples file {file_path}")

        payload = triples_to_payload(triples, source=source, timestamp=timestamp)
    else:
        payload = Payload.model_validate(data)

    return ingest_payload(payload, dry_run=dry_run)


def print_summary(file_path: Path, result: IngestResult, dry_run: bool) -> None:
    """Print user-friendly summary of ingestion result."""
    mode_str = "DRY RUN (no changes persisted)" if dry_run else "LIVE INGESTION"
    print("=" * 70)
    print(f"File: {file_path}")
    print(f"Mode: {mode_str}")
    print("-" * 70)
    print(f"  Nodes created:    {result.nodes_created}")
    print(f"  Nodes merged:     {result.nodes_merged}")
    print(f"  Edges created:    {result.edges_created}")
    print(f"  Edges merged:     {result.edges_merged}")
    print(f"  Edges replaced:   {result.edges_replaced}")
    print(f"  Aliases added:    {result.aliases_added}")
    if result.warnings:
        print(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")
    else:
        print("  Warnings:         None")
    print(f"  Touched entities: {len(result.touched)}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Knowledge Graph payload or triple JSON files into Neo4j."
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="Path(s) to payload or triple JSON files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate ingestion in a rolled-back transaction without saving changes.",
    )
    parser.add_argument(
        "--triples",
        action="store_true",
        help="Treat input files as triple lists ([S, P, O] tuples or typed triples).",
    )

    args = parser.parse_args()

    for file_str in args.files:
        p = Path(file_str)
        try:
            result = process_file(p, dry_run=args.dry_run, is_triples=args.triples)
            print_summary(p, result, dry_run=args.dry_run)
        except Exception as exc:
            print(f"ERROR processing {p}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
