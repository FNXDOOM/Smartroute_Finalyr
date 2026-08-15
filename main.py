"""Project-root Uvicorn entry point.

The backend currently uses top-level imports such as ``database`` and
``routers``. Add the backend directory to the import path before loading the
application so ``uvicorn main:app`` works from the project root.
"""

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.main import app  # noqa: E402

__all__ = ["app"]
