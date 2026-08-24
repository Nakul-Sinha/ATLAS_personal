# ATLAS Backend

A FastAPI WebSocket relay that bridges clients (the Flutter companion app, or any
WebSocket client) to the ATLAS desktop agent in `ml/`.

## Why a relay

The agent runs on the PC. Your phone sends a natural-language command over the local
network, the relay hands it to the agent, and progress streams back to the phone in
real time.

## Endpoints

| Endpoint | Type | Purpose |
|----------|------|---------|
| `GET /health` | REST | Liveness and readiness; the companion app uses this to verify a host |
| `GET /status` | REST | Whether the agent is `idle` or `running` |
| `GET /companion` | REST | Server identity for the companion handshake |
| `WS /ws` | WebSocket | Bidirectional command and progress stream |

## WebSocket protocol

```jsonc
// Client -> Server
{"type": "command", "command": "Open Notepad and type hello"}
{"type": "stop"}

// Server -> Client
{"type": "progress", "step": "act", "status": "executing", "detail": "..."}
{"type": "result", "success": true, "detail": "..."}
{"type": "error", "message": "..."}
```

## Agent modes

The relay never fails to start, even without a desktop or Ollama:

- `auto` (default): use the real agent when it imports and Ollama is reachable, else fall
  back to a mock that simulates the perceive / plan / act / verify steps.
- `real`: force the real agent (needs Ollama with `llama3.2` and `llava`, plus a live
  desktop session).
- `mock`: always simulate. Useful for demos, UI development, and CI.

Set the mode with `ATLAS_AGENT_MODE`. See `.env.example` for all settings.

## Quick start

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env
python server.py            # http://0.0.0.0:8000
```

Development with autoreload:

```bash
uvicorn server:app --reload
```

## Connect the companion app

1. On the PC, run `ipconfig` and note the IPv4 address.
2. In the companion app, enter that IP and port `8000`.
3. The app calls `/health` to verify, then opens the WebSocket.

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest
```

Tests force mock mode and zero step delays, so they run fully offline.

## Docker

```bash
cd backend
docker build -t atlas-backend .
docker run --rm -p 8000:8000 -e ATLAS_AGENT_MODE=mock atlas-backend
```

The container runs the relay in mock mode by default because it has no desktop session.
Point it at a host Ollama and run in `auto`/`real` mode only where a desktop is present.
