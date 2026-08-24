"""
ATLAS Backend - Agent Bridge
============================

Bridges the WebSocket relay to the vision-driven desktop agent in ``ml/``.

The ml package is written to run with its own directory as the import root
(``from config import ...``, ``from agent import ...``). The backend has its own
``config`` module, so importing ml in-process would collide. Instead the bridge
runs the agent as a subprocess (``ml/agent_runner.py``) with ``cwd=ml/``, which
isolates the import namespace and, as a bonus, keeps a GUI-automation crash from
taking down the relay. The subprocess streams newline-delimited JSON events that
the bridge forwards to the client unchanged.

Modes (``ATLAS_AGENT_MODE``):

- ``real``: run the real agent subprocess.
- ``mock``: simulate perceive / plan / act / verify and echo the task.
- ``auto``: real when the runner imports and Ollama is reachable, else mock.
- ``plan``: never execute; stream the plan only (safe preview / dry run).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from config import config

# An async callback that pushes one event dict to the connected client.
EventEmitter = Callable[[dict], Awaitable[None]]

_ML_DIR = Path(__file__).resolve().parent.parent / "ml"
_ML_RUNNER = _ML_DIR / "agent_runner.py"


def _ollama_reachable(base_url: str, timeout: float = 2.0) -> bool:
    """Return True if an Ollama server answers at base_url."""
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _agent_importable() -> bool:
    """
    Return True if the ml runner can import its dependencies.

    Checked in a subprocess with cwd=ml/ so the result reflects the exact
    environment the runner will use (and avoids the config-name collision).
    """
    if not _ML_RUNNER.is_file():
        return False
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import models, agent"],
            cwd=str(_ML_DIR),
            capture_output=True,
            timeout=60,
        )
        return proc.returncode == 0
    except Exception:
        return False


class AgentBridge:
    """Owns agent lifecycle and translates a task run into a stream of events."""

    def __init__(self) -> None:
        self._status = "idle"
        self._stop_requested = False
        self._resolved_mode: Optional[str] = None
        self._unavailable_reason: Optional[str] = None
        self._proc: Optional[asyncio.subprocess.Process] = None

    @property
    def status(self) -> str:
        return self._status

    def resolve_mode(self) -> str:
        """Decide whether real or mock execution is used, and cache the result."""
        if self._resolved_mode is not None:
            return self._resolved_mode

        requested = config.agent_mode
        if requested == "mock":
            self._resolved_mode = "mock"
            self._unavailable_reason = "forced by ATLAS_AGENT_MODE=mock"
            return self._resolved_mode

        if requested == "real":
            self._resolved_mode = "real"
            return self._resolved_mode

        # auto and plan both want to know whether the real agent is usable.
        if not _agent_importable():
            self._unavailable_reason = "agent dependencies not importable"
            self._resolved_mode = "mock"
        elif not _ollama_reachable(config.ollama_base_url):
            self._unavailable_reason = "ollama server not reachable"
            self._resolved_mode = "mock"
        else:
            self._resolved_mode = "real"
        return self._resolved_mode

    def describe_mode(self) -> dict:
        mode = self.resolve_mode()
        info = {"mode": mode}
        if mode == "mock" and self._unavailable_reason:
            info["reason"] = self._unavailable_reason
        if config.agent_mode == "plan":
            info["dry_run"] = True
        return info

    def request_stop(self) -> None:
        self._stop_requested = True
        proc = self._proc
        if proc is not None and proc.returncode is None:
            try:
                proc.terminate()
            except Exception:
                pass

    async def run_task(self, command: str, emit: EventEmitter) -> None:
        """Execute a task, emitting progress / result / error events."""
        if self._status == "running":
            await emit({"type": "error", "message": "Agent is already running a task"})
            return

        self._stop_requested = False
        self._status = "running"
        try:
            # A plan-only server never executes OS input; it previews the plan.
            if config.agent_mode == "plan":
                await self._run_plan(command, emit)
            elif self.resolve_mode() == "real":
                await self._run_real(command, emit)
            else:
                await self._run_mock(command, emit)
        except Exception as exc:  # never let the socket handler crash
            await emit({"type": "error", "message": f"Agent run failed: {exc}"})
        finally:
            self._status = "idle"

    async def plan_task(self, command: str, emit: EventEmitter) -> None:
        """
        Produce and stream a plan without executing any action (dry run).

        The safe preview path: the agent decides what it would do and streams the
        steps, but never touches the mouse or keyboard. Available on request
        regardless of the configured agent mode.
        """
        if self._status == "running":
            await emit({"type": "error", "message": "Agent is already running a task"})
            return
        self._stop_requested = False
        self._status = "running"
        try:
            await self._run_plan(command, emit)
        except Exception as exc:
            await emit({"type": "error", "message": f"Planning failed: {exc}"})
        finally:
            self._status = "idle"

    # -- subprocess runner ----------------------------------------------------

    async def _stream_runner(self, command: str, emit: EventEmitter, plan_only: bool) -> bool:
        """
        Launch the ml runner subprocess and forward its JSON events.

        Returns True if a terminal event (result or error) was emitted by the
        runner. cwd=ml/ so the runner's imports resolve to the ml package.
        """
        args = [sys.executable, str(_ML_RUNNER)]
        if plan_only:
            args.append("--plan-only")
        args.append(command)

        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(_ML_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._proc = proc
        saw_terminal = False
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict) and event.get("type"):
                    if event["type"] in ("result", "error"):
                        saw_terminal = True
                    await emit(event)
            await proc.wait()
        finally:
            self._proc = None

        if self._stop_requested and not saw_terminal:
            await emit({"type": "result", "success": False, "detail": "Stopped by user"})
            return True

        if not saw_terminal and proc.returncode not in (0, None):
            detail = ""
            if proc.stderr is not None:
                try:
                    detail = (await proc.stderr.read()).decode("utf-8", "replace").strip()[-400:]
                except Exception:
                    detail = ""
            await emit({
                "type": "error",
                "message": f"Agent runner exited with code {proc.returncode}. {detail}".strip(),
            })
            saw_terminal = True
        return saw_terminal

    # -- plan (dry run) -------------------------------------------------------

    async def _run_plan(self, command: str, emit: EventEmitter) -> None:
        if self.resolve_mode() == "real":
            if await self._stream_runner(command, emit, plan_only=True):
                return
            # runner produced nothing usable; fall through to a simulated plan.

        # Fallback: simulate a plan so the preview works offline and in CI.
        sim_steps = [
            "Open the target application",
            "Locate the relevant control on screen",
            "Perform the requested action",
            "Verify the result",
        ]
        await emit({
            "type": "progress", "step": "understand", "status": "planned",
            "detail": f"Intent parsed from: {command}",
        })
        for i, desc in enumerate(sim_steps, 1):
            if config.mock_step_delay > 0:
                await asyncio.sleep(config.mock_step_delay)
            await emit({
                "type": "progress", "step": "plan", "status": "step",
                "detail": f"{i}. {desc}",
            })
        await emit({
            "type": "result", "success": True,
            "detail": f"Simulated plan for: {command} (dry run, nothing executed)",
            "plan": sim_steps,
        })

    # -- real execution -------------------------------------------------------

    async def _run_real(self, command: str, emit: EventEmitter) -> None:
        await emit({
            "type": "progress", "step": "start", "status": "executing",
            "detail": "Launching agent",
        })
        if not await self._stream_runner(command, emit, plan_only=False):
            await emit({
                "type": "result", "success": False,
                "detail": "Agent produced no result",
            })

    # -- mock execution -------------------------------------------------------

    async def _run_mock(self, command: str, emit: EventEmitter) -> None:
        steps = [
            ("perceive", "Capturing screen and reading UI text"),
            ("understand", f"Parsing intent from: {command}"),
            ("plan", "Breaking the task into atomic steps"),
            ("act", "Executing the planned action"),
            ("verify", "Confirming the action took effect"),
        ]
        for step, detail in steps:
            if self._stop_requested:
                await emit({"type": "result", "success": False, "detail": "Stopped by user"})
                return
            await emit(
                {"type": "progress", "step": step, "status": "executing", "detail": detail}
            )
            if config.mock_step_delay > 0:
                await asyncio.sleep(config.mock_step_delay)
        await emit(
            {
                "type": "result",
                "success": True,
                "detail": f"Simulated completion of task: {command}",
            }
        )


# Module-level singleton used by the server.
bridge = AgentBridge()
