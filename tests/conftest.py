# Ensures `import app` works when running `pytest` from repo root or a parent folder.
# This keeps tests hermetic without relying on PYTHONPATH being set by the shell.
import sys
from pathlib import Path

# project root = parent of this tests/ directory
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
