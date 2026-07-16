# IRENA Fast-Spectrum Example Workflow

This document defines the strict physics contract selected by the IRENA-30
full-core example manifest. It is not a universal Converter workflow.
Historical scripts that use local colorsets, post-transport record reuse,
zero-flux filling, identity substitutions, flux floors, frozen groups, clipping,
eigenvalue fitting, or a global multiplier remain useful as research records,
but they do not produce an accepted IRENA full-core result.

The current qualification unit is one position-resolved full core. The fine
transport either keeps 91 independent domains or pools tallies on 21 exact
global D3 symmetry orbits while particles are being transported:

```text
fine OpenMC CE 91-position full core
  -> 91 independent domains or 21 exact D3 transport-time tally pools
  -> Converter reference MACROLIB
  -> native DRAGON SPH on the matching 91-position coarse geometry
  -> corrected MACROLIB
  -> DONJON k-effective, leakage, and 91-position power verification
```

Historical IRENA local studies declare colorsets such as `int_ext`, `ext_int`,
`csd_int`, `dsdf_int`, and `pnl_ext`. These labels and counts are template
facts, not Converter defaults. They are not the current full-core production
mapping because identical material labels can occupy different global leakage
environments.

## 1. Strict full-core SPH contract

An accepted IRENA full-core handoff must satisfy all of the following:

- The fine reference contains all 91 physical OpenMC CE positions with exact
  integrated flux, reaction rates, energy coverage, uncertainty, and boundary
  leakage evidence.
- Converter preserves the declared 91-position or 21-orbit transport-time tally
  mapping and writes the uncorrected reference MACROLIB before SPH.
- DRAGON native `SPH:` converges on the matching project-declared full-core
  geometry using SN or SPN as declared by that model.
- Zero or unusable bins are rejected. Identity substitution, floors, frozen
  groups, clipping, and ADF are absent.
- Converter rate balance and final DONJON eigenvalue both pass the predeclared
  OpenMC-uncertainty gate.
- Full-core k-effective, leakage, and power are validation observables only; no
  empirical scalar or fitted global coefficient participates in factor
  generation.

If statistics are insufficient to evaluate a bin, the remedy is better tally
design, a physically justified energy structure, or more histories. A numerical
exception is not a physical SPH result.

The local workspace currently has no accepted IRENA full-core physical closure.
Earlier PNL/EXT and INT/EXT summaries had converged SPH fixed points but
unconverged final transport solves, so they are retained only as negative
evidence.

## 2. Converter is the controlled boundary

Converter first writes the uncorrected `L_MACROLIB` reference from the declared
component HDF5. DRAGON then solves native SPH and writes the corrected NSPH
MACROLIB consumed by DONJON. The Converter receipt identifies the exact
reference input and object; `validate-native-sph` links that reference to the
SPH and verification artifacts.

The older OpenMC MG-side `apply-sph` route remains an optional diagnostic or
alternate project method. It is not the primary IRENA production route.

## 3. Full-core DONJON model

The IRENA full-core solve is a coarse transport model over 91 physical core
positions (52 are fuel), not a 91-mixture fit and not 91 fuel assemblies. The
fine reference keeps all 91 heterogeneous assemblies. It may retain 91
independent homogenized domains or pool tallies during OpenMC transport on the
21 exact global D3 symmetry orbits. The older five-material and 13-local-
signature maps are diagnostic only because they overmerge distinct global
environments. The downstream solver may be SN or SPN; a special `SN8` choice
is not part of the general physical contract.

Full-core k-effective, leakage, and power shape are validation observables only.
They may reveal that the coarse model is inadequate, but they may never be
used to tune a global SPH coefficient.

## 4. Historical evidence

- `examples/irena30_sph_stage2_csd` records the earlier seven-assembly
  colorset experiments. Its identity/floor/freeze/clip prescriptions are
  archived and production-rejected; its reproduction runners are guarded and
  their summaries are permanently marked withdrawn diagnostics.
- `examples/irena30_sph_stage3_fullcore` records the rejected full-core SPH
  research line. Its sparse/fill/floor/frozen-group artifacts are not the
  current full-core input.
- `examples/irena30_zrefl_hex` remains useful converter/DONJON benchmark
  evidence. Its older 91-position representation does not prove an accepted
  five-component physical SPH model.
- C5G7 ADF validation remains a separate capability. ADF is not part of the
  IRENA product route described here.
