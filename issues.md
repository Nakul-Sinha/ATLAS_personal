# ATLAS - Issues

Tracked gaps that stand between the current repository and a deployable, functional
project. Grouped by component. Each issue has an ID, severity, and the phase that
resolves it (see `phases.md`).

Severity legend:
- P0: blocks the project from running or building at all
- P1: blocks the advertised end-to-end flow or a clean install
- P2: robustness, correctness, or polish
- P3: docs, hygiene, nice-to-have

Status legend: OPEN, IN PROGRESS, DONE.

---

## A. Backend hub (`backend/`)

The FastAPI WebSocket relay described in the README does not exist. The directory
contains only an empty `.init` file. This is the single largest gap: the companion
app and the advertised architecture both depend on it.

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| BE-01 | P0 | `backend/server.py` is missing entirely; no FastAPI app, no `/health`, `/status`, `/companion`, `/ws`. | 2 | OPEN |
| BE-02 | P0 | No `backend/requirements.txt`; nothing to install. | 2 | OPEN |
| BE-03 | P1 | No bridge from the WebSocket layer to the `ml/` `AgentLoop`; commands cannot reach the agent. | 2 | OPEN |
| BE-04 | P1 | No graceful degradation when Ollama or a desktop session is unavailable (needed so the server runs in CI and on headless hosts). | 2 | OPEN |
| BE-05 | P1 | No automated tests for the server (REST + WebSocket). | 2 | OPEN |
| BE-06 | P2 | No `backend/.env.example`, no `backend/README.md`, no containerization. | 2, 8 | OPEN |

## B. Companion app (`companion-app/`)

A static Flutter UI shell. Every networking, voice, and persistence feature in the
README is unbuilt.

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| CA-01 | P1 | No WebSocket client (`AtlasService`); the search box does nothing. | 5 | OPEN |
| CA-02 | P1 | No connection screen for entering the PC IP and port, and no health-check handshake. | 5 | OPEN |
| CA-03 | P1 | No persistence of connection settings (`shared_preferences` not present). | 5 | OPEN |
| CA-04 | P2 | `lib/executing_card.dart` is dead code, never imported. | 5 | OPEN |
| CA-05 | P2 | `pubspec.yaml` is missing `web_socket_channel`, `http`, `shared_preferences`. | 5 | OPEN |
| CA-06 | P1 | `AndroidManifest.xml` lacks INTERNET permission and cleartext allowance for LAN `ws://`. | 5 | OPEN |
| CA-07 | P3 | Voice input advertised but not implemented (deferred: needs device testing). | 5 | OPEN |

## C. ML pipeline (`ml/`)

Core loop is implemented and runs against Ollama on a live Windows desktop, but the
package is not installable as-is and the four CRITICAL robustness issues are open.

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| ML-01 | P0 | `requirements.txt` omits imported packages (`easyocr`, `requests`, `huggingface_hub`) and lists unused ones (`paddleocr`, `paddlepaddle`, `transformers`, `accelerate`, `bitsandbytes`, `langgraph`). A clean install does not work. | 3 | OPEN |
| ML-02 | P1 | `load_config()` ignores the environment (`TODO: Load from .env`); every setting is hardcoded. | 3 | OPEN |
| ML-03 | P1 | CRITICAL-001 DPI scaling: `detect_dpi_scale()` exists but is never called, and `_resolve_action` bypasses `to_absolute()`, so DPI scaling is inert. | 3 | OPEN |
| ML-04 | P1 | CRITICAL-002 modal/dialog detection: absent. | 3 | OPEN |
| ML-05 | P1 | CRITICAL-003 window-state / bring-to-front: absent. | 3 | OPEN |
| ML-06 | P1 | CRITICAL-004 multi-monitor: monitor offsets discarded in `grab()`, so clicks land wrong on non-primary monitors. | 3 | OPEN |
| ML-07 | P2 | `_store_success_pattern` records `fused_elements[0]` instead of the acted-on element. | 3 | OPEN |
| ML-08 | P2 | `rank_candidates` result is discarded; `_resolve_action` uses original order. | 3 | OPEN |
| ML-09 | P2 | Config paths are CWD-relative, so the agent only works when launched from `ml/`. | 3 | OPEN |
| ML-10 | P2 | Tests are live-desktop scripts, not hermetic; nothing runs in CI. | 3 | OPEN |
| ML-11 | P3 | Stale docs: code uses EasyOCR, docs still say PaddleOCR; `errors.txt` table shows all issues OPEN. | 3, 8 | OPEN |

## D. MCP browser agent (`ml/mcp/`)

Fully implemented, but the documented entry point is broken and defaults are
inconsistent.

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| MCP-01 | P1 | `python -m mcp` collides with the installed `mcp` SDK package name; the documented command does not run reliably. | 4 | OPEN |
| MCP-02 | P2 | Default `LLM_BACKEND=gemini` contradicts `.env.example` (openai/OpenRouter); no-config runs raise. | 4 | OPEN |
| MCP-03 | P2 | Node.js + `npx` is a hard requirement but is undocumented in `requirements.txt`; only surfaces as a runtime error. | 4 | OPEN |
| MCP-04 | P2 | Unused `playwright` Python dependency; heavyweight `llama-cpp-python` forces a source build. | 4 | OPEN |
| MCP-05 | P3 | CDP port `9222` is hardcoded, not configurable. | 4 | OPEN |

## E. Frontend launcher (`frontend/`)

Compiles and runs standalone on Windows. Minor functional gaps.

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| FE-01 | P2 | Title-bar Settings and Close buttons have no handlers. | 6 | OPEN |
| FE-02 | P2 | `core:window:allow-hide` capability is missing, so Escape-to-hide is denied at runtime. | 6 | OPEN |
| FE-03 | P3 | `search_items` Tauri command is dead code (filtering is client-side). | 6 | OPEN |
| FE-04 | P3 | Startup indexing runs synchronously on the main thread before first paint. | 6 | OPEN |

## F. Landing page (`landing-page/`)

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| LP-01 | P2 | Empty directory; no landing page exists. | 7 | OPEN |

## G. Project infrastructure and docs

| ID | Sev | Issue | Phase | Status |
|----|-----|-------|-------|--------|
| IN-01 | P1 | No LICENSE; the project is unlicensed and cannot be released. | 1 | OPEN |
| IN-02 | P1 | No CI: no linting, type-checking, build, or test automation. | 8 | OPEN |
| IN-03 | P2 | No containerization for the backend and no compose file. | 8 | OPEN |
| IN-04 | P2 | README is out of sync: references nonexistent `ml_2/`, `architecture.md`, `backend/server.py`, and companion `services/`/`screens/`; the architecture diagram and a section are duplicated. | 8 | OPEN |
| IN-05 | P3 | No `CONTRIBUTING.md`, no root `.env.example`, no `.editorconfig`. | 1 | OPEN |
| IN-06 | P3 | Stray `.expo/` directory is unrelated tooling cruft. | 1 | OPEN |

---

## Out of scope for this pass (documented, not fully verified here)

The following require hardware or SDKs not available in the build environment and are
delivered as reviewed code plus CI wiring rather than live-verified runs:

- Flutter compilation and on-device behavior (no Flutter SDK present).
- The GUI-driving desktop agent end to end (no interactive display for `pyautogui`/`mss`).
- Voice input on a physical device (CA-07).

These are wired into CI where a hosted runner can build them, and documented so a
maintainer with the hardware can validate.
