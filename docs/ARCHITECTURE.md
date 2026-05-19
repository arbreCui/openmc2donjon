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
| `openmc2donjon.multicompo` | `L_MULTICOMPO` container writer for one-state spatial-domain MGXS data, with experimental `BURN`-axis histories. |
| `openmc2donjon.macrolib` | root `L_MACROLIB` writer for direct DONJON ingestion. |
| `openmc2donjon.cli` | HDF5 reader, preflight options, and command-line output selection. |
| `openmc2donjon.export_cli` | Helper CLI for pickled OpenMC MGXS library exports. |

## Example And Validation Layer

| Path | Role |
| --- | --- |
| `docs/HDF5_INPUT_CONTRACT.md` | HDF5 schema expected by the converter. |
| `scripts/run_c5g7_demo.sh` | portable C5G7 converter demo and optional DONJON smoke entry point. |
| `scripts/export_c5g7_statepoint.py` | rebuilds the C5G7 OpenMC MGXS library from a saved statepoint and exports the HDF5 contract. |
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

## Important Conventions

- OpenMC group-index order is preserved for cross-section arrays.
- `ENERGY` is written as reversed HDF5 energy bounds.
- Scatter triplets use contiguous incoming-group spans in descending incoming
  group order.
- Legendre scattering values are bare moments.
- `STRD` comes from `transport_total` when available, otherwise from P1-derived
  transport correction, otherwise `NTOT0`.
- ADF payloads are optional per-mixture datasets under `/mixtures/<name>/adf/`.
