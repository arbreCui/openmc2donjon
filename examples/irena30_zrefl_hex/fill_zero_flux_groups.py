#!/usr/bin/env python3
"""Deprecated shim: use ``openmc2donjon fill-zero-flux <mgxs> --macrolib PATH --in-place``.

The fill now lives in the package (:mod:`openmc2donjon.zero_flux_fill`); this
script only forwards the historical ``--mgxs``/``--macrolib`` invocation to it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from openmc2donjon.zero_flux_fill import fill_zero_flux_groups


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgxs", type=Path, required=True,
                        help="converted mgxs_library.h5 (edited in place)")
    parser.add_argument("--macrolib", type=Path, required=True,
                        help="OpenMC MG macrolib the run consumed")
    args = parser.parse_args()

    print(
        "note: fill_zero_flux_groups.py is a deprecated shim; use "
        "'openmc2donjon fill-zero-flux <mgxs> --macrolib PATH --in-place'",
        file=sys.stderr,
    )
    try:
        report = fill_zero_flux_groups(args.mgxs, macrolib=args.macrolib, in_place=True)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        raise SystemExit(f"fill_zero_flux_groups: error: {exc}") from exc
    print(f"filled {report.total_filled_bins} zero-flux (mixture, group) bins from {args.macrolib}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
