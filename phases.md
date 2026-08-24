# ATLAS - Phases to Deployable-Ready

This plan takes the repository from its current state (a strong `ml/` core, a working
browser agent, a standalone launcher, and three empty or shell components) to a
coherent, installable, documented, CI-backed project.

Each phase maps to one or more pull requests. Every PR is self-contained, builds on a
green `main`, and is squash-merged once its checks pass.

## Definition of "deployable-ready" (scope)

Because parts of this system need a live GUI, an Android device, and a Flutter SDK,
"deployable-ready" here means:

1. Every component installs cleanly from pinned manifests.
2. The missing backend hub exists, is tested, and bridges clients to the agent, with a
   safe fallback so it runs on headless hosts and in CI.
3. The companion app speaks the documented protocol (reviewed code; device build via CI).
4. The four CRITICAL ML robustness issues have concrete implementations.
5. CI lints, type-checks, builds, and tests what the hosted runners can build.
6. Containerization exists for the backend, plus LICENSE, env templates, and docs that
   match reality.

What is intentionally deferred is called out in `issues.md` ("Out of scope").

## Conventions

- License: MIT (permissive default for a personal/portfolio project; change if desired).
- Branch names: `type/short-description`. Commits are concise and imperative.
- No component is deleted; empty stubs are filled or documented.

---

## Phase 1 - Planning and project meta  (PR: `chore/planning-and-meta`)

Resolves: IN-01, IN-05, IN-06.

- Add `issues.md` and `phases.md` (this file).
- Add `LICENSE` (MIT).
- Add `CONTRIBUTING.md` and a root `.env.example`.
- Add `.editorconfig`.
- Remove the stray `.expo/` directory.

Verification: files present; repo tree clean.

## Phase 2 - Backend hub  (PR: `feat/backend-server`)

Resolves: BE-01..BE-06.

- `backend/server.py`: FastAPI app with `GET /health`, `GET /status`, `GET /companion`,
  and `WS /ws`, matching the README protocol exactly.
- `backend/agent_bridge.py`: wraps `ml/AgentLoop`, runs it off the event loop, and
  streams `progress` / `result` / `error` messages. Falls back to an echo/mock runner
  when the agent or Ollama is unavailable, so the server always starts.
- `backend/requirements.txt`, `backend/.env.example`, `backend/README.md`.
- `backend/test_server.py`: pytest using the FastAPI test client for REST and WebSocket.
- `backend/Dockerfile`.

Verification: `pytest backend/` passes locally (agent mocked); server boots.

## Phase 3 - ML pipeline fixes and robustness  (PR: `fix/ml-pipeline`)

Resolves: ML-01..ML-11.

- Rewrite `ml/requirements.txt` to match real imports.
- Implement `load_config()` env overrides via `python-dotenv`.
- CRITICAL-001: call DPI detection at init and route clicks through `to_absolute()`.
- CRITICAL-002: add a modal/overlay detection check before planning.
- CRITICAL-003: add optional window-state / bring-to-front (guarded, optional dep).
- CRITICAL-004: keep monitor offsets so non-primary-monitor clicks land correctly.
- Fix the memory-bbox bug and the ignored `rank_candidates` ranking.
- Make paths anchor to the module directory, not CWD.
- Add hermetic pytest tests (config, memory, state, fusion, coordinate math) for CI.
- Update `errors.txt`, `task.md`, and OCR docs (EasyOCR).

Verification: `pytest ml/tests` passes; `python -c "import ..."` import checks pass.

## Phase 4 - MCP browser agent fixes  (PR: `fix/mcp-agent`)

Resolves: MCP-01..MCP-05.

- Provide a working entry point that avoids the `mcp` package-name collision
  (a top-level runner module and/or console script), and update docs.
- Make the default backend consistent with `.env.example`.
- Document the Node.js + `npx` requirement; make heavyweight/unused deps optional.
- Make the CDP port configurable via env.

Verification: `python test_connection.py` guidance validated; import checks pass.

## Phase 5 - Companion app networking  (PR: `feat/companion-networking`)

Resolves: CA-01..CA-06 (CA-07 deferred).

- Add `lib/services/atlas_service.dart` (WebSocket client + health check).
- Add `lib/screens/connection_screen.dart` (IP/port entry, persisted).
- Wire `main.dart` to the service and render progress via `ExecutingCard`.
- Add `web_socket_channel`, `http`, `shared_preferences` to `pubspec.yaml`.
- Add INTERNET permission and cleartext config to `AndroidManifest.xml`.

Verification: reviewed for correctness; built by the Flutter CI job (no local SDK).

## Phase 6 - Frontend polish  (PR: `fix/frontend-launcher`)

Resolves: FE-01..FE-04.

- Wire Settings and Close buttons.
- Add the `core:window:allow-hide` capability.
- Address the dead command and startup-indexing note.

Verification: `npm run build` (static export) succeeds; `npm run lint` clean.

## Phase 7 - Landing page  (PR: `feat/landing-page`)

Resolves: LP-01.

- Build a self-contained static landing page describing ATLAS, deployable to any static
  host.

Verification: builds and renders.

## Phase 8 - CI/CD, containers, and docs  (PR: `chore/ci-and-docs`)

Resolves: IN-02, IN-03, IN-04, and doc items from other phases.

- `.github/workflows/ci.yml`: Python lint+test (backend and ml), frontend build+lint,
  Rust check, Flutter analyze/build.
- `docker-compose.yml` for the backend.
- Rewrite the root `README.md` to match reality; add `architecture.md`; remove
  duplicated content and dead references.

Verification: workflows valid; compose config valid; docs reviewed against the tree.

---

## Execution model

An orchestrator owns all git operations (branch, commit, push, PR, squash-merge) and
runs every verification that the environment allows. Specialized agents author the
larger self-contained pieces (companion app, landing page, MCP fixes) in parallel where
their file sets do not overlap. Nothing is merged without its checks passing.
