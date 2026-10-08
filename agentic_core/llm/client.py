from dataclasses import dataclass
import ollama
from .config import LLMConfig, load_config


@dataclass
class LLMResult:
    text: str
    tokens_out: int
    tpot_ms: float   # time per output token, in milliseconds
    total_s: float


class LLMClient:
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or load_config()
        self._client = ollama.Client(host=self.config.host)

    def is_ready(self) -> bool:
        """True if Ollama is running and our model is downloaded."""
        try:
            names = [m.model for m in self._client.list().models]
        except Exception:
            return False
        return self.config.model in names

    def chat(self, user_prompt: str, system_prompt: str | None = None) -> LLMResult:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = self._client.chat(
            model=self.config.model,
            messages=messages,
            options={
                "num_ctx": self.config.num_ctx,
                "temperature": self.config.temperature,
                "num_predict": self.config.num_predict,
            },
            keep_alive=self.config.keep_alive,
        )

        tokens = response.eval_count or 0
        eval_ns = response.eval_duration or 0
        tpot = (eval_ns / 1e6 / tokens) if tokens else 0.0
        
        return LLMResult(
            text=response.message.content,
            tokens_out=tokens,
            tpot_ms=tpot,
            total_s=(response.total_duration or 0) / 1e9,
        )