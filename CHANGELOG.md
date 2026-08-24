# Changelog

All notable changes to ATLAS are recorded here. Dates are in ISO format.

## [0.1.0] - 2026-08-25

First coherent, installable, tested release. The project went from a set of
partly-built components to a working full stack.

### Added
- **Backend relay** (`backend/`): a FastAPI server with `/health`, `/status`,
  `/companion`, and a `/ws` WebSocket that streams `progress` / `result` / `error`.
- **Agent bridge** with `auto` / `real` / `mock` / `plan` modes. The real agent runs
  as an isolated subprocess (`ml/agent_runner.py`), so the backend can drive it without
  import collisions, and a stop terminates it.
- **Plan (dry run) mode**: preview what the agent would do without executing OS input.
- **Companion app networking**: WebSocket client, connection screen with health check and
  persistence, voice input (speech-to-text), and LAN auto-discovery.
- **Desktop launcher**: functional Settings / Close / Quit, background indexing, and an
  Agent console wired to the backend.
- **ML robustness**: DPI awareness, modal detection, window focus, multi-monitor offset,
  error taxonomy, chunked unicode-safe typing, multi-app context switching, a VLM cache,
  and text-free icon matching. Optional OCR + VLM cross-validation.
- **Landing page**: a minimal single-card static site.
- **Infrastructure**: GitHub Actions CI across all stacks, a backend Dockerfile and
  `docker-compose.yml`, an MIT license, `ruff` config, env templates, and hermetic tests
  (backend and ml).

### Fixed
- The default Ollama backend no longer requires a local llama.cpp model file, so a fresh
  install runs.
- The backend can now actually reach the real agent (previously a `config` module-name
  collision made real mode silently unreachable).
- The ML pipeline installs from a correct `requirements.txt`.

### Known limitations
- The end-to-end GUI-driving run and the mobile app on-device are validated by CI and
  live reasoning checks, not a full hardware run in this environment.
- Real backend mode needs the ml dependencies installed in the backend's Python
  environment (documented in `backend/README.md`).
