from dataclasses import dataclass
from pathlib import Path
import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml" # path to the config.yaml file


@dataclass(frozen=True)
class LLMConfig:
    model: str
    host: str
    num_ctx: int
    temperature: float
    num_predict: int
    keep_alive: str


def load_config(path: Path = CONFIG_PATH) -> LLMConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return LLMConfig(**data)