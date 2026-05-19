#!/usr/bin/env python3
"""Run a manifest-described OpenMC-to-DONJON handoff case."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any


sys.dont_write_bytecode = True

ROOT = Path(os.environ.get("OPENMC2DONJON_ROOT", "/Users/wen/dragon-5.1"))
DONJON_DIR = ROOT / "Donjon"
DATA_DIR = DONJON_DIR / "data/openmc2donjon"
RUNTIME_IO_DIR = Path(os.environ.get("OPENMC2DONJON_DONJON_IO_DIR", "/tmp/openmc2donjon_io"))
PACKAGE_SRC = Path(
    os.environ.get("OPENMC2DONJON_SRC", "/Users/wen/openmc-workspace/openmc2donjon/src")
)
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from convert_mgxs_with_preflight import main as convert_main  # noqa: E402


SCHEMA = "openmc2donjon.handoff-case.v1"
DECISION_PASS = "handoff_case_passed"
DECISION_FAIL = "handoff_case_failed"


def main() -> int:
    args = parse_args()
    manifest_path = args.manifest.resolve()
    manifest = load_manifest(manifest_path)
    case_name = manifest.get("case_name") or manifest_path.stem
    run_dir = resolve_run_dir(args.run_dir, case_name)
    output_path = resolve_case_path(manifest["output"], run_dir, case_name)
    output_archive = run_dir / "outputs" / output_path.name

    print("OpenMC-to-DONJON handoff case")
    print(f"  schema: {SCHEMA}")
    print(f"  manifest: {manifest_path}")
    print(f"  case: {case_name}")
    print(f"  run_dir: {run_dir}")
    print(f"  run_donjon: {args.run_donjon}")
    print()

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "decks").mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "schema": SCHEMA,
        "case_name": case_name,
        "manifest": str(manifest_path),
        "run_dir": str(run_dir),
        "run_donjon": args.run_donjon,
        "steps": [],
    }

    try:
        run_conversion(manifest, output_path)
        archived = archive_output(output_path, output_archive)
        summary["steps"].append(
            {
                "name": "convert",
                "status": "PASS",
                "output": str(output_path),
                "archive_output": str(output_archive),
                "archived_copy": archived,
            }
        )

        deck_info = maybe_generate_deck(manifest, output_path, run_dir, case_name)
        if deck_info:
            summary["steps"].append({"name": "deck", "status": "PASS", **deck_info})

        if args.run_donjon:
            if not deck_info:
                raise ValueError("manifest has no donjon deck section; cannot --run-donjon")
            result_info = run_donjon(deck_info, manifest.get("donjon", {}))
            summary["steps"].append({"name": "donjon", "status": "PASS", **result_info})

        summary["decision"] = DECISION_PASS
        print()
        print("Handoff case decision")
        print(f"  {DECISION_PASS}")
        return_code = 0
    except Exception as exc:
        summary["decision"] = DECISION_FAIL
        summary["error"] = str(exc)
        print()
        print("Handoff case decision")
        print(f"  {DECISION_FAIL}")
        print(f"  {exc}")
        return_code = 1

    summary_path = args.summary_json or run_dir / "handoff_case_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"summary: {summary_path}")
    return return_code


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="handoff case manifest JSON")
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="case run directory; default is DATA/case_runs/<case>_<timestamp>",
    )
    parser.add_argument(
        "--run-donjon",
        action="store_true",
        help="run the generated DONJON deck after conversion",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        default=None,
        help="write the machine-readable summary to this path",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = data.get("schema")
    if schema != SCHEMA:
        raise ValueError(f"{path}: schema={schema!r}, expected {SCHEMA!r}")
    for key in ("input_h5", "format", "output"):
        if key not in data:
            raise ValueError(f"{path}: missing required key {key!r}")
    if data["format"] not in ("multicompo", "macrolib"):
        raise ValueError(f"{path}: format must be 'multicompo' or 'macrolib'")
    return data


def resolve_run_dir(raw: Path | None, case_name: str) -> Path:
    if raw is not None:
        return raw.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DATA_DIR / "case_runs" / f"{case_name}_{stamp}"


def resolve_path(raw: str | Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return (DATA_DIR / path).resolve()


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


def resolve_deck_output_path(raw: str | Path, run_dir: Path, case_name: str) -> Path:
    path = Path(expand_case_text(raw, run_dir, case_name))
    if path.is_absolute():
        return path.resolve()
    return (run_dir / "decks" / path).resolve()


def archive_output(output_path: Path, output_archive: Path) -> bool:
    if output_path.resolve() == output_archive.resolve():
        print(f"output already under run archive: {output_path}")
        return False
    shutil.copy2(output_path, output_archive)
    print(f"archived output: {output_archive}")
    return True


def run_conversion(manifest: dict[str, Any], output_path: Path) -> None:
    preflight = manifest.get("preflight", {})
    conversion = manifest.get("conversion", {})
    argv = [
        str(resolve_path(manifest["input_h5"])),
        "--format",
        manifest["format"],
        "-o",
        str(output_path),
    ]
    if preflight.get("require_adf"):
        argv.append("--require-adf")
    if preflight.get("expected_adf_faces"):
        argv.extend(["--expected-adf-faces", ",".join(preflight["expected_adf_faces"])])
    if preflight.get("require_transport_dataset"):
        argv.append("--require-transport-dataset")
    if preflight.get("require_volume"):
        argv.append("--require-volume")
    for key, option in (
        ("root_name", "--root-name"),
        ("comment", "--comment"),
        ("burnup", "--burnup"),
        ("h_factor_default", "--h-factor-default"),
    ):
        if key in conversion and conversion[key] is not None:
            argv.extend([option, str(conversion[key])])
    for mixture in conversion.get("mixtures", []):
        argv.extend(["--mixture", str(mixture)])

    print("== Convert ==")
    old_argv = sys.argv
    try:
        sys.argv = ["convert_mgxs_with_preflight.py", *argv]
        status = convert_main()
    finally:
        sys.argv = old_argv
    if status != 0:
        raise RuntimeError(f"convert_mgxs_with_preflight failed with status {status}")


def maybe_generate_deck(
    manifest: dict[str, Any],
    output_path: Path,
    run_dir: Path,
    case_name: str,
) -> dict[str, Any] | None:
    deck = manifest.get("donjon")
    if not deck:
        return None
    template = resolve_path(deck["deck_template"])
    replace_path = str(resolve_path(deck["replace_path"]))
    deck_input = prepare_donjon_input(output_path, run_dir, case_name)
    generated = resolve_deck_output_path(
        deck.get("generated_deck", f"{run_dir.name}_{template.name}"),
        run_dir,
        case_name,
    )
    generated.parent.mkdir(parents=True, exist_ok=True)

    text = template.read_text(encoding="utf-8")
    if replace_path not in text:
        raise ValueError(f"{template}: replace_path not found: {replace_path}")
    text = text.replace(replace_path, deck_input["file_literal"])
    generated.write_text(text, encoding="utf-8")
    print()
    print("== DONJON deck ==")
    print(f"  template: {template}")
    print(f"  generated: {generated}")
    print(f"  deck input: {deck_input['file_literal']}")
    return {
        "deck_template": str(template),
        "generated_deck": str(generated),
        "deck_input": deck_input,
        "replace_path": replace_path,
    }


def prepare_donjon_input(output_path: Path, run_dir: Path, case_name: str) -> dict[str, Any]:
    """Create a short absolute alias for DONJON's fixed line parser."""
    source = output_path.resolve()
    digest = hashlib.sha1(str(run_dir.resolve()).encode("utf-8")).hexdigest()[:8]
    alias_dir = RUNTIME_IO_DIR / f"{short_case_name(case_name)}_{digest}"
    alias_dir.mkdir(parents=True, exist_ok=True)
    alias = alias_dir / source.name
    if source != alias.resolve():
        shutil.copy2(source, alias)
    file_literal = str(alias)
    return {
        "source": str(source),
        "alias": str(alias),
        "file_literal": file_literal,
        "line_length": len(f"SEQ_ASCII CPO_ASC :: FILE '{file_literal}' ;"),
    }


