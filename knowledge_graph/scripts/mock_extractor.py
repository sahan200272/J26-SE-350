"""Mock Agentic Core Extractor CLI.

This script simulates the Agentic Core extractor by reading hand-crafted payload
JSON fixtures from sample_data/payloads/ and POSTing them to the Knowledge Graph
FastAPI ingestion service (http://127.0.0.1:8000/ingest).

ARCHITECTURE & INTEGRATION NOTE:
This mock replaces the real Agentic Reasoning Core extractor component until
the teammate's extractor is ready and integrated. Once the real Agentic Core
extractor is deployed, this mock script is the ONLY component in the pipeline
that will be replaced or pointed to the live streaming extraction queue.
The Knowledge Graph ingestion API contract remains completely unchanged.
"""

import argparse
import json
from pathlib import Path
import sys
import time
from typing import List, Optional
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/ingest"
DEFAULT_DELAY = 1.0


def get_payload_files(payloads_dir: Path, include_unknown: bool = False) -> List[Path]:
    """Retrieve payload files, excluding triples_example.json and optionally 06_unknown_types.json."""
    if not payloads_dir.exists():
        raise FileNotFoundError(f"Payloads directory not found: {payloads_dir}")

    files: List[Path] = []
    for p in sorted(payloads_dir.glob("*.json")):
        if p.name == "triples_example.json":
            continue
        if p.name == "06_unknown_types.json" and not include_unknown:
            continue
        files.append(p)

    return files


def send_payload(url: str, file_path: Path) -> None:
    """Read a JSON payload file and POST to the ingestion API using only urllib."""
    with open(file_path, "rb") as f:
        payload_bytes = f.read()

    req = urllib.request.Request(
        url=url,
        data=payload_bytes,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status_code = resp.status
            body = resp.read().decode("utf-8")
            data = json.loads(body)

            # Print concise summary line with returned counts; NEVER print payload contents
            nodes_created = data.get("nodes_created", 0)
            nodes_merged = data.get("nodes_merged", 0)
            edges_created = data.get("edges_created", 0)
            edges_merged = data.get("edges_merged", 0)
            edges_replaced = data.get("edges_replaced", 0)
            aliases_added = data.get("aliases_added", 0)
            warning_count = len(data.get("warnings", []))

            print(
                f"[{file_path.name}] {status_code} OK - "
                f"nodes: created={nodes_created}, merged={nodes_merged} | "
                f"edges: created={edges_created}, merged={edges_merged}, replaced={edges_replaced} | "
                f"aliases: +{aliases_added} | warnings: {warning_count}"
            )
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        print(f"[{file_path.name}] HTTP {exc.code} Error: {err_msg}", file=sys.stderr)
    except urllib.error.URLError as exc:
        print(f"[{file_path.name}] Connection Error: {exc.reason}", file=sys.stderr)
    except Exception as exc:
        print(f"[{file_path.name}] Error: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mock Agentic Core Extractor: stream synthetic conversation payloads to Knowledge Graph API."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Target FastAPI ingestion URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Delay in seconds between sending payloads (default: {DEFAULT_DELAY})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate ingestion using ?dry_run=true without mutating Neo4j database",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Send the entire batch of payloads N times to demonstrate idempotency (default: 1)",
    )
    parser.add_argument(
        "--include-unknown",
        action="store_true",
        help="Include 06_unknown_types.json (excluded by default)",
    )

    args = parser.parse_args()

    # Determine target URL
    target_url = args.url
    if args.dry_run:
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{sep}dry_run=true"

    payloads_dir = Path(__file__).resolve().parent.parent / "sample_data" / "payloads"
    files = get_payload_files(payloads_dir, include_unknown=args.include_unknown)

    if not files:
        print(f"No payload files found in {payloads_dir}", file=sys.stderr)
        sys.exit(1)

    mode_label = "DRY RUN (rolled back)" if args.dry_run else "LIVE INGESTION"
    print(f"=== Mock Agentic Core Extractor ===")
    print(f"Target URL: {target_url} ({mode_label})")
    print(f"Payloads:   {len(files)} files | Delay: {args.delay}s | Repeat: {args.repeat}x")
    print("-" * 65)

    for round_idx in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f">>> Round {round_idx}/{args.repeat}")

        for idx, file_path in enumerate(files):
            send_payload(target_url, file_path)
            if args.delay > 0 and (idx < len(files) - 1 or round_idx < args.repeat):
                time.sleep(args.delay)

    print("-" * 65)
    print("Mock extraction run complete.")


if __name__ == "__main__":
    main()
