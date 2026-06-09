# ATLAS

> **A**utonomous **T**ask **L**earning & **A**ction **S**ystem

A full-stack AI agent that sees your screen, understands your intent, and takes action — across desktop apps, browsers, and mobile.

---

##  Architecture Overview

```
                        ┌──────────────────┐
                        │   Companion App   │  (Flutter · Android/iOS)
                        │  Voice + Text UI  │
                        └────────┬─────────┘
                                 │ WebSocket
                        ┌────────▼─────────┐
                        │     Backend       │  (FastAPI · Python)
                        │  WebSocket relay  │
                        │  Agent orchestr.  │
                        └──┬───────────┬───┘
                           │           │
              ┌────────────▼──┐   ┌────▼────────────┐
              │    ML Pipeline │   │   MCP Agent      │
              │  (ml/ · ml_2/) │   │  (ml/mcp/)       │
              │  Vision-driven │   │  Browser automat. │
              │  desktop agent │   │  Playwright+LLM   │
              └────────────────┘   └──────────────────┘
                           │
                  ┌────────▼─────────┐
                  │    Frontend       │  (Tauri v2 + Next.js)
                  │  Desktop launcher │
                  │  File & app index │
                  └──────────────────┘
```

---

##  Project Structure

```
ATLAS/
├── ml/                  # ML Pipeline v1 — Vision-driven desktop agent
│   ├── config/          #   Pydantic configuration management
│   ├── models/          #   OCR, VLM (LLaVA), LLM (Mistral/Phi) wrappers
│   ├── perception/      #   Screen capture, bbox fusion, perception engine
│   ├── actions/         #   Action dataclasses + PyAutoGUI executor
│   ├── agent/           #   State tracking, verification, main agent loop
│   ├── memory/          #   SQLite pattern memory
│   ├── mcp/             #   MCP Browser Agent (see below)
│   └── main.py          #   CLI entry point
│
├── ml_2/                # ML Pipeline v2 — Enhanced vision agent
│   ├── config/          #   Updated configuration
│   ├── models/          #   Refined OCR, VLM, LLM model wrappers
│   ├── perception/      #   Improved screen capture + bbox fusion
│   ├── actions/         #   Enhanced action execution
│   ├── agent/           #   Improved agent loop with better verification
│   ├── memory/          #   Pattern memory storage
│   ├── test_*.py        #   Phased test suites (unit → integration → e2e)
│   └── main.py          #   CLI entry point
│
├── ml/mcp/              # MCP Browser Agent — Autonomous web automation
│   ├── browser_agent.py #   Playwright MCP + LLM action loop
│   ├── llm_backend.py   #   Multi-backend LLM (Gemini / OpenAI / llama.cpp)
│   ├── config.py        #   Pydantic config with .env support
│   └── __main__.py      #   CLI entry point (interactive + single-task)
│
├── backend/             # WebSocket Backend — Agent orchestration server
│   ├── server.py        #   FastAPI app with REST + WebSocket endpoints
│   └── test_*.py        #   Connection and command tests
│
├── frontend/            # Desktop Launcher — Tauri v2 + Next.js 16
│   ├── src/app/         #   Next.js pages (search UI, file/app indexer)
│   ├── src-tauri/       #   Rust backend (file scanning, global shortcut)
│   └── public/          #   Static assets (owl mascot, logos, SVGs)
│
├── companion-app/       # Mobile Companion — Flutter cross-platform app
│   └── companion_app/
│       ├── lib/main.dart          #  Home screen with voice + text input
│       ├── lib/services/          #  AtlasService (WebSocket client)
│       └── lib/screens/           #  Connection settings screen
│
└── architecture.md      # Detailed architecture documentation
```

---

##  Components

### 1. ML Pipeline (`ml/` · `ml_2/`)

The core vision-driven desktop agent. Operates any desktop application using **only screen pixels** — no APIs, no hooks, no accessibility trees.

