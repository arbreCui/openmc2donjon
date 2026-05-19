#!/usr/bin/env python3
"""Validate manifest-driven handoff case definitions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


sys.dont_write_bytecode = True

ROOT = Path(os.environ.get("OPENMC2DONJON_ROOT", "/Users/wen/dragon-5.1"))
DONJON_DIR = ROOT / "Donjon"
DATA_DIR = DONJON_DIR / "data/openmc2donjon"
MANIFEST_DIR = DATA_DIR / "case_manifests"
PACKAGE_SRC = Path(
    os.environ.get("OPENMC2DONJON_SRC", "/Users/wen/openmc-workspace/openmc2donjon/src")
)
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from validate_mgxs_input_contract import output_name_issue  # noqa: E402


CASE_SCHEMA = "openmc2donjon.handoff-case.v1"
DECISION_PASS = "handoff_case_manifests_valid"
DECISION_FAIL = "handoff_case_manifests_invalid"
REQUIRED_CASES = {
    "c5g7_production_diffusion.json",
}


def main() -> int:
    args = parse_args()
    manifests = args.manifest or sorted(MANIFEST_DIR.glob("*.json"))
    checks: list[tuple[str, bool, str]] = []

    print("OpenMC-to-DONJON handoff case manifest validator")
    print(f"  manifest_dir: {MANIFEST_DIR}")
    print()

    checks.append(("manifest directory exists", MANIFEST_DIR.is_dir(), str(MANIFEST_DIR)))
    found = {path.name for path in manifests}
    checks.append(
        (
            "required accepted case manifests are present",
            REQUIRED_CASES.issubset(found),
            ",".join(sorted(found)),
        )
    )

    for path in manifests:
        checks.extend(validate_manifest(path))

    ok = all(check[1] for check in checks)
    for label, passed, detail in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {label}: {detail}")

    print()
    print("Handoff case manifest decision")
    print(f"  {DECISION_PASS if ok else DECISION_FAIL}")
    return 0 if ok or not args.check else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="*",
        type=Path,
        help="case manifest JSON; default validates all manifests under case_manifests",
    )
    parser.add_argument("--check", action="store_true", help="return non-zero on validation failure")
    return parser.parse_args()


def validate_manifest(path: Path) -> list[tuple[str, bool, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    case_name = str(data.get("case_name") or path.stem)
    fixture_run_dir = DATA_DIR / "case_runs" / f"{case_name}_VALIDATION"
    checks: list[tuple[str, bool, str]] = []

    def add(label: str, passed: bool, detail: str) -> None:
        checks.append((f"{path.name}: {label}", passed, detail))

    add("schema is current", data.get("schema") == CASE_SCHEMA, str(data.get("schema")))
    add("case_name matches filename", case_name == path.stem, case_name)
    for key in ("input_h5", "format", "output", "preflight"):
        add(f"required key {key} is present", key in data, str(data.get(key)))

    output_format = str(data.get("format"))
    add("format is supported", output_format in {"multicompo", "macrolib"}, output_format)

    output_raw = str(data.get("output", ""))
    output_path = resolve_case_path(output_raw, fixture_run_dir, case_name)
    add("output uses run-dir placeholder", "$RUN_DIR" in output_raw, output_raw)
    add(
        "output is kept under run outputs",
        output_path.parent == fixture_run_dir / "outputs",
        str(output_path),
    )
    issue = output_name_issue(output_path, output_format)
    add("output extension matches format", issue is None, issue or output_path.name)

    input_path = resolve_data_path(str(data.get("input_h5", "")))
    add("input HDF5 exists", input_path.is_file(), str(input_path))

    preflight = data.get("preflight", {})
    add(
        "preflight requires transport dataset",
        preflight.get("require_transport_dataset") is True,
        str(preflight),
    )
    add("preflight requires volume", preflight.get("require_volume") is True, str(preflight))
    if preflight.get("require_adf"):
        faces = preflight.get("expected_adf_faces", [])
        add("ADF face list is explicit", isinstance(faces, list) and bool(faces), ",".join(faces))

    deck = data.get("donjon", {})
    if deck:
        template = resolve_data_path(str(deck.get("deck_template", "")))
        replace_path = str(resolve_data_path(str(deck.get("replace_path", ""))))
        add("DONJON deck template exists", template.is_file(), str(template))
        add("DONJON replace_path is absolute data path", replace_path.startswith(str(DATA_DIR)), replace_path)
        text = template.read_text(encoding="utf-8", errors="replace") if template.is_file() else ""
        add("DONJON replace_path occurs in template", replace_path in text, replace_path)
        add("expected keff is recorded", "expected_keff" in deck, str(deck.get("expected_keff")))
        add("keff tolerance is recorded", "keff_tolerance" in deck, str(deck.get("keff_tolerance")))
        generated = resolve_deck_output_path(
            deck.get("generated_deck", f"{fixture_run_dir.name}_{template.name}"),
            fixture_run_dir,
            case_name,
        )
        add(
            "generated deck stays under run decks",
            generated.parent == fixture_run_dir / "decks",
            str(generated),
        )

    return checks


def expand_case_text(raw: str | Path, run_dir: Path, case_name: str) -> str:
    text = str(raw)
    replacements = {
        "$RUN_DIR": str(run_dir),
        "${RUN_DIR}": str(run_dir),
        "$CASE_NAME": case_name,
        "${CASE_NAME}": case_name,
        "$DATA_DIR": str(DATA_DIR),
        "${DATA_DIR}": str(DATA_DIR),
        "$DONJON_DIR": str(DONJON_DIR),
        "${DONJON_DIR}": str(DONJON_DIR),
        "$ROOT": str(ROOT),
        "${ROOT}": str(ROOT),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text


def resolve_case_path(raw: str | Path, run_dir: Path, case_name: str) -> Path:
    path = Path(expand_case_text(raw, run_dir, case_name))
    if path.is_absolute():
        return path.resolve()
    return (DATA_DIR / path).resolve()


def resolve_data_path(raw: str | Path) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path.resolve()
    return (DATA_DIR / path).resolve()


def resolve_deck_output_path(raw: str | Path, run_dir: Path, case_name: str) -> Path:
    path = Path(expand_case_text(raw, run_dir, case_name))
    if path.is_absolute():
        return path.resolve()
    return (run_dir / "decks" / path).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
