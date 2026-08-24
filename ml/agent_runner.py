"""
ATLAS ML Pipeline - Subprocess Runner
=====================================

A thin entry point that a host process (the backend relay) launches as a
subprocess with this directory as the working directory, so the ml package's
top-level imports (config, models, agent, ...) resolve to this package and do
not collide with the host's own modules.

It streams newline-delimited JSON events on stdout using the same protocol the
backend speaks to clients:

    {"type": "progress", "step": "...", "status": "...", "detail": "..."}
    {"type": "result", "success": true, "detail": "...", "plan": [...]}
    {"type": "error", "message": "..."}

Usage:
    python agent_runner.py "Open Notepad and type hello"        # execute
    python agent_runner.py --plan-only "Open Notepad ..."       # dry run, no input
"""

import argparse
import json
import sys


def _emit(event: dict) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def _plan_only(command: str) -> None:
    from models import LLMModel

    llm = LLMModel()
    llm.load()
    intent = llm.extract_intent(command)
    steps = llm.create_task_plan(intent)
    _emit({
        "type": "progress", "step": "understand", "status": "planned",
        "detail": f"Goal: {intent.goal}",
    })
    for i, step in enumerate(steps, 1):
        _emit({
            "type": "progress", "step": "plan", "status": "step",
            "detail": f"{i}. {step.description}",
        })
    _emit({
        "type": "result", "success": True,
        "detail": f"Planned {len(steps)} steps (dry run, nothing executed)",
        "plan": [s.description for s in steps],
    })


def _execute(command: str) -> None:
    from loguru import logger

    from agent import AgentLoop

    # Forward the agent's log lines as progress events.
    logger.remove()
    logger.add(
        lambda m: _emit({
            "type": "progress",
            "step": "agent",
            "status": m.record["level"].name.lower(),
            "detail": m.record["message"],
        }),
        level="INFO",
    )

    agent = AgentLoop()
    ok = agent.run(command)
    _emit({
        "type": "result",
        "success": bool(ok),
        "detail": "Task completed" if ok else "Task failed",
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="ATLAS agent subprocess runner")
    parser.add_argument("command", help="Natural-language task")
    parser.add_argument("--plan-only", action="store_true", help="Plan without executing")
    args = parser.parse_args()

    try:
        if args.plan_only:
            _plan_only(args.command)
        else:
            _execute(args.command)
    except Exception as exc:  # surface any failure as a protocol error
        _emit({"type": "error", "message": str(exc)})
        sys.exit(1)


if __name__ == "__main__":
    main()
