"""Cut a transcript into conversation segments using simple rules (no LLM)."""

from dataclasses import dataclass

from agentic_core.segmentation.signals import TurnSignals, compute_signals
from agentic_core.segmentation.transcript import Transcript, Turn

# Assumptions, not measured. Check them later against Ollama's real token counts.
TOKENS_PER_WORD = 1.3
TOKENS_PER_TURN_OVERHEAD = 8  # speaker label, time stamp, line break


@dataclass(frozen=True)
class SegmentationConfig:
    """Settings for the segmenter. Defaults are untuned guesses."""

    long_pause_s: float = 120.0  # a pause this long always starts a new segment
    cue_pause_s: float = 15.0  # a cue phrase plus this pause starts a new segment
    max_segment_tokens: int = 1500  # leave room inside num_ctx 4096 for prompt and answer

    def __post_init__(self) -> None:
        if self.long_pause_s <= 0 or self.cue_pause_s <= 0 or self.max_segment_tokens <= 0:
            raise ValueError("all settings must be positive")
        if self.cue_pause_s > self.long_pause_s:
            raise ValueError("cue_pause_s must not be larger than long_pause_s")


@dataclass(frozen=True)
class Segment:
    """A block of turns that belong to one topic."""

    index: int
    turns: tuple[Turn, ...]
    started_because: str  # "start", "long_pause", "cue_and_pause" or "size_limit"
    est_tokens: int
    oversized: bool  # one turn alone is bigger than the limit

    @property
    def start_s(self) -> float:
        return self.turns[0].start_s

    def to_text(self) -> str:
        """The segment as transcript lines, ready to put in a prompt."""
        return "\n".join(
            f"[{format_time(turn.start_s)}] {turn.speaker}: {turn.text}" for turn in self.turns
        )


def format_time(seconds: float) -> str:
    """Turn 102.0 into '00:01:42'."""
    total = int(round(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def estimate_turn_tokens(turn: Turn) -> int:
    """Guess how many tokens this turn will use in a prompt."""
    return round(len(turn.text.split()) * TOKENS_PER_WORD) + TOKENS_PER_TURN_OVERHEAD


def _topic_break_reason(signal: TurnSignals, config: SegmentationConfig) -> str | None:
    """Return why a new segment should start before this turn, or None."""
    if signal.pause_s is None:
        return None
    if signal.pause_s >= config.long_pause_s:
        return "long_pause"
    if signal.has_cue and signal.pause_s >= config.cue_pause_s:
        return "cue_and_pause"
    return None


def _make_segment(
    index: int, turns: list[Turn], reason: str, tokens: int, config: SegmentationConfig
) -> Segment:
    return Segment(index, tuple(turns), reason, tokens, tokens > config.max_segment_tokens)


def segment_transcript(
    transcript: Transcript, config: SegmentationConfig | None = None
) -> list[Segment]:
    """Cut a transcript into segments. Every turn lands in exactly one segment."""
    config = config or SegmentationConfig()
    signals = compute_signals(transcript)

    segments: list[Segment] = []
    turns_now: list[Turn] = []
    tokens_now = 0
    reason_now = "start"

    for turn, signal in zip(transcript.turns, signals):
        turn_tokens = estimate_turn_tokens(turn)
        reason = _topic_break_reason(signal, config)
        if turns_now and reason is None and tokens_now + turn_tokens > config.max_segment_tokens:
            reason = "size_limit"

        if turns_now and reason is not None:
            segments.append(_make_segment(len(segments), turns_now, reason_now, tokens_now, config))
            turns_now, tokens_now, reason_now = [], 0, reason

        turns_now.append(turn)
        tokens_now += turn_tokens

    segments.append(_make_segment(len(segments), turns_now, reason_now, tokens_now, config))
    return segments