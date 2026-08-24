"""LLM backend selection. The default Ollama path must not need a local GGUF."""

from config.settings import LLMConfig
from models.llm_model import LLMModel


def test_ollama_backend_load_is_noop_and_needs_no_model_file():
    # The documented default. load() must not raise or require a GGUF, because
    # generation talks to the Ollama server over HTTP.
    llm = LLMModel(LLMConfig(backend="ollama"))
    llm.load()
    assert llm._model is None


def test_llama_cpp_backend_still_attempts_local_load():
    # With the fallback backend and a missing model file, load() should raise,
    # proving the branch is still wired (it just is not the default path).
    llm = LLMModel(LLMConfig(backend="llama_cpp", model_path="/does/not/exist.gguf"))
    raised = False
    try:
        llm.load()
    except Exception:
        raised = True
    assert raised
