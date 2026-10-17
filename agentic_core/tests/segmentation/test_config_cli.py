from pathlib import Path

import pytest

from agentic_core.segmentation.cli import main
from agentic_core.segmentation.config import load_config
from agentic_core.segmentation.segmenter import SegmentationConfig

SAMPLE = Path(__file__).resolve().parents[2] / "datasets" / "segmentation" / "sample_standup.md"


def _write(tmp_path, text):
    path = tmp_path / "settings.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_yaml_file_matches_code_defaults():
    assert load_config() == SegmentationConfig()


def test_custom_values_are_loaded(tmp_path):
    config = load_config(_write(tmp_path, "long_pause_s: 90\ncue_pause_s: 10\nmax_segment_tokens: 800\n"))
    assert config.long_pause_s == 90
    assert config.cue_pause_s == 10
    assert config.max_segment_tokens == 800


def test_empty_file_gives_defaults(tmp_path):
    assert load_config(_write(tmp_path, "")) == SegmentationConfig()


def test_unknown_setting_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown setting"):
        load_config(_write(tmp_path, "long_paus_s: 90\n"))


@pytest.mark.parametrize("value", ['"abc"', "true"])
def test_non_number_is_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="must be a number"):
        load_config(_write(tmp_path, f"long_pause_s: {value}\n"))


def test_contradicting_settings_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="must not be larger"):
        load_config(_write(tmp_path, "long_pause_s: 10\ncue_pause_s: 20\n"))


def test_missing_settings_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_cli_prints_three_segments(capsys):
    code = main([str(SAMPLE)])
    out = capsys.readouterr().out
    assert code == 0
    assert "3 segments" in out
    assert "started_because=cue_and_pause" in out
    assert "Great, I will review it after this call." in out


def test_cli_summary_hides_the_text(capsys):
    code = main([str(SAMPLE), "--summary"])
    out = capsys.readouterr().out
    assert code == 0
    assert "3 segments" in out
    assert "Great, I will review it after this call." not in out


def test_cli_missing_transcript_gives_clear_error(capsys):
    code = main(["does_not_exist.md"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_cli_bad_transcript_gives_clear_error(tmp_path, capsys):
    bad = tmp_path / "bad.md"
    bad.write_text("this is wrong", encoding="utf-8")
    code = main([str(bad)])
    assert code == 1
    assert "not a valid turn" in capsys.readouterr().err