def short_case_name(case_name: str) -> str:
    letters = "".join(part[0] for part in re.split(r"[_\W]+", case_name) if part)
    fallback = re.sub(r"[^A-Za-z0-9]+", "", case_name)[:8]
    return (letters or fallback or "case").lower()[:8]


def run_donjon(deck_info: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    deck = Path(deck_info["generated_deck"])
    if not deck.is_file():
        raise FileNotFoundError(deck)
    if not (DONJON_DIR / "rdonjon").is_file():
        raise FileNotFoundError(DONJON_DIR / "rdonjon")

    deck_arg = rdonjon_deck_arg(deck)
    print()
    print("== DONJON ==")
    print(f"  ./rdonjon -q {deck_arg}")
    subprocess.run(["./rdonjon", "-q", deck_arg], cwd=DONJON_DIR, check=True)

    result = DONJON_DIR / "Darwin_arm64" / f"{deck.stem}.result"
    if not result.is_file():
        raise FileNotFoundError(result)
    text = result.read_text(encoding="utf-8", errors="replace")
    if "normal end of execution" not in text.lower():
        raise RuntimeError(f"DONJON listing did not reach normal end: {result}")

    observed = extract_keff(text)
    expected = config.get("expected_keff")
    tolerance = float(config.get("keff_tolerance", 0.0))
    if expected is not None:
        expected_value = float(expected)
        if observed is None:
            raise RuntimeError(f"could not extract k-effective from {result}")
        if abs(observed - expected_value) > tolerance:
            raise RuntimeError(
                f"k-effective mismatch: observed={observed:.12g} "
                f"expected={expected_value:.12g} tolerance={tolerance:.3g}"
            )
        print(f"  PASS  k-effective {observed:.12g}")
    print(f"  result: {result}")
    return {
        "deck_arg": deck_arg,
        "result": str(result),
        "keff": observed,
    }


def rdonjon_deck_arg(deck: Path) -> str:
    data_root = DONJON_DIR / "data"
    try:
        return str(deck.resolve().relative_to(data_root))
    except ValueError as exc:
        raise ValueError(
            f"generated deck must be under {data_root} so rdonjon can consume it: {deck}"
        ) from exc


def extract_keff(text: str) -> float | None:
    patterns = (
        r"EFFECTIVE MULTIPLICATION FACTOR\s*=\s*([0-9.+\-Ee]+)",
        r"K-EFFECTIVE\s+([0-9.+\-Ee]+)",
        r"ANM KEFF=\s*([0-9.+\-Ee]+)",
    )
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            return float(matches[-1])
    return None


if __name__ == "__main__":
    raise SystemExit(main())
