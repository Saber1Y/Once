"""Load a company's integration module (``ONCE_INTEGRATION``, default ``acme.integration``).

An integration module exposes ``create_guard(memory, env=None) -> Guard`` and,
for the demo queue, ``demo_tickets() -> list[dict]``.
"""

from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path
from types import ModuleType

from once.config import ROOT

EXAMPLES = ROOT / "examples"


def load(spec: str | None = None) -> ModuleType:
    spec = spec or os.getenv("ONCE_INTEGRATION") or "acme.integration"
    if str(EXAMPLES) not in sys.path:
        sys.path.insert(0, str(EXAMPLES))
    module = importlib.import_module(spec)
    if not hasattr(module, "create_guard"):
        raise RuntimeError(f"{spec} must define create_guard(memory, env=None)")
    return module


def source_files(module: ModuleType) -> dict[str, str]:
    """The integration's own files, shown on the console's Integration screen."""
    folder = Path(inspect.getfile(module)).parent
    files = {}
    for name in ("integration.py", "once.yaml", "checks.py", "cases.py", "agent.py"):
        path = folder / name
        if path.exists():
            files[name] = path.read_text()
    return files
