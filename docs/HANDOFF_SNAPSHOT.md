# Handoff Snapshot

Last updated: 2026-07-09

## Goal

`openmc2donjon` is a Python package that converts OpenMC homogenized MGXS HDF5
handoff files into DRAGON/DONJON LCM ASCII:

- `L_MULTICOMPO` for spatially mapped homogenized calculations;
- root `L_MACROLIB` for direct one-state macrolib consumption.

The production mapping is spatial:

```text
one OpenMC MGXS domain or subdomain -> one DONJON mixture
```

Materials are not collapsed by name. Two positions with the same material can
remain separate mixtures when their spectra or leakage environments differ.

## Current Capabilities

- Ordered LCM ASCII reader/writer for the converter formats used here.
- OpenMC MGXS HDF5 exporter with recipe/statepoint entry points.
- One-command OpenMC recipe/statepoint -> HDF5 -> DONJON ASCII workflow.
- Strict dry-run checks for production recipe readiness.
- Input-contract preflight checks for required XS, volumes, transport data,
  ADF/DF presence, and scatter row balance.
- P0/P1+ Legendre scatter carry-through and DRAGON sparse scatter layout.
- `transport_total` / `STRD` carry-through for transport-corrected diffusion
  data.
- ADF/DF sidecar injection, OpenMC surface-flux export, low-order driver
  canonicalization, face-flux contract checks, and flux-ratio ADF workflow
  plumbing.
- SPH sidecar injection and DONJON `NSPH` carry-through for routes where the
  downstream solver uses SPH equivalence factors instead of ADF/DF, including
  extraction from DONJON/DRAGON `L_MACROLIB` ASCII dumps.
- OpenMC-side CE/MG SPH iteration with a fixed, convergent update
  (direction fix of 2026-07), selectable equivalence target
  (`--sph-target {flux,rate}`; rate = Hebert/DRAGON rate-preserving,
  pins k in coupled geometry), and fast-spectrum regularization
  (`--allow-zero-flux`, `--zero-flux-policy`, `--flux-floor-rel`,
  `--freeze-groups`). Validated on the IRENA fissile-assembly and
  CSD/PNL colorset stages (`examples/irena30_sph_stage1`,
  `examples/irena30_sph_stage2_csd`); the PNL prescription
  (rate, freeze {1,31}, 2-3 iterations) is closed to core level.
- External homogeneous face-flux adapter pattern for low-order, nodal, SPN, or
  diffusion solvers that already compute the ADF denominator directly.
- Managed run directories with `mgxs_library.h5`, DONJON ASCII output,
  summaries, recipe copies, and bundle manifests.

## Accepted Validation

Two accepted physics lines exist.

**Hex line — IRENA-30 ZREFL 91-hex benchmark** (`examples/irena30_zrefl_hex`,
local IRENA workspace + DONJON required): OpenMC-MG per-position tallies ->
91-mixture `L_MULTICOMPO` -> DONJON `NCR:` + `SNT:` SN8. Both gates pass in
one invocation against the paired OpenMC reference: k-eff delta -9 pcm
(21 pcm sigma; different-seed run +29 pcm) and fission-source shape
1.27 % worst / 0.47 % RMS over 52 fuel positions. Locked summaries are
checked by the baseline manifest validation.

**Cartesian line — C5G7 assembly-wise homogenization:**

```text
OpenMC MGXS + production ADF HDF5
  -> openmc2donjon L_MULTICOMPO
  -> DONJON assembly-wise diffusion/SPN checks
```

Accepted source:

```text
examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5
```

Locked reference results:

| Case | k-effective |
| --- | ---: |
| OpenMC reference | `1.18798` |
| DONJON diffusion | `1.1896194220` |
| DONJON SPN3 | `1.1912802458` |
| DONJON SPN3 with first-order scattering retained | `1.1912822723` |
| DONJON 2-group ADF smoke | `1.18533289` |
| DONJON 2-group NODF smoke | `1.20179343` |

## Default Release Gate

Run:

```sh
bash scripts/release_check.sh
```

The default gate covers:

- package tests;
- installed CLI help/version smoke;
- recipe/export smoke;
- direct external face-flux adapter smoke;
- real OpenMC Cartesian production minicase;
- real OpenMC hex minicase;
- C5G7 converter readback to `L_MULTICOMPO` and `L_MACROLIB`;
- accepted baseline manifest validation;
- C5G7 ADF augment smoke;
- C5G7 SPH augment and `L_MACROLIB/NSPH` readback smoke;
- C5G7 DONJON face-flux regeneration from local `L_FLUX`/`L_TRACK` dumps when
  those files are present;
- C5G7 production ADF source reconstruction from OpenMC surface flux over
  DONJON homogeneous face flux.

Full local DONJON-side decks can be added with:

```sh
bash scripts/release_check.sh --run-donjon
```

Fresh clone install checks were also run on 2026-05-21:

- GitHub clone to `/private/tmp/openmc2donjon_fresh_install_check`;
- editable install in a fresh venv;
- console scripts without `PYTHONPATH`;
- C5G7 `check` and conversion;
- recipe managed run;
- `scripts/release_check.sh --skip-tests`.

All passed.

## Known Boundaries

- One calculation state per mixture is the production path.
- One-dimensional `BURN` serialization exists and has a DONJON consumer smoke,
  but it is not an accepted physics validation line.
- General multi-axis branch libraries are rejected rather than silently ignored.
- Hex is implemented as converter/modeling capability and is covered by real
  OpenMC workflow smoke, but no accepted hex benchmark is included yet.
- DRAGON/DONJON equivalence effects such as `SPH` or `LEAK B2` are not
  inferred from plain OpenMC MGXS handoffs. Explicit SPH vectors can now be
  carried through as `NSPH`; physical SPH generation still belongs to the
  matching deterministic/equivalence workflow.
- The accepted C5G7 statepoint/exporter parity path is locked to the OpenMC
  `consistent nu-scatter matrix` tally definition that produced the baseline.
  New user recipes should still use ordinary `scatter matrix` unless they
  explicitly want a non-default scattering definition.

## Next Physical Work

1. Replace the deterministic external low-order handoff example with the real
   low-order driver handoff from the intended DONJON calculation route.
2. Add a larger OpenMC-sourced user case with assembly-wise domains and
   production ADF/DF, then compare DONJON k-effective against the OpenMC
   reference at that homogenization level.
3. Promote a hex validation line only after complete model inputs, correction
   handoffs, and a defensible reference solution are available.
