# Architecture

`openmc2donjon` is intentionally small. It translates a compact OpenMC MGXS HDF5
handoff file into DRAGON/DONJON LCM ASCII without linking against DRAGON/PyGan.

## Data Flow

```text
OpenMC MGXS domains
  -> exporter or user-written HDF5 input contract
  -> openmc2donjon CLI
  -> L_MULTICOMPO or L_MACROLIB
  -> DONJON geometry mixture map
```

The domain mapping is spatial:

```text
one OpenMC MGXS domain -> one cross-section set -> one DONJON mixture
```

## Package Modules

| Module | Responsibility |
| --- | --- |
| `openmc2donjon.lcm_ascii` | Ordered LCM ASCII reader/writer for block-level serialization. |
| `openmc2donjon.scatter` | Dense Legendre scattering arrays to DRAGON sparse `NJJS/IJJS/SCAT` triplets, and reverse conversion for tests. |
| `openmc2donjon.export_openmc_mgxs` | Duck-typed OpenMC `mgxs.Library` exporter for whole domains and explicit mesh/cell subdomains. |
| `openmc2donjon.openmc_statepoint` | Recipe runner that builds a user OpenMC MGXS library, loads a statepoint, and exports the HDF5 handoff. |
| `openmc2donjon.openmc_surface_flux` | OpenMC mesh-surface angular-current tally exporter for flux-ratio ADF sidecars. |
| `openmc2donjon.adf_augment` | ADF/DF sidecar injector for adding computed discontinuity factors to an MGXS HDF5 handoff. |
| `openmc2donjon.multicompo` | `L_MULTICOMPO` container writer for one-state spatial-domain MGXS data, with experimental `BURN`-axis histories. |
| `openmc2donjon.macrolib` | root `L_MACROLIB` writer for direct DONJON ingestion. |
| `openmc2donjon.mgxs_input_contract` | Packaged HDF5 input-contract preflight used by `openmc2donjon check`. |
| `openmc2donjon.cli` | HDF5 reader, preflight options, and command-line output selection. |
| `openmc2donjon.export_cli` | Export CLI for recipe/statepoint workflows and pickled MGXS library fixtures. |
| `openmc2donjon.from_openmc_cli` | One-step recipe/statepoint export plus DONJON ASCII conversion. |

## Example And Validation Layer

| Path | Role |
| --- | --- |
| `docs/HDF5_INPUT_CONTRACT.md` | HDF5 schema expected by the converter. |
| `docs/OPENMC_EXPORT_WORKFLOW.md` | User-facing OpenMC recipe/statepoint export workflow. |
| `docs/FROM_OPENMC_SUMMARY_SCHEMA.md` | Machine-readable summary schema for one-step OpenMC conversions. |
| `examples/openmc_recipe_template/` | Editable OpenMC recipe skeleton for user cases. |
| `examples/recipe_export_smoke/minimal_recipe.py` | tiny no-OpenMC-data recipe used to test the export workflow mechanics. |
| `scripts/run_recipe_export_smoke.sh` | portable recipe/statepoint export smoke, HDF5 preflight, and converter readback. |
| `scripts/run_c5g7_demo.sh` | portable C5G7 converter demo and optional DONJON smoke entry point. |
| `scripts/c5g7_export_recipe.py` | C5G7 recipe for the production OpenMC statepoint export CLI. |
| `scripts/export_c5g7_statepoint.py` | legacy C5G7-specific statepoint export helper retained for comparison. |
| `examples/donjon_openmc2donjon/` | DONJON-side C5G7 validation snapshot. |
| `examples/donjon_openmc2donjon/run_handoff_case.py` | manifest-driven conversion and DONJON deck replacement helper. |
| `examples/donjon_openmc2donjon/c5g7_validation/` | accepted C5G7 validation decks and summaries. |

## Output Modes

`L_MULTICOMPO` is the default path for spatially mapped homogenized data. It is
the main route for assembly-wise C5G7.

`L_MACROLIB` is available for direct DONJON consumption when a full MULTICOMPO
container is unnecessary or too heavy for a given one-state solve.

## State And Parameter Scope

The current production scope is one state point by default:

```text
NPAR = 0
NLOC = 0
single calculation per spatial domain
```

Single-point helper metadata such as `BURN` can be written for compatibility
checks. The converter can also serialize an experimental one-parameter burnup
history:

```text
NPAR = 1
PARKEY = BURN
one CALCULATIONS item per burnup state
```

That path is covered by unit tests and by a tiny DONJON `NCR:` consumer smoke,
but it is not part of the accepted physics validation.

The history path is intentionally one-dimensional for now. Inputs with
additional `/state_points/*` branch axes are rejected so boron, temperature,
control, or other branch coordinates cannot be silently dropped.

## Important Conventions

- OpenMC group-index order is preserved for cross-section arrays.
- `ENERGY` is written as reversed HDF5 energy bounds.
- Scatter triplets use contiguous incoming-group spans in descending incoming
  group order.
- Legendre scattering values are bare moments.
- `STRD` comes from `transport_total` when available, otherwise from P1-derived
  transport correction, otherwise `NTOT0`.
- ADF payloads are optional per-mixture datasets under `/mixtures/<name>/adf/`.
