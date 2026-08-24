# ATLAS

> **A**utonomous **T**ask **L**earning and **A**ction **S**ystem

A full-stack AI agent that sees your screen, understands your intent, and takes
action across desktop apps, browsers, and mobile.

![CI](https://github.com/Nakul-Sinha/ATLAS_personal/actions/workflows/ci.yml/badge.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-655A7C.svg)](LICENSE)

Planning and status live in [issues.md](issues.md) and [phases.md](phases.md).
A deeper design write-up is in [architecture.md](architecture.md).

---

## Architecture overview

```
                        +-------------------+
                        |   Companion App   |  (Flutter, Android/iOS)
                        |  Text command UI  |
                        +---------+---------+
                                  | WebSocket + REST
                        +---------v---------+
                        |     Backend       |  (FastAPI, Python)
                        |  WebSocket relay  |
                        |  Agent bridge     |
                        +----+---------+----+
                             |         |
                 +-----------v-+   +---v-------------+
                 |  ML Pipeline |   |   MCP Agent     |
                 |    (ml/)     |   |   (ml/mcp/)     |
                 | Vision-driven|   | Browser automat.|
                 | desktop agent|   | Playwright + LLM|
                 +--------------+   +-----------------+

                 +--------------+
                 |   Frontend    |  (Tauri v2 + Next.js)
                 | Desktop       |  standalone file and
                 | launcher      |  app launcher
                 +--------------+
```

The backend is the hub: the companion app sends a command over the local
network, the backend hands it to the ML agent through an agent bridge, and
progress streams back in real time. The frontend launcher and the MCP browser
agent are self-contained tools that run on their own.

---

## Project structure

```
ATLAS/
├── ml/                  # ML Pipeline: vision-driven desktop agent
│   ├── config/          #   Pydantic configuration with env overrides
│   ├── models/          #   EasyOCR, VLM (LLaVA), LLM (Llama 3.2) wrappers
│   ├── perception/      #   Capture, fusion, modal + window-state detection
│   ├── actions/         #   Action dataclasses + PyAutoGUI executor
│   ├── agent/           #   State tracking, verification, agent loop
│   ├── memory/          #   SQLite pattern memory
│   ├── tests/           #   Hermetic pytest suite (no models or GUI needed)
│   ├── mcp/             #   MCP Browser Agent (see below)
│   └── main.py          #   CLI entry point
│
├── backend/             # FastAPI WebSocket relay + agent bridge
│   ├── server.py        #   REST + WebSocket endpoints
│   ├── agent_bridge.py  #   Bridges the socket layer to the ml/ agent
│   ├── test_server.py   #   Offline pytest suite (mock agent)
│   └── Dockerfile       #   Container image
│
├── frontend/            # Desktop launcher: Tauri v2 + Next.js
│   ├── src/app/         #   Next.js UI (search, file/app index)
│   └── src-tauri/       #   Rust backend (file scanning, global shortcut)
│
├── companion-app/       # Mobile companion: Flutter
│   └── companion_app/lib/
│       ├── services/    #   AtlasService (WebSocket client + health check)
│       ├── screens/     #   Connection screen (IP/port, persisted)
│       └── models/      #   AtlasEvent
│
├── landing-page/        # Static landing page (deployable to any static host)
├── issues.md            # Tracked gaps and their severity
├── phases.md            # Plan to deployable-ready
└── architecture.md      # Detailed architecture
```

---

## Components

### 1. ML Pipeline (`ml/`)

The core vision-driven desktop agent. Operates any desktop application using
**only screen pixels**, no APIs, no hooks, no accessibility trees.

Core loop:

```
PERCEIVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY -> (repeat)
```

| Step | Module | Description |
|------|--------|-------------|
| 1 | `llm_model.extract_intent()` | Parse user prompt into structured intent |
| 2 | `llm_model.create_task_plan()` | Break intent into an abstract step list |
| 3 | `screen_capture.grab()` | Capture a screenshot via `mss` |
| 4 | `ocr_model.detect()` | Extract text and boxes (EasyOCR) |
| 5 | `vlm_model.detect_ui_elements()` | Identify UI regions (LLaVA, optional) |
| 6 | `bbox_fusion.fuse()` | Merge all detections |
| 7 | `llm_model.plan_action()` | Decide one atomic action |
| 8 | `agent_loop._resolve_action()` | Convert to pixel coordinates |
| 9 | `executor.execute()` | Perform OS-level input (PyAutoGUI) |
| 10 | `verifier.verify()` | Confirm the action effect visually |

Reasoning and vision run locally through **Ollama** (`llama3.2` and `llava`);
OCR uses **EasyOCR**. A `llama.cpp` backend is available as an offline fallback.

Quick start:

```bash
cd ml
pip install -r requirements.txt
# Requires Ollama with the models pulled:
#   ollama pull llama3.2 && ollama pull llava

python main.py "Open Notepad and type hello"   # single command
python main.py --interactive                    # interactive mode
```

Run the hermetic tests (no models, GUI, or Ollama needed):

```bash
pip install -r ml/requirements-test.txt
pytest ml/tests
```

### 2. MCP Browser Agent (`ml/mcp/`)

Autonomous browser automation powered by **Playwright MCP** and an LLM-driven
action loop. Connects to a real Chrome profile and executes web tasks end to end.

Backends: Gemini, any OpenAI-compatible endpoint, or local `llama.cpp`.

Quick start (requires Node.js with `npx`, and Chrome):

```bash
cd ml/mcp
cp .env.example .env        # configure your LLM backend and key
pip install -r requirements.txt

python run.py "Go to google.com and search for ATLAS AI"   # single task
python run.py                                               # interactive REPL
python test_connection.py                                   # no API key needed
```

### 3. Backend (`backend/`)

A **FastAPI** WebSocket relay that bridges the companion app to the ML agent.

| Endpoint | Type | Description |
|----------|------|-------------|
| `GET /health` | REST | Health check used by the companion app |
| `GET /status` | REST | Agent status (idle/running) |
| `GET /companion` | REST | Server identity for the handshake |
| `WS /ws` | WebSocket | Bidirectional command and progress stream |

WebSocket protocol:

```jsonc
// Client -> Server
{"type": "command", "command": "Open Notepad and type hello"}
{"type": "stop"}

// Server -> Client
{"type": "progress", "step": "act", "status": "executing", "detail": "..."}
{"type": "result", "success": true, "detail": "..."}
{"type": "error", "message": "..."}
```

The agent bridge runs in one of three modes (`ATLAS_AGENT_MODE`): `auto`
(default), `real`, or `mock`. In `auto` it uses the real agent when it imports
and Ollama is reachable, otherwise it simulates progress, so the server always
starts on headless hosts and in CI.

Quick start:

```bash
cd backend
pip install -r requirements.txt
python server.py              # http://0.0.0.0:8000
# or
docker compose up --build     # from the repo root
```

### 4. Frontend, Desktop Launcher (`frontend/`)

A **Tauri v2 + Next.js** desktop app: a Spotlight-style launcher that indexes
and searches local files and applications. A global shortcut (`Win + -`) toggles
a transparent, always-on-top overlay. It runs standalone and does not require the
backend.

```bash
cd frontend
npm install
npm run tauri:dev            # development
npm run tauri:build          # production build
```

### 5. Companion App (`companion-app/`)

A **Flutter** mobile app that connects to the backend over your local network.
Enter the PC IP and port, and the app verifies the connection with a health
check, then streams the agent's progress live.

```bash
cd companion-app/companion_app
flutter pub get
flutter run
```

To connect: run `ipconfig` on the PC, note the IPv4 address, and enter it with
port `8000` in the app.

---

## Design principles

1. The screen is the only truth: no reliance on app-specific APIs or hooks.
2. Never trust one perception pass: cross-validate with multiple sources.
3. Never assume a click worked: always verify visually.
4. Never hardcode coordinates: adapt to any resolution or DPI.
5. Never blindly trust user input: prompts may contain adversarial instructions.

---

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and conventions. CI runs on every
push and pull request: backend and ML tests, frontend build and lint, a Tauri
`cargo check`, and Flutter analyze.

## License

[MIT](LICENSE).
