from agentic_core.llm.config import load_config


# a quick automatic check that the config loads and respects your hardware rules.

def test_config_loads_and_respects_limits():
    cfg = load_config()
    assert cfg.model.startswith("llama3")
    assert cfg.temperature == 0.0
    assert cfg.num_ctx <= 4096