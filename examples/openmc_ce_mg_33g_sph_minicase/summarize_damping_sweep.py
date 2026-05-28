"""Summarize several OpenMC-side SPH damping runs side by side.

This is a small review helper for the CE/MG colorset minicase.  It reads the
``physics_summary.json`` files written by ``summarize_outputs.py`` and extracts
the quantities that matter when choosing a damping value:

* final SPH/update range,
* current-solve reaction-rate residual,
* frozen-flux residual after applying the newly generated SPH factors,
* CE/MG flux uncertainty.

It deliberately does not rerun OpenMC.  Use ``run_workflow.sh`` to generate the
individual runs, then point this script at their run roots, handoff directories,
or ``physics_summary.json`` files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SWEEP_SCHEMA = "openmc2donjon.openmc-ce-mg-sph-damping-sweep.v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help=(
            "case label and run path; PATH may be a run root, handoff directory, "
            "or physics_summary.json (repeatable)"
        ),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("damping_sweep_summary.json"),
        help="summary JSON path (default: damping_sweep_summary.json)",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("damping_sweep_summary.md"),
        help="Markdown report path (default: damping_sweep_summary.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = summarize_sweep(args.case)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(render_markdown(summary), encoding="utf-8")
    print(f"wrote damping sweep JSON: {args.output_json}")
    print(f"wrote damping sweep Markdown: {args.output_md}")
    return 0


def summarize_sweep(case_specs: list[str]) -> dict[str, Any]:
    cases = [_case_row(label, path) for label, path in map(_parse_case_spec, case_specs)]
    return {
        "schema": SWEEP_SCHEMA,
        "case_count": len(cases),
        "cases": cases,
        "best_by_after_update_residual": _best_case(cases, "after_update_max_relative_residual"),
        "best_by_current_solve_residual": _best_case(cases, "current_max_relative_residual"),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# OpenMC-side SPH Damping Sweep",
        "",
        "Each row is one completed CE/MG/SPH minicase. `current residual` is",
        "the reaction-rate residual in the latest OpenMC MG solve using the",
        "SPH factors that actually generated that solve. `after-update",
        "residual` applies the newly generated SPH factors to the same MG",
        "flux as a frozen-flux diagnostic for the next iteration.",
        "",
        "| case | damping | iterations | current residual | after-update residual | "
        "SPH range | update range | max flux rel std | worst after-update bin |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in summary["cases"]:
        worst = row.get("after_update_worst")
        if isinstance(worst, dict):
            worst_text = "{reaction} {mixture} g{group}".format(
                reaction=worst.get("reaction", "n/a"),
                mixture=worst.get("mixture", "n/a"),
                group=worst.get("group", "n/a"),
            )
        else:
            worst_text = "n/a"
        lines.append(
            (
                "| {label} | {damping} | {iterations} | {current} | {after} | "
                "{sph_min}..{sph_max} | {update_min}..{update_max} | {flux_std} | {worst} |"
            ).format(
                label=row["label"],
                damping=_fmt_optional(row.get("damping")),
                iterations=row.get("iterations", 0),
                current=_fmt_optional(row.get("current_max_relative_residual")),
                after=_fmt_optional(row.get("after_update_max_relative_residual")),
                sph_min=_fmt_optional(row.get("sph_min")),
                sph_max=_fmt_optional(row.get("sph_max")),
                update_min=_fmt_optional(row.get("raw_update_minimum")),
                update_max=_fmt_optional(row.get("raw_update_maximum")),
                flux_std=_fmt_optional(row.get("max_flux_relative_std_dev")),
                worst=worst_text,
            )
        )
    lines.extend(
        [
            "",
            "## Selection Hints",
            "",
            _best_line(summary, "best_by_after_update_residual", "Best frozen-flux residual"),
            _best_line(summary, "best_by_current_solve_residual", "Best current-solve residual"),
            "",
        ]
    )
    return "\n".join(lines)


def _case_row(label: str, path: Path) -> dict[str, Any]:
    summary_path = _summary_path(path)
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    iterations = payload.get("sph_iterations")
    last_iteration = iterations[-1] if isinstance(iterations, list) and iterations else {}
    sph = payload.get("sph", {})
    quality = payload.get("quality", {})
    preservation = payload.get("reaction_rate_preservation", {})
    current = preservation.get("current_solve", {})
    after = preservation.get("after_sph_update_frozen_flux", {})
    return {
        "label": label,
        "summary_path": str(summary_path),
        "damping": _optional_float(last_iteration.get("damping")),
        "iterations": len(iterations) if isinstance(iterations, list) else 0,
        "sph_min": _optional_float(sph.get("minimum")),
        "sph_max": _optional_float(sph.get("maximum")),
        "raw_update_minimum": _optional_float(last_iteration.get("raw_update_minimum")),
        "raw_update_maximum": _optional_float(last_iteration.get("raw_update_maximum")),
        "current_max_relative_residual": _optional_float(
            current.get("max_relative_residual")
        ),
        "current_mean_relative_residual": _optional_float(
            current.get("mean_relative_residual")
        ),
        "current_worst": current.get("worst"),
        "after_update_max_relative_residual": _optional_float(
            after.get("max_relative_residual")
        ),
        "after_update_mean_relative_residual": _optional_float(
            after.get("mean_relative_residual")
        ),
        "after_update_worst": after.get("worst"),
        "max_flux_relative_std_dev": _optional_float(
            quality.get("max_flux_relative_std_dev")
        ),
        "quality_decision": quality.get("decision"),
        "production_ready": bool(quality.get("production_ready", False)),
    }


def _parse_case_spec(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        path = Path(raw)
        return path.name or "case", path
    label, path = raw.split("=", 1)
    label = label.strip()
    if not label:
        raise ValueError(f"case label cannot be empty: {raw!r}")
    return label, Path(path)


def _summary_path(path: Path) -> Path:
    path = path.expanduser().resolve()
    candidates = [path]
    if path.is_dir():
        candidates = [
            path / "physics_summary.json",
            path / "handoff" / "physics_summary.json",
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"cannot find physics_summary.json from {path}")


def _best_case(cases: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    valid = [case for case in cases if case.get(key) is not None]
    if not valid:
        return None
    best = min(valid, key=lambda case: float(case[key]))
    return {
        "label": best["label"],
        key: best[key],
        "damping": best.get("damping"),
        "iterations": best.get("iterations"),
    }


def _best_line(summary: dict[str, Any], key: str, label: str) -> str:
    best = summary.get(key)
    if not isinstance(best, dict):
        return f"- {label}: n/a"
    metric = next((name for name in best if name.endswith("_residual")), None)
    value = _fmt_optional(best.get(metric)) if metric is not None else "n/a"
    return (
        f"- {label}: `{best.get('label')}` "
        f"(damping={_fmt_optional(best.get('damping'))}, residual={value})"
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _fmt_optional(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
