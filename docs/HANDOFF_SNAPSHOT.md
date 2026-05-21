# Handoff Snapshot

Last updated: 2026-05-21

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
- Managed run directories with `mgxs_library.h5`, DONJON ASCII output,
  summaries, recipe copies, and bundle manifests.

## Accepted Validation

The accepted physics line is C5G7 assembly-wise homogenization:

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
- real OpenMC Cartesian production minicase;
- real OpenMC hex minicase;
- C5G7 converter readback to `L_MULTICOMPO` and `L_MACROLIB`;
- accepted baseline manifest validation;
- C5G7 ADF augment smoke;
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
  inferred from plain OpenMC MGXS handoffs. They need explicit matching
  handoff data.
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
