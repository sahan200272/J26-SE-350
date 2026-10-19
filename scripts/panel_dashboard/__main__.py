"""Run the PP1 panel dashboard: python -m scripts.panel_dashboard"""

from __future__ import annotations

import argparse
from pathlib import Path

from scripts.panel_dashboard.server import DEFAULT_EVAL_DIR, make_server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Local PP1 panel dashboard (Component 2).")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--eval-dir", type=Path, default=DEFAULT_EVAL_DIR,
                        help="folder with the result JSON files")
    args = parser.parse_args(argv)

    server = make_server("127.0.0.1", args.port, args.eval_dir.resolve())
    print(f"Panel dashboard on http://127.0.0.1:{args.port}/  (Ctrl+C to stop)")
    print(f"Reading result files from {args.eval_dir}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
