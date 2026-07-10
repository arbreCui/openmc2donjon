# IRENA SPH Stage 2 — CSD Absorber Colorset, CE Fine vs MG Coarse

Second stage of the three-model OpenMC-side SPH route for IRENA-30: the
explicit seven-assembly colorset with the CSD control assembly at the
center and six INT fuel neighbors (the DRAGON ``csd_int`` colorset case).
Unlike Stage 1's single fissile assembly (nearly self-consistent
homogenization, only the top group needed correction), the absorber
center gives SPH a substantial homogenization defect to correct.

```text
1. CE fine model    : explicit7 csd_int colorset from the IRENA workspace's
                      colorset-comparison infrastructure (7 top-level
                      assembly cells, shared transmission planes, white
                      outer edges, reflective z) — those 7 cells are the
                      MGXS domains directly.
2. MG coarse model  : mgxs.Library.create_mg_mode() -> 7 homogeneous
                      hexes, same boundaries.
3. DONJON consumer  : SPH-corrected handoff as L_MACROLIB with
                      GROUP/*/NSPH (mixtures CSD_C, INT_N1..INT_N6 =
                      DONJON MIX 1..7).
```

## Run

```sh
bash examples/irena30_sph_stage2_csd/run_stage2.sh
```

Same knobs as Stage 1 (`BATCHES/INACTIVE/PARTICLES`, `MG_*`,
`SPH_ITERATIONS`, `SPH_DAMPING`, `SPH_FLUX_FLOOR_REL`, `SPH_CLIP_*`,
`RUN_ROOT`), plus `SPH_FREEZE_GROUPS` which **defaults to 31 here**: the
established IRENA practice for the CSD colorset is to switch group-31 SPH
off outright (DRAGON-order 33-group numbering); the relative flux floor
remains the automated safety net for the other micro-flux bins.

Local inputs (not shipped):

- `IRENA_CE_COMPARE_DIR` (default
  `/Users/wen/dragon-5.1/Dragon/irena_core/colorset_rebuild_20260527/ce_compare`):
  provides `colorset_common.py`, `openmc_colorset.py` (CE materials and
  assembly universes, including the CSD B4C pin bundle), and
  `openmc_explicit7_probe.py` (the seven-cell colorset geometry).
- `IRENA30_MACROLIB` (default the IRENA workspace 33g macrolib): source
  for the zero-flux thermal-group fill of the DONJON handoff (labels
  `CSD` / `INT`).
- CE nuclear data via `OPENMC_CROSS_SECTIONS`.

Convergence analysis (shared tool, multi-mixture aware):

```sh
python examples/irena30_sph_stage1/analyze_convergence.py \
  --handoff-dir /private/tmp/openmc2donjon_irena_sph_stage2/handoff \
  --mixture CSD_C
```

The colorset case is selectable via `IRENA_SPH2_CASE` (default
`csd_int`; also `pnl_ext`, `dsdf_int`, `int_ext`, `ext_int`,
`refl_ext`), and the SPH equivalence target via `SPH_TARGET`:

- `flux` (package default): fixed point makes the corrected coarse-model
  flux equal the CE flux. In coupled colorsets this does NOT preserve
  reaction rates, and the corrected model's k drifts away from CE with
  the size of the center assembly's homogenization defect (measured:
  single fissile assembly ~0, pnl_ext -145 pcm, csd_int -440+ pcm).
- `rate`: classic Hebert/DRAGON rate-preserving SPH (fixed point
  mu * phi_corrected = phi_ref); k stays pinned at the uncorrected
  coarse value by construction. Rate mode relies on spatial coupling —
  isolated bins have no rate fixed point, which is another reason the
  flux floor / freeze-groups regularization exists.

## PNL line results (rate mode)

- Loop: k pinned across iterations (1.1119 +/- 0.0003 band, no trend)
  while flux-mode drifted monotonically; coupled bins converge in 3-4
  iterations, quasi-isolated bins (chi-driven top groups, weakly coupled
  reflector bins) drift geometrically and must be frozen — the
  recommended prescription is rate mode, freeze {1, 31}, 2-3 iterations.
- Core-level closure of the DONJON leg (the SNT hex COMPLETE
  REFL/ALBE boundary silently leaks, so the colorset-level DONJON check
  is not possible; see below): applying the PNL_C iteration-2 factors to
  the 30 ring-5 PNL mixtures of the accepted 91-hex ZREFL benchmark
  gives
  - OpenMC-MG core:  uncorrected 1.19223 +/- 25 pcm, corrected
    1.19247 +/- 26 pcm  (delta +24 +/- 36 pcm)
  - DONJON SN8 core: uncorrected 1.192125, corrected 1.192084
    (delta -4 pcm, deterministic)
  DONJON consumes the corrected library in agreement with the OpenMC
  coarse twin (corrected-model offset -32 +/- 26 pcm, same class as the
  benchmark's -9 +/- 21), and the rate-mode k-neutrality holds at core
  level by construction.

## Known DONJON limitation

DONJON/DRAGON SNT hexagonal `HBC COMPLETE REFL` (and `ALBE 1.0`) leaks:
with identical clean cross sections the 7-hex fully-"reflected" colorset
gives 0.969 in SNT vs 1.149 in OpenMC-MG, while the VOID pairing agrees
to SN-discretization level. REFL and ALBE 1.0 return bit-identical
results. Consequence: white-boundary colorset decks cannot be validated
in SNT; DONJON-side checks for this example are done at core level
(VOID boundary, validated by the accepted benchmark) instead.

## CSD line results (rate mode)

Rate mode on csd_int (freeze {1,31}, damping 0.5, 6 iterations) shows
the stronger property of rate-preserving SPH: it does not merely avoid
the flux-mode k drift, it RECOVERS the homogenization k defect — the
corrected coarse model climbs from -423 pcm (uncorrected) to -78 pcm
against the CE reference and is still converging (deltas per iteration
+146/+114/+95/+35/+38 pcm). The dominant corrections sit in the B4C
resonance region (s up to ~1.28 at the near-thermal end, i.e. the
homogenized absorber over-absorbs where pin self-shielding was lost),
physically as expected. Group 2 shows the same chi-driven quasi-isolated
drift as the PNL top groups: the CSD freeze list should be {1, 2, 31}.
CSD converges slower than PNL (larger defect); 6 iterations are not yet
converged and the recorded factors are a lower bound on the correction.

Core-level closure (iteration-6 factors on the 6 CSD rod positions of
the accepted 91-hex ARI benchmark):

| Core solve | uncorrected | CSD-SPH corrected | delta |
| --- | --- | --- | --- |
| OpenMC-MG twin | 1.19223 +/- 25 pcm | 1.19392 +/- 24 pcm | +142 pcm |
| DONJON SN8 | 1.192125 | 1.193048 | +77 pcm |

Both solvers move in the same direction with comparable magnitude (the
~65 pcm spread is ~2 sigma and grows with the factor size; the PNL
closure with its small factors agreed to -4 vs +24 +/- 36 pcm). The
headline physics: restoring B4C self-shielding through rate-SPH is worth
roughly +100 pcm on the all-rods-in core.

## Status

PNL (pnl_ext) line: complete under the prescription rate + freeze
{1,31} + 2-3 iterations. CSD (csd_int) line: rate-mode results and
core-level closure recorded above; recommended prescription rate +
freeze {1,2,31} + more iterations (>= 8) pending a converged rerun.
