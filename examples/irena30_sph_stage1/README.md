# IRENA SPH Stage 1 — Fissile Assembly, CE Fine vs MG Coarse

First stage of the three-model OpenMC-side SPH route for IRENA-30:

```text
1. CE fine model    : TDT-validated 217-pin IRENA fissile assembly
                      (rnr_assembly.py; white radial / reflective axial),
                      wrapped in ONE container cell = one MGXS domain.
2. MG coarse model  : mgxs.Library.create_mg_mode() fills that container
                      with the homogenized 33g macro -> single homogeneous
                      hex, same boundaries. This is the SPH iteration's
                      low-order operator.
3. DONJON consumer  : the SPH-corrected handoff is written as L_MACROLIB
                      with GROUP/*/NSPH (the operator equivalence of the
                      MG coarse model and DONJON was established by the
                      accepted irena30_zrefl_hex benchmark).
```

Stage 1's question is loop mechanics, not physics acceptance: how do the
33 SPH(group) factors of a single region converge when the low-order
operator is itself a Monte Carlo solve (statistics x damping x iteration
count)?

## Run

```sh
bash examples/irena30_sph_stage1/run_stage1.sh
```

Knobs: `BATCHES/INACTIVE/PARTICLES` (CE), `MG_*` (coarse solve per
iteration), `SPH_ITERATIONS`, `SPH_DAMPING`, `RUN_ROOT`. Local inputs:
`IRENA30_DIR` (assembly model), `IRENA30_MACROLIB` (thermal-group fill),
`OPENMC_CROSS_SECTIONS` (defaults to the local ENDF/B-VIII.1 library).

Each iteration leaves `openmc_sph_iterNN.csv` / `openmc_sph_summary_iterNN.json`
in the handoff directory for convergence analysis.

## Fast-spectrum workflow notes

- The thermal groups of the ECCO-33 mesh carry exactly zero Monte Carlo
  flux. The workflow uses the package's explicit policies for that:
  `export-volume-flux --allow-zero-flux` and
  `make-openmc-sph-sidecar --zero-flux-policy identity` (matched zero
  bins keep their previous SPH value; a one-sided zero is a real CE/MG
  inconsistency and still fails).
- The DONJON handoff's zero-flux rows are substituted from the IRENA MG
  macrolib (via `openmc2donjon fill-zero-flux`; the homogenized fissile
  assembly is the macrolib's `INT` mixture by construction).
- `prepare_mg_case.py` blackens zero-XS groups of the OpenMC-native macro
  library (unit total/absorption): no population ever reaches those
  groups, but a collisionless group would otherwise let a stray particle
  stream forever.
- CE sanity anchor: the container-wrapped assembly reproduces the
  TDT-validated k (1.362) — first smoke gave 1.361 +/- 0.015.

## Results

This stage exposed and fixed a structural sign bug in the package's SPH
iteration (the update ratio was inverted relative to the divide-apply
convention, making the loop divergent with amplification (1+d) and even
one-shot corrections carry the wrong sign; see the sph_iteration.py
direction-flip change). With the fix, the loop shows textbook geometric
convergence at production statistics (CE 50k x 140, MG 200k x 120,
damping 0.5, floor 1e-3, clip [0.5, 2]):

```text
iter   max|update-1|
 1        0.105
 2        0.058
 3        0.022
 4        0.008     <- contraction ~0.5/iter = theoretical (1-d)
 5-8      0.004-0.016  <- Monte Carlo noise floor
```

Fixed point: only the top energy group needs a real correction
(SPH ~= 1.10 = phi_CE/phi_MG, matching the diagnosed uncorrected-flux
ratio exactly); all other active groups sit within +/-0.2% of unity —
per-assembly homogenization + ECCO-33 condensation of the fissile Na
assembly is nearly self-consistent. Recommended loop configuration from
this study: damping 0.5, 4 iterations, relative flux floor + explicit
freeze list for the near-thermal groups.

Stage 2 adds the CSD absorber colorset (specs from the existing DRAGON
`irena_core` colorset decks), where SPH has a substantial homogenization
defect to correct and the user's established "group 31 off" practice
applies via `--freeze-groups`.
