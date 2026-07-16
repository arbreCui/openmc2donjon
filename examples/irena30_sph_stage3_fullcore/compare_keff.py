#!/usr/bin/env python3
"""Withdrawn Stage 3 diagnostic: CE truth k vs MG twin and DONJON SN8 k.

Compares against the CE full-core statepoint:

- the uncorrected assembly-homogenized MG full core (iteration-1 statepoint),
- the SPH-corrected assembly-homogenized MG full core (a final statepoint that
  consumes the same final sidecar as the DONJON handoff),
- optionally the DONJON SN8 solves of the uncorrected and SPH-corrected
  multicompos.

Reports the homogenization defect (uncorrected - CE), the residual after
correction (corrected - CE), and the recovered-defect fraction
(corrected - uncorrected) / (CE - uncorrected).  The summary also records
whether the correction actually reduced the absolute defect.  This archived
OpenMC-MG-side route can report diagnostic gate results, but it can never emit
IRENA full-core physics acceptance.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import openmc

SN8_PATTERN = r"OPENMC2DONJON IRENA30 STAGE3 SN8 K-EFFECTIVE\s+([0-9.+\-Ee]+)"


def read_openmc_metrics(statepoint: Path) -> tuple[float, float, float, float]:
    with openmc.StatePoint(str(statepoint)) as sp:
        leakage_rows = [
            row
            for row in sp.global_tallies
            if row["name"].decode("utf-8") == "leakage"
        ]
        if len(leakage_rows) != 1:
            raise SystemExit(f"expected one leakage global tally in {statepoint}")
        leakage = leakage_rows[0]
        return (
            float(sp.keff.nominal_value),
            float(sp.keff.std_dev),
            float(leakage["mean"]),
            float(leakage["std_dev"]),
        )


def read_donjon_keff(result: Path) -> float:
    text = result.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(SN8_PATTERN, text)
    if not matches:
        raise SystemExit(f"no DONJON k-effective found in {result}")
    value = float(matches[-1])
    if value != value:  # NaN
        raise SystemExit(f"DONJON k-effective is NaN in {result}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ce-statepoint", type=Path, required=True)
    parser.add_argument("--mg-uncorrected-statepoint", type=Path, required=True)
    parser.add_argument("--mg-corrected-statepoint", type=Path, required=True)
    parser.add_argument(
        "--sph-summary",
        type=Path,
        default=None,
        help="final make-openmc-sph-sidecar summary used for a convergence decision",
    )
    parser.add_argument(
        "--max-sph-update-residual",
        type=float,
        default=None,
        help="maximum accepted abs(raw SPH update - 1); requires --sph-summary",
    )
    parser.add_argument("--sph-strategy", default=None)
    parser.add_argument("--power-summary", type=Path, default=None)
    parser.add_argument("--sn8-uncorrected-result", type=Path, default=None)
    parser.add_argument("--sn8-corrected-result", type=Path, default=None)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()

    if args.max_sph_update_residual is not None:
        if args.sph_summary is None:
            parser.error("--max-sph-update-residual requires --sph-summary")
        if not math.isfinite(args.max_sph_update_residual) or args.max_sph_update_residual < 0:
            parser.error("--max-sph-update-residual must be finite and non-negative")

    ce_keff, ce_std, ce_leakage, ce_leakage_std = read_openmc_metrics(
        args.ce_statepoint
    )
    mg_unc_keff, mg_unc_std, mg_unc_leakage, mg_unc_leakage_std = (
        read_openmc_metrics(args.mg_uncorrected_statepoint)
    )
    mg_cor_keff, mg_cor_std, mg_cor_leakage, mg_cor_leakage_std = (
        read_openmc_metrics(args.mg_corrected_statepoint)
    )

    def pcm(value: float) -> float:
        return (value - ce_keff) / ce_keff * 1.0e5

    defect_pcm = pcm(mg_unc_keff)
    residual_pcm = pcm(mg_cor_keff)
    recovered_pcm = residual_pcm - defect_pcm
    recovered_fraction = recovered_pcm / -defect_pcm if defect_pcm != 0.0 else None
    improved_defect = abs(residual_pcm) < abs(defect_pcm)
    uncorrected_leakage_error = mg_unc_leakage - ce_leakage
    corrected_leakage_error = mg_cor_leakage - ce_leakage
    improved_leakage = abs(corrected_leakage_error) < abs(
        uncorrected_leakage_error
    )

    summary: dict[str, object] = {
        "schema": "openmc2donjon.irena30-withdrawn-stage3-diagnostic.v1",
        "lifecycle": "withdrawn-diagnostic",
        "physics_accepted": False,
        "production_ready": False,
        "ce_keff": ce_keff,
        "ce_std": ce_std,
        "ce_std_pcm": ce_std / ce_keff * 1.0e5,
        "ce_leakage_fraction": ce_leakage,
        "ce_leakage_std": ce_leakage_std,
        "mg_uncorrected_keff": mg_unc_keff,
        "mg_uncorrected_std": mg_unc_std,
        "mg_uncorrected_delta_pcm": defect_pcm,
        "mg_uncorrected_leakage_fraction": mg_unc_leakage,
        "mg_uncorrected_leakage_std": mg_unc_leakage_std,
        "mg_uncorrected_leakage_error": uncorrected_leakage_error,
        "mg_corrected_keff": mg_cor_keff,
        "mg_corrected_std": mg_cor_std,
        "mg_corrected_delta_pcm": residual_pcm,
        "mg_corrected_leakage_fraction": mg_cor_leakage,
        "mg_corrected_leakage_std": mg_cor_leakage_std,
        "mg_corrected_leakage_error": corrected_leakage_error,
        "recovered_pcm": recovered_pcm,
        "recovered_fraction": recovered_fraction,
        "improved_defect": improved_defect,
        "improved_leakage": improved_leakage,
        "ce_statepoint": str(args.ce_statepoint),
        "mg_uncorrected_statepoint": str(args.mg_uncorrected_statepoint),
        "mg_corrected_statepoint": str(args.mg_corrected_statepoint),
    }
    if args.sph_strategy is not None:
        summary["sph_strategy"] = args.sph_strategy
    acceptance_reasons: list[str] = []
    if not improved_defect:
        acceptance_reasons.append("OpenMC MG correction did not reduce the CE/MG defect")
    if not improved_leakage:
        acceptance_reasons.append(
            "OpenMC MG correction did not reduce the CE/MG leakage error"
        )

    print("IRENA-30 Stage 3 full-core closure (deltas vs CE truth)")
    print(f"  OpenMC CE truth:      {ce_keff:.6f} +/- {ce_std / ce_keff * 1.0e5:.1f} pcm")
    print(f"  MG full core uncorr:   {mg_unc_keff:.6f}  delta {defect_pcm:+.1f} pcm (defect)")
    print(f"  MG full core SPH:      {mg_cor_keff:.6f}  delta {residual_pcm:+.1f} pcm (residual)")
    print(
        "  leakage CE/unc/cor:   "
        f"{ce_leakage:.5%} / {mg_unc_leakage:.5%} / {mg_cor_leakage:.5%}"
    )
    if args.sph_strategy is not None:
        print(f"  SPH strategy:          {args.sph_strategy}")
    if recovered_fraction is not None:
        outcome = "improved" if improved_defect else "worsened"
        print(
            f"  defect change:        {recovered_pcm:+.1f} pcm "
            f"(recovery {recovered_fraction:.1%}; {outcome})"
        )

    donjon_deltas: dict[str, float] = {}
    for tag, result in (
        ("uncorrected", args.sn8_uncorrected_result),
        ("corrected", args.sn8_corrected_result),
    ):
        if result is None:
            continue
        keff = read_donjon_keff(result)
        summary[f"donjon_sn8_{tag}_keff"] = keff
        summary[f"donjon_sn8_{tag}_delta_pcm"] = pcm(keff)
        summary[f"sn8_{tag}_result"] = str(result)
        donjon_deltas[tag] = pcm(keff)
        print(f"  DONJON SN8 {tag:>11}: {keff:.6f}  delta {pcm(keff):+.1f} pcm")

    if set(donjon_deltas) == {"uncorrected", "corrected"}:
        donjon_improved = abs(donjon_deltas["corrected"]) < abs(
            donjon_deltas["uncorrected"]
        )
        summary["donjon_improved_defect"] = donjon_improved
        if not donjon_improved:
            acceptance_reasons.append(
                "DONJON correction did not reduce the CE/DONJON defect"
            )
    else:
        acceptance_reasons.append("DONJON uncorrected/corrected closure was not evaluated")

    if args.sph_summary is not None:
        sph_summary = json.loads(args.sph_summary.read_text(encoding="utf-8"))
        raw_min = float(sph_summary["raw_update_minimum"])
        raw_max = float(sph_summary["raw_update_maximum"])
        update_residual = max(abs(raw_min - 1.0), abs(raw_max - 1.0))
        summary["sph_summary"] = str(args.sph_summary)
        summary["sph_raw_update_minimum"] = raw_min
        summary["sph_raw_update_maximum"] = raw_max
        summary["sph_max_update_residual"] = update_residual
        if args.max_sph_update_residual is not None:
            sph_converged = update_residual <= args.max_sph_update_residual
            summary["sph_max_update_residual_limit"] = args.max_sph_update_residual
            summary["sph_converged"] = sph_converged
            print(
                f"  SPH update residual:  {update_residual:.1%} "
                f"(limit {args.max_sph_update_residual:.1%})"
            )
            if not sph_converged:
                acceptance_reasons.append("final SPH raw update is not converged")

    if args.power_summary is not None:
        power = json.loads(args.power_summary.read_text(encoding="utf-8"))
        power_improved = bool(power.get("corrected_improved", False))
        summary["power_summary"] = str(args.power_summary)
        summary["power_shape_corrected_improved"] = power_improved
        summary["power_shape_uncorrected"] = power.get("uncorrected")
        summary["power_shape_corrected"] = power.get("corrected")
        corrected_power = power.get("corrected")
        if isinstance(corrected_power, dict):
            print(
                "  corrected power:      "
                f"max={float(corrected_power['maximum_absolute_relative_error']):.2%} "
                f"rms={float(corrected_power['rms_relative_error']):.2%}"
            )
        if not power_improved:
            acceptance_reasons.append(
                "SPH correction did not improve both maximum and RMS power-shape errors"
            )
    else:
        acceptance_reasons.append("OpenMC MG power-shape closure was not evaluated")

    diagnostic_gate_passed = not acceptance_reasons
    withdrawal_reason = (
        "This OpenMC-MG-side Stage 3 route is permanently withdrawn; current "
        "IRENA acceptance requires the 91-position or exact 21-D3-orbit "
        "transport-pooled Converter-to-native-DRAGON route."
    )
    summary["diagnostic_gate_passed"] = diagnostic_gate_passed
    summary["stage3_accepted"] = False
    summary["withdrawal_reason"] = withdrawal_reason
    summary["diagnostic_gate_failures"] = acceptance_reasons
    status = "PASSED" if diagnostic_gate_passed else "FAILED"
    print(f"  Diagnostic gates:    {status}")
    print("  Physics decision:    WITHDRAWN / REJECTED")
    print(f"    - {withdrawal_reason}")
    for reason in acceptance_reasons:
        print(f"    - {reason}")

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  summary: {args.summary}")
    return 0 if diagnostic_gate_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
