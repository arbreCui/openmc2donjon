#!/usr/bin/env python3
"""Validate the locked C5G7 OpenMC-to-DONJON accepted baseline."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py


ROOT = Path("/Users/wen/dragon-5.1")
DATA = ROOT / "Donjon/data/openmc2donjon"
VERSION_FILE = DATA / "VERSION"
DEFAULT_MANIFEST = DATA / "accepted_baseline_manifest.json"
SCHEMA = "openmc2donjon.accepted-baseline.v2"
DECISION = "c5g7_assembly_wise_baseline_locked"
KEFF_TOL = 5.0e-10
ANM_TOL = 5.0e-8


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def main() -> int:
    args = parse_args()
    manifest = load_json(args.manifest.resolve())
    checks = [
        *manifest_checks(manifest),
        *artifact_checks(manifest),
        *c5g7_checks(manifest),
        hex_status_check(manifest),
    ]

    print("OpenMC-to-DONJON accepted baseline")
    print(f"  manifest: {args.manifest.resolve()}")
    print()

    ok = True
    for check in checks:
        ok = ok and check.passed
        print(f"  {'PASS' if check.passed else 'FAIL'}  {check.name}: {check.detail}")

    print()
    print("Accepted baseline decision")
    print(f"  {DECISION if ok else 'accepted_baseline_inconsistent'}")
    return 0 if ok or not args.check else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--check", action="store_true", help="return non-zero on validation failure")
    return parser.parse_args()


def manifest_checks(manifest: dict[str, Any]) -> list[Check]:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    return [
        Check("schema is current", manifest.get("schema") == SCHEMA, str(manifest.get("schema"))),
        Check(
            "version matches workspace VERSION",
            manifest.get("version") == version,
            f"manifest={manifest.get('version')} version_file={version}",
        ),
        Check("decision is locked", manifest.get("decision") == DECISION, str(manifest.get("decision"))),
    ]


def artifact_checks(manifest: dict[str, Any]) -> list[Check]:
    c5g7 = manifest["lines"]["c5g7"]
    checks = [
        Check("C5G7 MGXS exists", resolve(c5g7["production_mgxs"]).is_file(), c5g7["production_mgxs"]),
        Check("C5G7 MULTICOMPO exists", resolve(c5g7["production_mco"]).is_file(), c5g7["production_mco"]),
    ]
    for label, row in c5g7["results"].items():
        checks.append(Check(f"C5G7 result exists: {label}", resolve(row["path"]).is_file(), row["path"]))
    return checks


def c5g7_checks(manifest: dict[str, Any]) -> list[Check]:
    c5g7 = manifest["lines"]["c5g7"]
    attrs = read_h5_attrs(resolve(c5g7["production_mgxs"]))
    checks = [
        Check("C5G7 domain mode is assembly", attrs.get("domain_mode") == "assembly", str(attrs.get("domain_mode"))),
        Check("C5G7 group count is locked", attrs.get("energy_groups") == c5g7["energy_groups"], str(attrs.get("energy_groups"))),
        Check("C5G7 Legendre order is locked", attrs.get("legendre_order") == c5g7["legendre_order"], str(attrs.get("legendre_order"))),
        Check(
            "C5G7 real ADF payload is production",
            attrs.get("adf_kind") == "production" and attrs.get("adf_real") == "true",
            f"kind={attrs.get('adf_kind')} real={attrs.get('adf_real')}",
        ),
    ]
    for label in ("diffusion", "spn3", "spn3_scat1"):
        row = c5g7["results"][label]
        checks.append(close_check(f"C5G7 {label} keff is locked", extract_keff(resolve(row["path"])), row["keff"], KEFF_TOL))

    nssf_path = resolve(c5g7["results"]["nssf_2g_adf"]["path"])
    adf_keff, nodf_keff = extract_nssf_pair(nssf_path)
    checks.append(close_check("C5G7 2g NSSF ADF keff is locked", adf_keff, c5g7["results"]["nssf_2g_adf"]["keff"], ANM_TOL))
    checks.append(close_check("C5G7 2g NSSF NODF keff is locked", nodf_keff, c5g7["results"]["nssf_2g_nodf"]["keff"], ANM_TOL))
    return checks


def hex_status_check(manifest: dict[str, Any]) -> Check:
    status = manifest.get("hex", {}).get("status")
    return Check(
        "hex line is marked capability-only",
        status == "capability_done_no_accepted_benchmark",
        str(status),
    )


def close_check(name: str, observed: float, expected: float, tolerance: float) -> Check:
    delta = abs(observed - expected)
    return Check(name, delta <= tolerance, f"observed={observed:.12g} expected={expected:.12g} delta={delta:.3g}")


def read_h5_attrs(path: Path) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    with h5py.File(path, "r") as handle:
        for key, value in handle.attrs.items():
            if getattr(value, "shape", ()) == () and hasattr(value, "item"):
                value = value.item()
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            attrs[key] = value
    return attrs


def extract_keff(path: Path) -> float:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"EFFECTIVE MULTIPLICATION FACTOR\s*=\s*([0-9.+\-Ee]+)", text)
    if not matches:
        matches = re.findall(r"K-EFFECTIVE\s+([0-9.+\-Ee]+)", text)
    if not matches:
        raise ValueError(f"no k-effective found in {path}")
    return float(matches[-1])


def extract_nssf_pair(path: Path) -> tuple[float, float]:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = [float(value) for value in re.findall(r"NSSFL4:\s+ANM KEFF=\s*([0-9.+\-Ee]+)", text)]
    if len(matches) < 2:
        raise ValueError(f"expected two NSSFL4 ANM KEFF lines in {path}")
    return matches[0], matches[1]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = DATA / path
    return path


if __name__ == "__main__":
    raise SystemExit(main())
