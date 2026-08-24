# ATLAS Architecture

This document describes how the ATLAS components fit together and how a single
command flows through the system.

## System shape

ATLAS is a monorepo of five deployable pieces plus a landing page:

| Component | Path | Runtime | Role |
|-----------|------|---------|------|
| ML Pipeline | `ml/` | Python + Ollama | Vision-driven desktop agent |
| MCP Browser Agent | `ml/mcp/` | Python + Node + Chrome | Web automation |
| Backend | `backend/` | Python (FastAPI) | Relay and agent bridge |
| Frontend | `frontend/` | Rust (Tauri) + Next.js | Desktop launcher |
| Companion App | `companion-app/` | Flutter | Mobile client |
| Landing page | `landing-page/` | Static HTML/CSS | Public page |

The backend is the integration hub. The frontend launcher and the MCP browser
agent are independent tools that do not depend on the backend.

## Command flow (phone to desktop)

```
Phone (Flutter)                Backend (FastAPI)              Desktop agent (ml/)
--------------                 -----------------              -------------------
1. GET /health           ----> verify reachable
2. open ws://host/ws     ----> accept, send "connected"
3. {"type":"command"}    ----> AgentBridge.run_task
                                  |  auto: real or mock
                                  v
                               real: AgentLoop.run(command)
                                  |  perceive -> plan -> act -> verify
4. {"type":"progress"}   <----   (streamed from agent logs)
   ...                   <----   ...
5. {"type":"result"}     <----   success or failure
```

In `mock` mode (the default in containers and CI) the bridge simulates the
perceive, plan, act, and verify steps instead of driving a real desktop, so the
whole path is exercisable without a GUI or Ollama.

## ML pipeline internals

The agent loop (`ml/agent/agent_loop.py`) implements
`PERCEIVE -> UNDERSTAND -> PLAN -> ACT -> VERIFY`:

- **Perceive**: `mss` captures the screen; EasyOCR extracts text and boxes;
  optional LLaVA adds UI regions; `bbox_fusion` merges them into elements.
- **Understand and plan**: Llama 3.2 (via Ollama) extracts intent, builds a step
  plan, and picks one atomic action per step.
- **Act**: the planned action is resolved to absolute coordinates through
  `ScreenFrame.to_absolute` (which applies the monitor offset and DPI awareness),
  then executed with PyAutoGUI.
- **Verify**: an OpenCV visual diff plus OCR checks confirm the action took
  effect; failures route through LLM-guided recovery (retry, skip, or abort).
- **Memory**: successful patterns are stored in SQLite and used to boost
  confidence on future lookups.

Robustness modules address the previously open critical issues: DPI awareness is
set at startup, `perception/modal_detection.py` flags blocking dialogs,
`perception/window_state.py` focuses the target window, and the monitor offset is
carried on every frame so clicks land correctly on non-primary monitors.

## Backend internals

- `server.py` defines the REST endpoints and the `/ws` WebSocket, and translates
  socket messages into calls on the agent bridge.
- `agent_bridge.py` owns the agent lifecycle. It resolves a mode (`auto`, `real`,
  `mock`), and for real runs it executes the synchronous agent in a worker thread
  while forwarding its log lines as `progress` events, so no change to the agent
  is required.
- `config.py` reads all settings from the environment with safe defaults.

## Frontend internals

The Tauri Rust layer (`src-tauri/src/lib.rs`) indexes Start Menu shortcuts,
Program Files executables, and common user folders on a background thread, then
serves the cached list to the Next.js UI over Tauri IPC. A global shortcut toggles
the overlay window. The UI is a static Next.js export embedded in the app.

## MCP browser agent internals

The agent launches the Node `@playwright/mcp` server over stdio, discovers its
browser tools, and runs an LLM-driven loop: the model calls a tool, MCP executes
it in Chrome over CDP, the result feeds back, and the loop repeats until the task
finishes. Three LLM backends are supported (Gemini, OpenAI-compatible, local
llama.cpp), selected by `LLM_BACKEND`.

## Deployment notes

- The backend ships a Dockerfile and a root `docker-compose.yml`. In a container
  it runs in mock mode by default because there is no desktop session; point it at
  a host Ollama and a real desktop to run for real.
- The frontend produces a static export consumed by the Tauri bundler; the desktop
  app is built with `npm run tauri:build`.
- The landing page is static and deploys to any static host, including GitHub
  Pages (a `.nojekyll` file is included).
- CI builds and tests every component on each push and pull request.
