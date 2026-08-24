"""
ATLAS MCP Agent - CLI Entry Point
=================================

Recommended (collision-free) way to run, from inside ml/mcp/:
    python run.py "Go to google.com and search for ATLAS AI"
    python run.py                 # interactive mode

This file still works when invoked directly:
    python __main__.py "your task here"
    python __main__.py            # interactive mode

Note: "python -m mcp" does NOT work reliably. The folder is named "mcp" and
collides with the installed "mcp" Python SDK, so use run.py instead.
"""

import os
import sys

# Ensure this folder is importable when run directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cli import main

if __name__ == "__main__":
    main()
