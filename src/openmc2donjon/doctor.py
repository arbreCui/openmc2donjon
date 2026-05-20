"""Environment diagnostics for openmc2donjon."""

from __future__ import annotations

import importlib
import json
import platform
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import __version__
from .openmc_statepoint import dry_run_openmc_statepoint_recipe


SCHEMA = "openmc2donjon.doctor.v1"
REQUIRED_PYTHON = (3, 10)
CONSOLE_SCRIPTS = (
    "openmc2donjon",
    "openmc2donjon-export",
    "openmc2donjon-from-openmc",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


@dataclass
class DoctorReport:
    schema: str = SCHEMA
    ok: bool = True
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append(CheckResult(name=name, status=status, detail=detail))
        if status == "FAIL":
            self.ok = False


def run_doctor(
    *,
    recipe: Path | None = None,
    statepoint: Path | None = None,
    load_statepoint: bool = False,
    summary_json: Path | None = None,
) -> DoctorReport:
    """Run environment diagnostics, print a report, and optionally write JSON."""

    report = DoctorReport()
    _check_python(report)
    _check_package(report)
    _check_import(report, "numpy")
    _check_import(report, "h5py")
    _check_optional_import(report, "openmc")
    _check_console_scripts(report)
    if recipe is not None:
        _check_recipe(report, recipe, statepoint, load_statepoint)

    print_report(report)
    if summary_json is not None:
        write_summary(summary_json, report)
    return report


def print_report(report: DoctorReport) -> None:
    print("OpenMC-to-DONJON doctor")
    print(f"  schema: {SCHEMA}")
    print()
    for check in report.checks:
        print(f"  {check.status:<4} {check.name}: {check.detail}")
    print()
    print("Doctor decision")
    print(f"  {'openmc2donjon_doctor_passed' if report.ok else 'openmc2donjon_doctor_failed'}")


def write_summary(path: Path, report: DoctorReport) -> None:
    payload = {
        "schema": report.schema,
        "decision": "openmc2donjon_doctor_passed"
        if report.ok
        else "openmc2donjon_doctor_failed",
        "ok": report.ok,
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "detail": check.detail,
            }
            for check in report.checks
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _check_python(report: DoctorReport) -> None:
    version = sys.version_info
    detail = (
        f"{version.major}.{version.minor}.{version.micro} "
        f"({platform.python_implementation()}, {sys.executable})"
    )
    if version < REQUIRED_PYTHON:
        report.add("python", "FAIL", f"{detail}; requires >= 3.10")
    else:
        report.add("python", "OK", detail)


def _check_package(report: DoctorReport) -> None:
    report.add("openmc2donjon", "OK", f"version {__version__}")


def _check_import(report: DoctorReport, module_name: str) -> None:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        report.add(module_name, "FAIL", f"cannot import: {exc}")
        return
    report.add(module_name, "OK", _module_detail(module))


def _check_optional_import(report: DoctorReport, module_name: str) -> None:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        report.add(module_name, "WARN", f"optional import unavailable: {exc}")
        return
    report.add(module_name, "OK", _module_detail(module))


def _check_console_scripts(report: DoctorReport) -> None:
    for name in CONSOLE_SCRIPTS:
        path = shutil.which(name)
        if path is None:
            report.add(f"script:{name}", "WARN", "console script not found on PATH")
        else:
            report.add(f"script:{name}", "OK", path)


def _check_recipe(
    report: DoctorReport,
    recipe: Path,
    statepoint: Path | None,
    load_statepoint: bool,
) -> None:
    try:
        summary = dry_run_openmc_statepoint_recipe(
            recipe,
            statepoint_path=statepoint,
            load_statepoint=load_statepoint,
        )
    except Exception as exc:
        report.add("recipe", "FAIL", f"{recipe}: dry-run failed: {exc}")
        return
    statepoint_detail = "none"
    if summary.statepoint_path is not None:
        statepoint_detail = (
            f"{summary.statepoint_path} "
            f"({'loaded' if summary.statepoint_loaded else 'not loaded'})"
        )
    report.add(
        "recipe",
        "OK",
        (
            f"{summary.recipe_path}; mixtures={len(summary.domains)} "
            f"groups={summary.energy_groups} P{summary.legendre_order} "
            f"statepoint={statepoint_detail}"
        ),
    )
    for check in summary.production_checks:
        status = "OK" if check.status == "PASS" else check.status
        report.add("recipe-check", status, f"{check.name}: {check.detail}")
    for warning in summary.warnings:
        report.add("recipe-warning", "WARN", warning)


def _module_detail(module: Any) -> str:
    version = getattr(module, "__version__", None)
    path = getattr(module, "__file__", None)
    if version and path:
        return f"version {version}; {path}"
    if version:
        return f"version {version}"
    if path:
        return str(path)
    return "imported"
