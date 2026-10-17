"""Developer check: run the extractor on a transcript with the real LLM (RP-14).

Usage, from the repo root:
    python -m scripts.try_extractor <transcript.md> <recording date YYYY-MM-DD>
"""
import sys
from datetime import date

from agentic_core.decoding.extractor import extract_plan
from agentic_core.llm.client import LLMClient
from agentic_core.segmentation.segmenter import segment_transcript
from agentic_core.segmentation.transcript import parse_transcript_file


def main() -> None:
    path, day = sys.argv[1], date.fromisoformat(sys.argv[2])
    client = LLMClient()
    if not client.is_ready():
        raise SystemExit("Ollama is not running or the model is missing.")

    for segment in segment_transcript(parse_transcript_file(path)):
        result = extract_plan(segment, client, day)
        print(
            f"segment {segment.index}: skipped={result.skipped} "
            f"valid={result.plan is not None} tokens={result.tokens_out} "
            f"tpot={result.tpot_ms:.0f} ms total={result.total_s:.1f} s"
        )
        if result.error:
            print("  error:", result.error)
        if result.plan:
            print(result.plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()