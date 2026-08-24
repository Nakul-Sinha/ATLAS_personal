"""
ATLAS Backend - WebSocket Relay Server
======================================

A FastAPI server that bridges the companion app (and any other client) to the
ATLAS agent. It exposes REST endpoints for health, status, and a companion
handshake, plus a WebSocket endpoint for streaming commands and progress.

Run:
    python server.py                 # http://0.0.0.0:8000
    uvicorn server:app --reload      # development with autoreload

Protocol (WebSocket /ws):
    Client -> Server:
        {"type": "command", "command": "Open Notepad and type hello"}
        {"type": "stop"}
    Server -> Client:
        {"type": "progress", "step": "...", "status": "...", "detail": "..."}
        {"type": "result", "success": true, "detail": "..."}
        {"type": "error", "message": "..."}
"""

from __future__ import annotations

import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_bridge import bridge
from config import VERSION, config

app = FastAPI(title="ATLAS Backend", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origin_list(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness and readiness probe used by the companion app to verify a host."""
    return JSONResponse(
        {
            "status": "ok",
            "service": "atlas-backend",
            "version": VERSION,
            "agent": bridge.describe_mode(),
        }
    )


@app.get("/status")
async def status() -> JSONResponse:
    """Report whether the agent is idle or running a task."""
    return JSONResponse(
        {
            "status": bridge.status,
            "agent": bridge.describe_mode(),
        }
    )


@app.get("/companion")
async def companion() -> JSONResponse:
    """Server identity for the companion app handshake."""
    return JSONResponse(
        {
            "name": "ATLAS",
            "service": "atlas-backend",
            "version": VERSION,
            "protocol": "1.0",
            "capabilities": ["command", "plan", "stop", "progress", "result"],
            "auth_required": bool(config.auth_token),
            "agent": bridge.describe_mode(),
        }
    )


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    """Bidirectional command and progress stream."""
    await websocket.accept()

    async def emit(event: dict) -> None:
        await websocket.send_text(json.dumps(event))

    # Optional shared-token auth. When a token is configured, the client must
    # send {"type": "auth", "token": ...} before anything else.
    required_token = config.auth_token
    authenticated = not required_token

    await emit(
        {
            "type": "progress",
            "step": "connected",
            "status": "ready",
            "detail": "Connected to ATLAS backend",
            "auth_required": bool(required_token),
        }
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await emit({"type": "error", "message": "Invalid JSON"})
                continue

            if not isinstance(message, dict):
                await emit({"type": "error", "message": "Message must be a JSON object"})
                continue

            mtype = message.get("type")

            if not authenticated:
                if mtype == "auth" and message.get("token") == required_token:
                    authenticated = True
                    await emit(
                        {
                            "type": "progress",
                            "step": "authenticated",
                            "status": "ready",
                            "detail": "Authenticated",
                        }
                    )
                else:
                    await emit({"type": "error", "message": "Authentication required"})
                continue

            if mtype == "auth":
                # Already authenticated (or auth not required); acknowledge quietly.
                await emit(
                    {"type": "progress", "step": "authenticated", "status": "ready", "detail": "OK"}
                )
            elif mtype == "command":
                command = (message.get("command") or "").strip()
                if not command:
                    await emit({"type": "error", "message": "Empty command"})
                    continue
                await bridge.run_task(command, emit)
            elif mtype == "plan":
                command = (message.get("command") or "").strip()
                if not command:
                    await emit({"type": "error", "message": "Empty command"})
                    continue
                await bridge.plan_task(command, emit)
            elif mtype == "stop":
                bridge.request_stop()
                await emit(
                    {
                        "type": "progress",
                        "step": "stop",
                        "status": "requested",
                        "detail": "Stop requested",
                    }
                )
            else:
                await emit(
                    {"type": "error", "message": f"Unknown message type: {mtype!r}"}
                )
    except WebSocketDisconnect:
        bridge.request_stop()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
