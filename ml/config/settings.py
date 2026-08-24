"""
ATLAS ML Pipeline - Configuration Settings
==========================================

Central configuration for all pipeline components.
Supports both local models (llama.cpp) and Ollama.
"""

from pydantic import BaseModel
from typing import Literal
from pathlib import Path
import os

# Anchor default relative paths (models, database, screenshots) to the ml/
# package directory, not the current working directory, so the agent works no
# matter where it is launched from.
_ML_DIR = Path(__file__).resolve().parent.parent


def _env_str(name: str, default: str) -> str:
    val = os.getenv(name)
    return val if val is not None and val != "" else default


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        val = os.getenv(name)
        return float(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        val = os.getenv(name)
        return int(val) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


class OCRConfig(BaseModel):
    """EasyOCR configuration."""
    use_gpu: bool = True  # GPU enabled for speed (was False for CPU fallback)
    lang: str = "en"
    min_confidence: float = 0.3  # Minimum confidence threshold


class OllamaConfig(BaseModel):
    """Ollama server configuration."""
    base_url: str = "http://localhost:11434"
    timeout: int = 120  # Request timeout in seconds


class VLMConfig(BaseModel):
    """Vision-Language Model configuration."""
    use_vlm: bool = True  # Enable VLM
    backend: Literal["ollama", "transformers", "llama_cpp"] = "ollama"
    
    # Ollama settings
    ollama_model: str = "llava"  # User has 'llava:latest'
    
    # Transformers settings (fallback)
    hf_model_name: str = "llava-hf/llava-1.5-7b-hf"
    quantization: str = "4bit"
    
    # Generation settings
    max_new_tokens: int = 512
    temperature: float = 0.2


class LLMConfig(BaseModel):
    """Local LLM configuration."""
    backend: Literal["ollama", "llama_cpp"] = "ollama"
    
    # Ollama settings
    ollama_model: str = "llama3.2"  # User has 'llama3.2:latest'
    
    # llama.cpp settings (fallback)
    model_path: str = str(
        _ML_DIR / "models" / "downloads" / "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
    )
    n_ctx: int = 4096
    n_gpu_layers: int = -1  # -1 = use all GPU layers (was 0 for CPU only)
    
    # Generation settings
    temperature: float = 0.3
    max_tokens: int = 1024


class ScreenConfig(BaseModel):
    """Screen capture and interaction configuration."""
    capture_monitor: int = 1  # Primary monitor
    dpi_scale: float = 1.0  # Will be auto-detected
    screenshot_format: str = "png"
    mouse_move_duration: float = 0.1  # Seconds
    typing_interval: float = 0.02  # Seconds between keystrokes


class VerificationConfig(BaseModel):
    """Visual verification configuration."""
    max_retries: int = 3
    verification_delay: float = 0.5  # Wait before verification screenshot
    confidence_threshold: float = 0.7
    iou_threshold: float = 0.5  # For bounding box fusion


class MemoryConfig(BaseModel):
    """Memory/persistence configuration."""
    enabled: bool = True
    db_path: str = str(_ML_DIR / "data" / "memory.db")
    max_patterns: int = 1000


class PipelineConfig(BaseModel):
    """Master pipeline configuration."""
    ollama: OllamaConfig = OllamaConfig()
    ocr: OCRConfig = OCRConfig()
    vlm: VLMConfig = VLMConfig()
    llm: LLMConfig = LLMConfig()
    screen: ScreenConfig = ScreenConfig()
    verification: VerificationConfig = VerificationConfig()
    memory: MemoryConfig = MemoryConfig()
    
    # Global settings
    debug_mode: bool = True
    log_level: str = "INFO"
    save_screenshots: bool = True
    screenshots_dir: str = str(_ML_DIR / "data" / "screenshots")


def load_config() -> PipelineConfig:
    """
    Build configuration from defaults, then apply environment overrides.

    A .env file in the ml/ directory (or the repo root) is loaded first if
    python-dotenv is available. Recognized variables:

      OLLAMA_BASE_URL, ATLAS_LLM_MODEL, ATLAS_VLM_MODEL, ATLAS_LLM_BACKEND,
      ATLAS_VLM_BACKEND, ATLAS_USE_VLM, ATLAS_USE_GPU, ATLAS_CAPTURE_MONITOR,
      ATLAS_MAX_RETRIES, ATLAS_LOG_LEVEL, ATLAS_DEBUG, ATLAS_SAVE_SCREENSHOTS,
      ATLAS_MEMORY_ENABLED, ATLAS_MEMORY_DB.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(_ML_DIR.parent / ".env")
        load_dotenv(_ML_DIR / ".env", override=True)
    except Exception:
        # python-dotenv is optional; plain environment variables still apply.
        pass

    cfg = PipelineConfig()

    # Ollama
    cfg.ollama.base_url = _env_str("OLLAMA_BASE_URL", cfg.ollama.base_url)

    # LLM
    cfg.llm.backend = _env_str("ATLAS_LLM_BACKEND", cfg.llm.backend)  # type: ignore[assignment]
    cfg.llm.ollama_model = _env_str("ATLAS_LLM_MODEL", cfg.llm.ollama_model)

    # VLM
    cfg.vlm.backend = _env_str("ATLAS_VLM_BACKEND", cfg.vlm.backend)  # type: ignore[assignment]
    cfg.vlm.ollama_model = _env_str("ATLAS_VLM_MODEL", cfg.vlm.ollama_model)
    cfg.vlm.use_vlm = _env_bool("ATLAS_USE_VLM", cfg.vlm.use_vlm)

    # OCR / screen
    cfg.ocr.use_gpu = _env_bool("ATLAS_USE_GPU", cfg.ocr.use_gpu)
    cfg.screen.capture_monitor = _env_int("ATLAS_CAPTURE_MONITOR", cfg.screen.capture_monitor)

    # Verification
    cfg.verification.max_retries = _env_int("ATLAS_MAX_RETRIES", cfg.verification.max_retries)

    # Memory
    cfg.memory.enabled = _env_bool("ATLAS_MEMORY_ENABLED", cfg.memory.enabled)
    cfg.memory.db_path = _env_str("ATLAS_MEMORY_DB", cfg.memory.db_path)

    # Global
    cfg.log_level = _env_str("ATLAS_LOG_LEVEL", cfg.log_level)
    cfg.debug_mode = _env_bool("ATLAS_DEBUG", cfg.debug_mode)
    cfg.save_screenshots = _env_bool("ATLAS_SAVE_SCREENSHOTS", cfg.save_screenshots)

    return cfg


# Global config instance
config = load_config()
