#!/usr/bin/env python3
"""Run one exact IRENA local signature through OpenMC, Converter, and SPH."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess

from topology import BY_ID


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("signature", choices=tuple(BY_ID))
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--reuse-ce", action="store_true")
    parser.add_argument("--batches", type=int)
    parser.add_argument("--inactive", type=int)
    parser.add_argument("--particles", type=int)
    parser.add_argument("--openmc-threads", type=int)
    args = parser.parse_args(argv)

    signature = BY_ID[args.signature]
    repo_root = Path(__file__).resolve().parents[2]
    runner = (
        repo_root
        / "examples"
        / "irena30_sph_stage2_csd"
        / "run_native_colorset_component.sh"
    )
    run_root = (
        args.run_root.expanduser().resolve()
        if args.run_root is not None
        else repo_root
        / ".openmc2donjon-runs"
        / "irena_fullcore_signature_project"
        / "signatures"
        / signature.id
    )
    env = os.environ.copy()
    env.update(
        {
            "IRENA_SPH2_CASE": signature.id,
            "IRENA_SPH2_CENTER_KIND": signature.center,
            "IRENA_SPH2_NEIGHBOR_KINDS": ",".join(signature.neighbors),
            "IRENA_SPH2_SCATTER_MOMENTS": "2",
            "RUN_ROOT": str(run_root),
            "REUSE_CE": "1" if args.reuse_ce else "0",
        }
    )
    for name, value in (
        ("BATCHES", args.batches),
        ("INACTIVE", args.inactive),
        ("PARTICLES", args.particles),
        ("OPENMC_THREADS", args.openmc_threads),
    ):
        if value is not None:
            if value <= 0:
                parser.error(f"--{name.lower().replace('_', '-')} must be positive")
            env[name] = str(value)
    return subprocess.run(
        ["bash", str(runner), signature.id],
        cwd=repo_root,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
