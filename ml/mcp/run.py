"""
ATLAS MCP Agent - Runner
========================

Preferred way to launch the agent. The folder is named "mcp", which collides
with the installed "mcp" Python SDK. Running "python -m mcp" makes Python
resolve "from mcp import ClientSession" to this local folder instead of the
SDK, which breaks. This runner uses a distinct filename so no such collision
happens.

Run from inside ml/mcp/:
    python run.py "Go to google.com and search for ATLAS AI"
    python run.py                 # interactive REPL
    python run.py --help          # usage, no API key needed
"""

import os
import sys

# Make sure this folder is on sys.path so local modules import cleanly,
# even if run.py is invoked from another working directory.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from cli import main

if __name__ == "__main__":
    main()
