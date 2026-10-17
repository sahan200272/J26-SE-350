from dataclasses import fields
from pathlib import Path

import yaml

from agentic_core.segmentation.segmenter import SegmentationConfig

CONFIG_PATH = Path(__file__).parent / "config.yaml"  # path to the config.yaml file


def load_config(path: Path = CONFIG_PATH) -> SegmentationConfig:
    """Read the segmentation settings. Raises ValueError for unknown or bad values."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:  # an empty file means "use the defaults"
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected 'name: value' lines")

    allowed = {field.name for field in fields(SegmentationConfig)}
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(f"{path}: unknown setting(s): {', '.join(unknown)}")

    for name, value in data.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}: setting '{name}' must be a number, got {value!r}")

    return SegmentationConfig(**data)