"""
ATLAS Backend - Configuration
=============================

Environment-driven settings for the FastAPI relay. All values have safe defaults
so the server starts with no configuration at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "0.1.0"

try:
    from dotenv import load_dotenv

    # Load backend/.env and, if present, the repo-root .env (backend/.env wins).
    _here = Path(__file__).resolve().parent
    load_dotenv(_here.parent / ".env")
    load_dotenv(_here / ".env", override=True)
except Exception:
    # python-dotenv is optional; environment variables still work without it.
    pass


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class BackendConfig:
    """Runtime configuration for the ATLAS backend."""

    host: str = field(default_factory=lambda: os.getenv("ATLAS_BACKEND_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("ATLAS_BACKEND_PORT", "8000")))

    # auto: use the real agent if it imports and Ollama is reachable, else mock.
    # real: force the real agent (errors surface if unavailable).
    # mock: never load the agent; simulate progress. Useful for CI and demos.
    agent_mode: str = field(
        default_factory=lambda: os.getenv("ATLAS_AGENT_MODE", "auto").strip().lower()
    )

    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )

    # Delay between simulated steps in mock mode (seconds). Set to 0 in tests.
    mock_step_delay: float = field(
        default_factory=lambda: _get_float("ATLAS_MOCK_STEP_DELAY", 0.4)
    )

    # Comma-separated list of allowed CORS origins ("*" allows all).
    cors_origins: str = field(default_factory=lambda: os.getenv("ATLAS_CORS_ORIGINS", "*"))

    # Optional shared token. When set, a WebSocket client must authenticate with
    # {"type": "auth", "token": ...} before sending commands. Empty means open
    # (convenient for a trusted LAN; set a token to require pairing).
    auth_token: str = field(default_factory=lambda: os.getenv("ATLAS_AUTH_TOKEN", ""))

    def cors_origin_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if raw == "*" or not raw:
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


config = BackendConfig()
