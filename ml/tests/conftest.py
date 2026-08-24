"""
Shared pytest setup for the ATLAS ML tests.

Adds the ml/ directory to sys.path so the package-relative imports used by the
runtime code (``from config import ...``, ``from perception import ...``) resolve
the same way they do when the agent is launched from inside ml/.
"""

import sys
from pathlib import Path

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))
