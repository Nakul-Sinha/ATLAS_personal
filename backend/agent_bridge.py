"""
ATLAS Backend - Agent Bridge
============================

Bridges the WebSocket relay to the vision-driven desktop agent in ``ml/``.

The real agent (``ml/agent/agent_loop.py``) is a synchronous loop that needs a
running Ollama server and a live desktop session. Neither is available on a
headless host or in CI, so this bridge degrades gracefully:

- ``real``: import and run the real ``AgentLoop``.
- ``mock``: simulate the perceive / plan / act / verify steps and echo the task.
- ``auto``: use ``real`` when the agent imports and Ollama is reachable, else ``mock``.

Progress from a real run is captured from the agent's ``loguru`` logs and
forwarded as ``progress`` events, so the bridge does not need to modify the agent.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from config import config

# An async callback that pushes one event dict to the connected client.
EventEmitter = Callable[[dict], Awaitable[None]]

_ML_DIR = Path(__file__).resolve().parent.parent / "ml"


def _ollama_reachable(base_url: str, timeout: float = 2.0) -> bool:
    """Return True if an Ollama server answers at base_url."""
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def _agent_importable() -> bool:
    """Return True if the real agent and its dependencies import cleanly."""
    if not _ML_DIR.is_dir():
        return False
    added = False
    try:
        if str(_ML_DIR) not in sys.path:
            sys.path.insert(0, str(_ML_DIR))
            added = True
        import agent  # noqa: F401  (ml/agent package)

        return True
    except Exception:
        return False
    finally:
        if added and str(_ML_DIR) in sys.path:
            # Leave ml on the path only when the import succeeded so a later real
            # run can reuse it; otherwise remove our temporary entry.
            try:
                sys.path.remove(str(_ML_DIR))
            except ValueError:
                pass


class AgentBridge:
    """Owns agent lifecycle and translates a task run into a stream of events."""

    def __init__(self) -> None:
        self._status = "idle"
        self._stop_requested = False
        self._resolved_mode: Optional[str] = None
        self._agent = None  # lazily constructed real AgentLoop
        self._unavailable_reason: Optional[str] = None

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

        # auto
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
        return info

    def request_stop(self) -> None:
        self._stop_requested = True
        if self._agent is not None:
            try:
                self._agent.stop()
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
            mode = self.resolve_mode()
            if mode == "real":
                await self._run_real(command, emit)
            else:
                await self._run_mock(command, emit)
        except Exception as exc:  # never let the socket handler crash
            await emit({"type": "error", "message": f"Agent run failed: {exc}"})
        finally:
            self._status = "idle"

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

    # -- real execution -------------------------------------------------------

    def _get_agent(self):
        if self._agent is None:
            if str(_ML_DIR) not in sys.path:
                sys.path.insert(0, str(_ML_DIR))
            from agent import AgentLoop  # type: ignore

            self._agent = AgentLoop()
        return self._agent

    async def _run_real(self, command: str, emit: EventEmitter) -> None:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        await emit(
            {
                "type": "progress",
                "step": "start",
                "status": "executing",
                "detail": "Initializing agent",
            }
        )

        # Bridge loguru log lines from the worker thread into progress events.
        sink_id = None
        try:
            from loguru import logger

            def _sink(message) -> None:
                record = message.record
                text = record["message"]
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {
                        "type": "progress",
                        "step": "agent",
                        "status": record["level"].name.lower(),
                        "detail": text,
                    },
                )

            sink_id = logger.add(_sink, level="INFO")
        except Exception:
            sink_id = None

        async def _drain_until(done: asyncio.Future) -> None:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.25)
                    await emit(event)
                except asyncio.TimeoutError:
                    if done.done():
                        break

        def _blocking_run() -> bool:
            agent = self._get_agent()
            return bool(agent.run(command))

        run_future = loop.run_in_executor(None, _blocking_run)
        drain_task = asyncio.create_task(_drain_until(run_future))
        try:
            success = await run_future
        finally:
            await drain_task
            if sink_id is not None:
                try:
                    from loguru import logger

                    logger.remove(sink_id)
                except Exception:
                    pass
            # Flush any remaining queued events.
            while not queue.empty():
                await emit(queue.get_nowait())

        await emit(
            {
                "type": "result",
                "success": bool(success),
                "detail": "Task completed" if success else "Task failed",
            }
        )


# Module-level singleton used by the server.
bridge = AgentBridge()
