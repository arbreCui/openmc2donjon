#!/usr/bin/env python3
"""Build an explicitly unaccepted 91-position library from reference MGXS.

This diagnostic removes the native-SPH leg while keeping the same five local
colorset MGXS sources and the same full-core position map.  It is used only to
separate local-MGXS transfer error from local-SPH transfer error; it does not
create an accepted component library or an acceptance receipt.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import numpy as np

from layout import declared_positions
from openmc2donjon.macrolib import write_macrolib
from openmc2donjon.multicompo import MixtureXS, read_mgxs_hdf5


CASES = {
    "INT": "int_ext",
    "EXT": "ext_int",
    "CSD": "csd_int",
    "DSDF": "dsdf_int",
    "PNL": "pnl_ext",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists() and not args.force:
        parser.error(f"output exists; use --force: {output}")

    by_component: dict[str, MixtureXS] = {}
    reference_energy: np.ndarray | None = None
    for component, case in CASES.items():
        source = (
            args.project_root.expanduser().resolve()
            / "colorsets"
            / case
            / "handoff"
            / "mgxs_components.h5"
        )
        mixtures, energy = read_mgxs_hdf5(source)
        matches = [mixture for mixture in mixtures if mixture.name == component]
        if len(matches) != 1:
            raise ValueError(f"{source}: expected exactly one {component} mixture")
        mixture = matches[0]
        if mixture.sph is not None or mixture.adf:
            raise ValueError(f"{source}: reference diagnostic requires raw MGXS")
        if reference_energy is None:
            reference_energy = np.asarray(energy, dtype=float)
        elif not np.array_equal(reference_energy, np.asarray(energy, dtype=float)):
            raise ValueError(f"{source}: energy structure differs")
        by_component[component] = mixture

    assert reference_energy is not None
    position_mixtures = [
        replace(by_component[component], name=position_name)
        for position_name, component in declared_positions()
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    write_macrolib(position_mixtures, reference_energy, output)
    print("UNACCEPTED DIAGNOSTIC: five local reference MGXS mapped to 91 positions")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
