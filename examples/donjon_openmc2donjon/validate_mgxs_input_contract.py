#!/usr/bin/env python3
"""Compatibility wrapper for the packaged MGXS input contract validator."""

from __future__ import annotations

from openmc2donjon.mgxs_input_contract import *  # noqa: F401,F403
from openmc2donjon.mgxs_input_contract import main


if __name__ == "__main__":
    raise SystemExit(main())
