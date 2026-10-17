"""Command-line tool: cut a transcript file into segments and print them."""

import argparse
import sys
from pathlib import Path

import yaml

from agentic_core.segmentation.config import CONFIG_PATH, load_config
from agentic_core.segmentation.segmenter import format_time, segment_transcript
from agentic_core.segmentation.transcript import parse_transcript_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agentic_core.segmentation",
        description="Cut a diarized Markdown transcript into conversation segments.",
    )
    parser.add_argument("transcript", type=Path, help="path to the transcript .md file")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH, help="settings YAML file")
    parser.add_argument(
        "--summary", action="store_true", help="one line per segment, without the text"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
        transcript = parse_transcript_file(args.transcript)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    segments = segment_transcript(transcript, config)

    print(
        f"Recording: {transcript.recording_id or '(no id)'} | "
        f"{len(transcript.turns)} turns | {len(segments)} segments"
    )
    print(
        f"Settings: long_pause_s={config.long_pause_s}, cue_pause_s={config.cue_pause_s}, "
        f"max_segment_tokens={config.max_segment_tokens}"
    )
    for segment in segments:
        flag = " | OVERSIZED" if segment.oversized else ""
        print(
            f"\nSegment {segment.index} | starts {format_time(segment.start_s)} | "
            f"started_because={segment.started_because} | {len(segment.turns)} turns | "
            f"~{segment.est_tokens} tokens{flag}"
        )
        if not args.summary:
            for line in segment.to_text().splitlines():
                print(f"  {line}")
    return 0