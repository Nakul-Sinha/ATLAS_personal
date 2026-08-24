"""
ATLAS MCP Agent - Connection Test
===================================

Tests that the Playwright MCP server launches and tools are discoverable.
Does NOT require an LLM API key.

Run: python test_connection.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

console = Console()


async def test_mcp_connection():
    """Test that the Playwright MCP server starts and exposes tools."""
    console.print(Panel("[bold cyan]ATLAS MCP - Connection Test[/bold cyan]", border_style="cyan"))
    
    server_params = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest"],
    )
    
    console.print("[yellow]Starting Playwright MCP server...[/yellow]")
    
    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                console.print("[green]✓ MCP server connected successfully![/green]\n")
                
                # List tools
                tools_result = await session.list_tools()
                tools = tools_result.tools
                
                table = Table(title="Discovered Browser Tools", show_lines=False)
                table.add_column("#", style="dim", width=3)
                table.add_column("Tool Name", style="cyan", min_width=30)
                table.add_column("Description", style="dim")
                
                for i, t in enumerate(tools, 1):
                    desc = (t.description or "")[:80]
                    table.add_row(str(i), t.name, desc)
                
                console.print(table)
                console.print(f"\n[bold green]✓ {len(tools)} tools available.[/bold green]")
                console.print("[green]✓ Everything works! Set your API key in .env and run:[/green]")
                console.print("[white]  python run.py \"Go to google.com and search for ATLAS\"[/white]")
                
                return True
                
    except FileNotFoundError:
        console.print("[red]✗ npx not found. Install Node.js: https://nodejs.org[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Connection failed: {e}[/red]")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_mcp_connection())
    sys.exit(0 if success else 1)
