"""Config loading and environment overrides. Hermetic, no models needed."""

from pathlib import Path

from config.settings import PipelineConfig, load_config


def test_defaults_are_sane():
    cfg = PipelineConfig()
    assert cfg.llm.backend == "ollama"
    assert cfg.vlm.ollama_model == "llava"
    assert cfg.ollama.base_url.startswith("http")
    assert cfg.verification.max_retries >= 1


def test_default_paths_are_absolute_and_under_ml(tmp_path, monkeypatch):
    # Even when run from an unrelated cwd, default paths resolve under ml/.
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    db_path = Path(cfg.memory.db_path)
    assert db_path.is_absolute()
    assert "ml" in db_path.parts


def test_env_overrides_apply(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://example.local:1234")
    monkeypatch.setenv("ATLAS_LLM_MODEL", "custom-llm")
    monkeypatch.setenv("ATLAS_VLM_MODEL", "custom-vlm")
    monkeypatch.setenv("ATLAS_USE_VLM", "false")
    monkeypatch.setenv("ATLAS_MAX_RETRIES", "7")
    monkeypatch.setenv("ATLAS_MEMORY_ENABLED", "no")

    cfg = load_config()

    assert cfg.ollama.base_url == "http://example.local:1234"
    assert cfg.llm.ollama_model == "custom-llm"
    assert cfg.vlm.ollama_model == "custom-vlm"
    assert cfg.vlm.use_vlm is False
    assert cfg.verification.max_retries == 7
    assert cfg.memory.enabled is False


def test_absent_env_keeps_defaults(monkeypatch):
    for var in ["OLLAMA_BASE_URL", "ATLAS_LLM_MODEL", "ATLAS_MAX_RETRIES"]:
        monkeypatch.delenv(var, raising=False)
    cfg = load_config()
    assert cfg.llm.ollama_model == "llama3.2"
    assert cfg.verification.max_retries == 3
