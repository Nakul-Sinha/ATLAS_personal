"""
Tests for the ATLAS backend relay.

These run fully offline: the agent is forced into mock mode and step delays are
zeroed, so no Ollama server or desktop session is required.
"""

import os
import sys
from pathlib import Path

# Force deterministic, hermetic behavior before importing the app.
os.environ["ATLAS_AGENT_MODE"] = "mock"
os.environ["ATLAS_MOCK_STEP_DELAY"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "atlas-backend"
    assert data["agent"]["mode"] == "mock"


def test_status_idle():
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_companion_handshake():
    resp = client.get("/companion")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "ATLAS"
    assert data["protocol"] == "1.0"
    assert "command" in data["capabilities"]


def test_ws_command_streams_progress_then_result():
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "progress"
        assert hello["step"] == "connected"

        ws.send_json({"type": "command", "command": "Open Notepad and type hello"})

        events = []
        while True:
            msg = ws.receive_json()
            events.append(msg)
            if msg["type"] == "result":
                break

        progress = [e for e in events if e["type"] == "progress"]
        assert len(progress) >= 3
        result = events[-1]
        assert result["type"] == "result"
        assert result["success"] is True
        assert "Open Notepad and type hello" in result["detail"]


def test_ws_plan_streams_steps_without_executing():
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # connected banner
        ws.send_json({"type": "plan", "command": "Open Notepad and type hello"})
        events = []
        while True:
            msg = ws.receive_json()
            events.append(msg)
            if msg["type"] == "result":
                break
        plan_steps = [e for e in events if e["type"] == "progress" and e.get("step") == "plan"]
        assert len(plan_steps) >= 1
        result = events[-1]
        assert result["success"] is True
        assert "dry run" in result["detail"]
        assert isinstance(result.get("plan"), list) and result["plan"]


def test_ws_plan_rejects_empty_command():
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "plan", "command": "   "})
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_ws_invalid_json_is_reported():
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()  # connected banner
        ws.send_text("this is not json")
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_ws_empty_command_is_rejected():
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "command", "command": "   "})
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_ws_unknown_type_is_rejected():
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "frobnicate"})
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_companion_reports_auth_required_when_token_set():
    server.config.auth_token = "s3cret"
    try:
        data = client.get("/companion").json()
        assert data["auth_required"] is True
    finally:
        server.config.auth_token = ""


def test_ws_rejects_commands_until_authenticated():
    server.config.auth_token = "s3cret"
    try:
        with client.websocket_connect("/ws") as ws:
            hello = ws.receive_json()
            assert hello.get("auth_required") is True

            # A command before auth is rejected.
            ws.send_json({"type": "command", "command": "Open Notepad"})
            assert ws.receive_json()["type"] == "error"

            # A wrong token is rejected.
            ws.send_json({"type": "auth", "token": "nope"})
            assert ws.receive_json()["type"] == "error"

            # The right token authenticates, then a command is accepted.
            ws.send_json({"type": "auth", "token": "s3cret"})
            ok = ws.receive_json()
            assert ok["type"] == "progress" and ok["step"] == "authenticated"

            ws.send_json({"type": "command", "command": "Open Notepad"})
            events = []
            while True:
                msg = ws.receive_json()
                events.append(msg)
                if msg["type"] == "result":
                    break
            assert events[-1]["success"] is True
    finally:
        server.config.auth_token = ""


def test_ws_open_when_no_token():
    # Default (no token): the connected banner reports auth not required.
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello.get("auth_required") is False


def test_ws_stop_is_acknowledged():
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "stop"})
        msg = ws.receive_json()
        assert msg["type"] == "progress"
        assert msg["step"] == "stop"