**Core Loop:**
```
                        ┌──────────────────┐
                        │   Companion App   │  (Flutter · Android/iOS)
                        │  Voice + Text UI  │
                        └────────┬─────────┘
                                 │ WebSocket
                        ┌────────▼─────────┐
                        │     Backend       │  (FastAPI · Python)
                        │  WebSocket relay  │
                        │  Agent orchestr.  │
                        └──┬───────────┬───┘
                           │           │
              ┌────────────▼──┐   ┌────▼────────────┐
              │    ML Pipeline │   │   MCP Agent      │
              │  (ml/ · ml_2/) │   │  (ml/mcp/)       │
              │  Vision-driven │   │  Browser automat. │
              │  desktop agent │   │  Playwright+LLM   │
              └────────────────┘   └──────────────────┘
                           │
                  ┌────────▼─────────┐
                  │    Frontend       │  (Tauri v2 + Next.js)
                  │  Desktop launcher │
                  │  File & app index │
                  └──────────────────┘
```

**Pipeline Steps:**

| Step | Module | Description |
|------|--------|-------------|
| 1 | `llm_model.extract_intent()` | Parse user prompt → structured intent |
| 2 | `llm_model.create_task_plan()` | Break intent → abstract step list |
| 3 | `screen_capture.grab()` | Capture screenshot via `mss` |
| 4 | `ocr_model.detect()` | Extract text + bounding boxes (PaddleOCR) |
| 5 | `vlm_model.detect_ui_elements()` | Identify UI regions (LLaVA) |
| 6 | `bbox_fusion.fuse()` | Merge all detections |
| 7 | `llm_model.plan_action()` | Decide one atomic action |
| 8 | `agent_loop._resolve_action()` | Convert to pixel coordinates |
| 9 | `executor.execute()` | Perform OS-level input (PyAutoGUI) |
| 10 | `verifier.verify()` | Confirm action effect visually |


---

## 🧩 Components

### 1. ML Pipeline (`ml/` · `ml_2/`)

The core vision-driven desktop agent. Operates any desktop application using **only screen pixels** — no APIs, no hooks, no accessibility trees.

**Core Loop:**
```
PERCEIVE → UNDERSTAND → PLAN → ACT → VERIFY → (repeat)
```

**Pipeline Steps:**

| Step | Module | Description |
|------|--------|-------------|
| 1 | `llm_model.extract_intent()` | Parse user prompt → structured intent |
| 2 | `llm_model.create_task_plan()` | Break intent → abstract step list |
| 3 | `screen_capture.grab()` | Capture screenshot via `mss` |
| 4 | `ocr_model.detect()` | Extract text + bounding boxes (PaddleOCR) |
| 5 | `vlm_model.detect_ui_elements()` | Identify UI regions (LLaVA) |
| 6 | `bbox_fusion.fuse()` | Merge all detections |
| 7 | `llm_model.plan_action()` | Decide one atomic action |
| 8 | `agent_loop._resolve_action()` | Convert to pixel coordinates |
| 9 | `executor.execute()` | Perform OS-level input (PyAutoGUI) |
| 10 | `verifier.verify()` | Confirm action effect visually |

**`ml_2/`** is the enhanced v2 pipeline with improved model wrappers, better verification logic, UIA (UI Automation) support, and a comprehensive phased test suite.

**Quick Start:**
```bash
cd ml_2
pip install -r requirements.txt

# Single command
python main.py "Open Notepad and type hello"

# Interactive mode
python main.py --interactive
```

---

### 2. MCP Browser Agent (`ml/mcp/`)

Autonomous browser automation powered by **Playwright MCP** and an LLM-driven action loop. Connects to the user's real Chrome profile (cookies & sessions intact) and executes web tasks end-to-end.

**Supported LLM Backends:**
-  **Gemini API** (Google — primary, `gemini-2.0-flash`)
-  **OpenAI-compatible** (OpenAI, Groq, Together, local vLLM/Ollama)
-  **Local llama.cpp** (fully offline, GGUF models)

**How it works:**
1. Launches Chrome with remote debugging (CDP)
2. Starts a Playwright MCP server connected via `--cdp-endpoint`
3. Discovers available browser tools from MCP
4. Feeds tools + task to the LLM in an agentic loop
5. LLM calls tools → MCP executes in browser → results feed back → repeat

