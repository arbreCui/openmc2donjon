# Handoff Snapshot

Last updated: 2026-07-16

> This snapshot covers the general converter package as well as historical
> validation lines. For the current IRENA product contract and its stricter
> acceptance meaning, see `docs/PRODUCT_MODEL.md` and
> `docs/FAST_SPECTRUM_WORKFLOW.md`.

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
- OpenMC-side CE/MG SPH iteration with a rate-preserving target. The package
  still exposes identity/floor/freeze/clip controls for reproduction of older
  research, but the IRENA production gate rejects every such exemption.
- External homogeneous face-flux adapter pattern for low-order, nodal, SPN, or
  diffusion solvers that already compute the ADF denominator directly.
- Managed run directories with `mgxs_library.h5`, DONJON ASCII output,
  summaries, recipe copies, and bundle manifests.

## Validation Evidence

The following lines validate converter and solver capabilities. They must not
be interpreted as an accepted five-component IRENA physical-SPH result.

**Historical hex line — IRENA-30 ZREFL 91-hex benchmark** (`examples/irena30_zrefl_hex`,
local IRENA workspace + DONJON required): OpenMC-MG per-position tallies ->
91-mixture `L_MULTICOMPO` -> DONJON `NCR:` + `SNT:` SN8. Both gates pass in
one invocation against the paired OpenMC reference: k-eff delta -9 pcm
(21 pcm sigma; different-seed run +29 pcm) and fission-source shape
1.27 % worst / 0.47 % RMS over 52 fuel positions. Locked summaries are
checked by the baseline manifest validation. This proves that conversion and
the particular 91-position model are numerically reproducible; it does not
prove the product's five-colorset SPH model. The 91 positions are not all fuel.

**Current IRENA CE/SPH candidate:** all 91 heterogeneous fine assemblies with
real radial vacuum, tallied as either 91 independent domains or 21 exact global
D3 symmetry orbits pooled during OpenMC transport -> Converter reference
MACROLIB -> native DRAGON full-core SPH -> DONJON. This route is implemented
structurally but does not yet claim an accepted physics result. Acceptance
requires one hash-linked run to pass k-effective, leakage, 91-position power,
Monte Carlo quality, SPH fixed-point, every one-speed solve, and final
transport convergence. It uses no ADF or empirical/global factor.

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
  OpenMC workflow smoke. The IRENA ZREFL OpenMC-MG/DONJON transport baseline is
  an accepted downstream mechanics benchmark, not CE-fine/SPH/full-core
  physics acceptance.
- DRAGON/DONJON equivalence effects such as `SPH` or `LEAK B2` are not
  inferred from plain OpenMC MGXS handoffs. Explicit SPH vectors can now be
  carried through as `NSPH`; physical SPH generation still belongs to the
  matching deterministic/equivalence workflow.
- The accepted C5G7 statepoint/exporter parity path is locked to the OpenMC
  `consistent nu-scatter matrix` tally definition that produced the baseline.
  New user recipes should still use ordinary `scatter matrix` unless they
  explicitly want a non-default scattering definition.

## Next Physical Work

1. Run the heterogeneous 91-position OpenMC CE fine model with either 91
   independent domains or 21 exact global D3 orbits pooled during transport.
2. Pass that declared full-core HDF5 through Converter and preserve the
   hash-linked reference MACROLIB receipt.
3. Run native DRAGON SPH on the matching 91-position coarse geometry with the
   project-declared SN or SPN method, then verify the corrected object in DONJON.
4. Promote the line only after one hash-linked run passes native/final solver
   convergence, finite-domain k-effective and leakage, 91-position power,
   statistical-quality, and provenance gates without fitting any observable.
