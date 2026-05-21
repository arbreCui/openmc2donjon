"""Compatibility wrapper for the packaged DONJON deck runner."""

from __future__ import annotations

from openmc2donjon.donjon_deck_runner import main


if __name__ == "__main__":
    raise SystemExit(main())
