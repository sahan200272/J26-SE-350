#!/usr/bin/env sh
# Linux hub wrapper for the nightly compaction job (RP-18, section 4).
# cron starts this at 20:00 (see compaction.cron). It holds NO logic: it only
# finds the repo, uses the repo's .venv Python, and runs the Python entry point.
#
#   scripts/scheduler/run_compaction.sh /path/to/vault
#
# Exit code = the job's exit code (0 ok, 1 a write failed, 2 bad input).
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: run_compaction.sh /path/to/vault" >&2
    exit 2
fi

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p "$REPO/logs"
cd "$REPO"
exec "$REPO/.venv/bin/python" -m agentic_core.compaction.run --vault "$1" --log-file "$REPO/logs/compaction.log"