**Quick Start:**
```bash
cd ml/mcp
cp .env.example .env        # Configure your API keys
pip install -r requirements.txt

# Single task
python -m mcp "Go to google.com and search for ATLAS AI"

# Interactive REPL
python -m mcp
```

---

### 3. Backend (`backend/`)

A **FastAPI** WebSocket server that bridges the companion app to the ML agent. Provides real-time bidirectional communication for sending commands and streaming progress updates.

**Endpoints:**

| Endpoint | Type | Description |
|----------|------|-------------|
| `GET /health` | REST | Health check |
| `GET /status` | REST | Agent status (idle/running) |
| `GET /companion` | REST | Server identity for companion handshake |
| `WS /ws` | WebSocket | Bidirectional command + progress stream |

**WebSocket Protocol:**
```json
// Client → Server
{"type": "command", "command": "Open Notepad and type hello"}
{"type": "stop"}

// Server → Client
{"type": "progress", "step": "action", "status": "executing", "detail": "..."}
{"type": "result", "success": true, "detail": "..."}
{"type": "error", "message": "..."}
```

**Quick Start:**
```bash
cd backend
pip install -r requirements.txt
python server.py              # Runs on http://0.0.0.0:8000
```

---

### 4. Frontend — Desktop Launcher (`frontend/`)

A **Tauri v2** desktop app with a **Next.js 16** frontend. Acts as a Spotlight/Alfred-style launcher that indexes and searches your local files and applications.

**Features:**
-  **Global shortcut** (`Win + -`) to toggle the launcher overlay
-  **File & app indexing** — Scans Start Menu, Desktop, Downloads, Documents, Pictures, Videos, and Program Files
-  **Startup caching** — Indexes once at launch, serves from memory
-  **Glassmorphism UI** — Dark theme with backdrop blur and fade-in animations
-  **Keyboard navigation** — Arrow keys, Enter to open, Escape to dismiss
-  **Transparent, borderless window** — Always-on-top, skip taskbar

**Tech Stack:**
- Rust (Tauri v2) — file scanning, system shortcuts, window management
- Next.js 16 (Turbopack) — React UI with Tailwind CSS v4
- Framer Motion — animations

**Quick Start:**
```bash
cd frontend
npm install
npm run tauri:dev           # Development mode
npm run tauri:build         # Production build
```

---

### 5. Companion App (`companion-app/`)

A **Flutter** mobile app that connects to the ATLAS backend over your local network. Send voice or text commands from your phone and watch the agent execute tasks on your PC in real-time.

**Features:**
-  **Voice input** — Speech-to-text for hands-free commands
-  **Real-time progress feed** — Live streaming of agent actions
-  **Auto-discovery** — Connect via IP + port with health check verification
-  **Persistent settings** — Remembers server connection details
-  **Pixel-art themed UI** — Custom owl mascot with retro aesthetics

**Tech Stack:**
- Flutter/Dart
- WebSocket for real-time communication
- `speech_to_text` for voice input
- `shared_preferences` for persistent storage

**Quick Start:**
```bash
cd companion-app/companion_app
flutter pub get
flutter run                   # Run on connected device/emulator
```

---

##  Design Principles

1. **The screen is the only truth** — No reliance on app-specific APIs or hooks
2. **Never trust one perception pass** — Cross-validate with multiple models
3. **Never assume a click worked** — Always verify visually
4. **Never hardcode coordinates** — Adapt to any resolution or DPI
5. **Always verify visually** — Before and after every action
6. **Never blindly trust user input** — Prompts may contain adversarial instructions

---

##  Known Issues

See `ml/errors.txt` and `ml_2/errors.txt` for tracked issues:

- **CRITICAL**: DPI scaling on high-DPI displays, modal dialog handling, multi-monitor support
- **NON-CRITICAL**: Error taxonomy refinement, typing speed tuning, VLM inference latency

---


## HOW TO RUN

DESKTOP APP

cd frontend 

npm run tauri:dev


## HOW TO CONNECT COMPANION APP TO THE DESKTOP

ip config

get your ipv4 address

 Input that in the companion app

 
