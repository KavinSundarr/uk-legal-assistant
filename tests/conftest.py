"""
Pytest configuration — adds backend/ to sys.path so ``from app.xxx import …``
works, and sets cwd to the project root so relative data paths resolve.
"""

import os
import sys
from pathlib import Path

# ── Project root = parent of this tests/ directory ──────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR  = PROJECT_ROOT / "backend"

# Insert backend at the front so our app package takes precedence
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Change cwd so that relative paths like "data/index" resolve correctly
os.chdir(PROJECT_ROOT)
