"""Bundled fixture JSONs returned by the FastAPI app in ``--mock`` mode."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


def load_fixture(filename: str) -> dict[str, Any]:
    """Read a fixture JSON from this package."""

    text = resources.files(__package__).joinpath(filename).read_text(encoding="utf-8")
    return json.loads(text)
