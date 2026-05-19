#!/usr/bin/env python3
"""Prepare and validate the experimental BURN-axis DONJON smoke."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import h5py
import numpy as np


BURNUP_VALUES = (0.0, 10.0)
TOTALS = {
    0.0: np.array([0.50, 0.70], dtype=float),
    10.0: np.array([0.80, 0.90], dtype=float),
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare or validate a tiny DONJON BURN-axis consumer smoke."
    )
    parser.add_argument("command", choices=("prepare", "fixture", "convert", "validate"))
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--package-src", type=Path, required=True)
    parser.add_argument(
        "--result",
        action="append",
        default=[],
        help="DONJON result file to validate; repeat for each burnup deck",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(args.package_src))
    if args.command == "prepare":
        prepare(args.run_dir)
    elif args.command == "fixture":
        write_fixture(args.run_dir)
    elif args.command == "convert":
        convert_fixture(args.run_dir)
    else:
        validate(args.run_dir, [Path(path) for path in args.result])
    return 0


def prepare(run_dir: Path) -> None:
    write_fixture(run_dir)
    convert_fixture(run_dir)


def write_fixture(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    h5_path = run_dir / "xs.h5"
    write_hdf5_fixture(h5_path)
    print(f"wrote burnup-axis HDF5 fixture: {h5_path}")


def convert_fixture(run_dir: Path) -> None:
    h5_path = run_dir / "xs.h5"
    mco_path = run_dir / "xs.mco"
    manifest_path = run_dir / "burnup_axis_smoke_manifest.json"

    if not h5_path.is_file():
        raise SystemExit(f"missing HDF5 fixture: {h5_path}")

    from openmc2donjon.multicompo import convert_mgxs_hdf5

    convert_mgxs_hdf5(
        h5_path,
        mco_path,
        root_name="CPO",
        comment="openmc2donjon experimental BURN-axis smoke",
    )

    decks = []
    for burnup in BURNUP_VALUES:
        deck = run_dir / f"burn_b{_burnup_tag(burnup)}.x2m"
        write_donjon_deck(deck, str(mco_path), burnup)
        decks.append(
            {
                "burnup": burnup,
                "deck": str(deck),
                "expected_total": TOTALS[burnup].tolist(),
            }
        )

    manifest = {
        "schema": "openmc2donjon.burnup-axis-smoke.v1",
        "hdf5": str(h5_path),
        "multicompo": str(mco_path),
        "decks": decks,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"prepared burnup-axis smoke in {run_dir}")
    print(f"multicompo: {mco_path}")
    for item in decks:
        print(f"deck BURN={item['burnup']:g}: {item['deck']}")


def write_hdf5_fixture(path: Path) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = 2
        h5.attrs["legendre_order"] = 0
        h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
        state_points = h5.create_group("state_points")
        state_points.create_dataset("BURN", data=np.array(BURNUP_VALUES))

        mixtures = h5.create_group("mixtures")
        fuel = mixtures.create_group("fuel")
        fuel.attrs["fissionable"] = True
        fuel.attrs["scatter_axes"] = "moment,from,to"
        fuel.attrs["volume"] = 1.0
        states = fuel.create_group("states")

        for index, burnup in enumerate(BURNUP_VALUES, start=1):
            group = states.create_group(f"{index:08d}")
            total = TOTALS[burnup]
            group.create_dataset("total", data=total)
            group.create_dataset("transport_total", data=total)
            group.create_dataset("absorption", data=np.array([0.05, 0.08]))
            group.create_dataset("fission", data=np.array([0.010, 0.015]))
            group.create_dataset("nu_fission", data=np.array([0.025, 0.030]))
            group.create_dataset("chi", data=np.array([1.0, 0.0]))
            group.create_dataset(
                "scatter_matrix",
                data=np.array(
                    [
                        [
                            [0.18 + 0.01 * index, 0.04],
                            [0.00, 0.28 + 0.01 * index],
                        ]
                    ]
                ),
            )


def write_donjon_deck(path: Path, mco_ref: str, burnup: float) -> None:
    path.write_text(
        "\n".join(
            [
                "*----",
                "*  Experimental BURN-axis MULTICOMPO consumer smoke.",
                "*----",
                "MODULE NCR: UTL: END: ABORT: ;",
                "LINKED_LIST CPO MACRO ;",
                f"SEQ_ASCII CPO_ASC :: FILE '{mco_ref}' ;",
                "",
                "CPO := CPO_ASC ;",
                "",
                "MACRO := NCR: CPO :: EDIT 1 MACRO NMIX 1",
                "  COMPO CPO CPO",
                "  MIX 1",
                f"    SET LINEAR 'BURN' {burnup:.8E}",
                "  ENDMIX",
                "  ;",
                "",
                "UTL: MACRO :: IMPR STATE-VECTOR * DUMP ;",
                "",
                f"ECHO \"openmc2donjon burnup-axis smoke BURN={burnup:g}\" ;",
                "END: ;",
                "",
            ]
        )
    )


def validate(run_dir: Path, results: list[Path]) -> None:
    if len(results) != len(BURNUP_VALUES):
        raise SystemExit(
            f"expected {len(BURNUP_VALUES)} --result values, received {len(results)}"
        )

    from openmc2donjon.macrolib import read_macrolib_ascii

    for burnup, result in zip(BURNUP_VALUES, results, strict=True):
        macrolib = read_macrolib_ascii(result)
        expected = TOTALS[burnup].reshape((1, -1))
        if macrolib.state_vector[:2] != (2, 1):
            raise SystemExit(
                f"{result}: unexpected MACROLIB state prefix "
                f"{macrolib.state_vector[:2]}"
            )
        if not np.allclose(macrolib.ntot0, expected, rtol=1.0e-6, atol=1.0e-8):
            raise SystemExit(
                f"{result}: NTOT0 mismatch for BURN={burnup:g}; "
                f"actual={macrolib.ntot0.tolist()} expected={expected.tolist()}"
            )
        print(
            f"PASS BURN={burnup:g} NTOT0="
            f"{' '.join(f'{value:.8E}' for value in macrolib.ntot0[0])}"
        )

    manifest = run_dir / "burnup_axis_smoke_manifest.json"
    if not manifest.is_file():
        raise SystemExit(f"missing manifest: {manifest}")
    print("burnup_axis_smoke_passed")


def _burnup_tag(value: float) -> str:
    return ("%g" % value).replace(".", "p")


if __name__ == "__main__":
    raise SystemExit(main())
