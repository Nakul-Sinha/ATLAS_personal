"""
ATLAS MCP Agent - Shared CLI logic
==================================

This module holds the command-line logic used by both entry points:

  - run.py         (recommended, collision-free runner)
  - __main__.py    (kept for direct "python __main__.py" use)

Why a separate module: the folder is named "mcp", which collides with the
installed "mcp" Python SDK that browser_agent.py imports. Running the package
as "python -m mcp" makes Python resolve "from mcp import ClientSession" to this
local folder instead of the SDK, which breaks. Running "python run.py" (or
"python __main__.py") from inside this folder avoids that collision.

Run examples (from inside ml/mcp/):
    python run.py "Go to google.com and search for ATLAS AI"
    python run.py                 # interactive REPL
    python run.py --help          # usage, no API key needed
"""

import asyncio
import os
import sys

# Ensure this folder is importable (config.py, browser_agent.py, etc.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from config import get_config

console = Console()


USAGE = """\
ATLAS MCP Agent - autonomous browser automation via MCP + LLM

Usage (run from inside ml/mcp/):
  python run.py "your task here"     Run a single task and exit
  python run.py                      Start the interactive REPL
  python run.py --help               Show this message

Prerequisites:
  - Python deps:  pip install -r requirements.txt
  - Node.js + npx (launches @playwright/mcp)
  - Google Chrome (only when CHROME_PROFILE=true)

Setup:
  Copy .env.example to .env and set your LLM backend and API key.
  Smoke test (no API key needed):  python test_connection.py
"""


def print_usage():
    console.print(USAGE)


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]ATLAS MCP Agent[/bold cyan]\n"
        "[dim]Autonomous browser automation via MCP + LLM[/dim]\n\n"
        "Commands:\n"
        "  [green]Type a task[/green]  - Execute it in the browser\n"
        "  [green]config[/green]      - Show current configuration\n"
        "  [green]quit / exit[/green] - Exit\n",
        title="ATLAS",
        border_style="cyan",
    ))


def print_config(cfg):
    console.print(f"  [cyan]LLM Backend:[/cyan]  {cfg.llm_backend}")
    if cfg.llm_backend == "gemini":
        console.print(f"  [cyan]Model:[/cyan]        {cfg.gemini.model}")
        key_preview = cfg.gemini.api_key[:8] + "..." if cfg.gemini.api_key else "(not set)"
        console.print(f"  [cyan]API Key:[/cyan]      {key_preview}")
    elif cfg.llm_backend == "openai":
        console.print(f"  [cyan]Model:[/cyan]        {cfg.openai.model}")
        console.print(f"  [cyan]Base URL:[/cyan]     {cfg.openai.base_url or 'https://api.openai.com/v1'}")
        key_preview = cfg.openai.api_key[:8] + "..." if cfg.openai.api_key else "(not set)"
        console.print(f"  [cyan]API Key:[/cyan]      {key_preview}")
    else:
        console.print(f"  [cyan]Model Path:[/cyan]   {cfg.llama.model_path}")
    console.print(f"  [cyan]Headless:[/cyan]     {cfg.playwright_headless}")
    console.print(f"  [cyan]CDP Port:[/cyan]     {cfg.cdp_port}")
    console.print(f"  [cyan]Max Steps:[/cyan]    {cfg.max_steps}")
    console.print(f"  [cyan]Debug:[/cyan]        {cfg.debug}")


async def interactive_mode():
    """Interactive REPL - enter tasks one at a time."""
    # Imported here so "--help" and module import do not require the mcp SDK.
    from browser_agent import BrowserAgent

    print_banner()

    cfg = get_config()
    print_config(cfg)
    console.print()

    while True:
        try:
            task = Prompt.ask("\n[bold cyan]Task[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        task = task.strip()
        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if task.lower() == "config":
            cfg = get_config()
            print_config(cfg)
            continue

        try:
            agent = BrowserAgent(cfg)
            await agent.run(task)
        except KeyboardInterrupt:
            console.print("\n[yellow]Task cancelled.[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            if cfg.debug:
                console.print_exception()


async def single_task_mode(task: str):
    """Execute a single task and exit."""
    # Imported here so "--help" and module import do not require the mcp SDK.
    from browser_agent import BrowserAgent

    cfg = get_config()
    agent = BrowserAgent(cfg)
    await agent.run(task)


def main(argv=None):
    """CLI entry point shared by run.py and __main__.py."""
    args = list(sys.argv[1:] if argv is None else argv)

    # --help must work without an API key and without launching anything.
    if args and args[0] in ("-h", "--help", "help"):
        print_usage()
        return

    if args:
        task = " ".join(args)
        asyncio.run(single_task_mode(task))
    else:
        asyncio.run(interactive_mode())


if __name__ == "__main__":
    main()
