# HDF5 Input Contract

`openmc2donjon` consumes a compact HDF5 export of OpenMC MGXS data. The file is
not required to be an OpenMC statepoint; it is a deliberately small handoff
format with one group structure and one or more spatial MGXS domains.

The package includes a duck-typed OpenMC exporter for this contract:

```python
from openmc2donjon import DomainExportSpec, export_openmc_mgxs_library

export_openmc_mgxs_library(library, "mgxs_library.h5")
```

It expects an OpenMC `mgxs.Library`-like object with `energy_groups`, `domains`,
and `get_mgxs(domain, mgxs_type)`. It writes one HDF5 mixture group per OpenMC
MGXS domain.

For mesh or cell subdomains, use explicit export specs:

```python
export_openmc_mgxs_library(
    library,
    "mgxs_library.h5",
    domain_specs=[
        DomainExportSpec(
            domain=mesh,
            name="ASM_Y01_X01",
            xs_kwargs={"subdomains": [(1, 1, 1)]},
            volume=assembly_volume,
        ),
    ],
)
```

## Domain Rule

The mapping is spatial:

```text
one OpenMC MGXS domain
  -> one homogenized cross-section set
  -> one DONJON mixture
```

Do not collapse domains just because they share a material label. If two
assemblies or components occupy different positions, keep them as distinct
domains so OpenMC spectrum, leakage, and neighbor effects are retained.

For 3D cases, choose the spatial partition explicitly. A common choice is:

```text
assembly position + axial layer -> one MGXS domain -> one DONJON mixture
```

## Supported Schema Variants

| HDF5 layout | Status | Required state metadata | Converter behavior |
| --- | --- | --- | --- |
| One-state `/mixtures/<domain_name>/...` | Production path | None | Writes one calculation per mixture. |
| One-dimensional burnup history | Experimental | Exactly one `BURN` axis from `/state_points/BURN`, `/burnup_values`, `/burnup`, or matching root attrs | Writes `NPAR=1`, `PARKEY=BURN`, one calculation per burnup value, and per-mixture `TREE`. |
| Multi-axis branch library | Not supported | More than one branch axis, such as `BORON`, `TEMP`, `COOLANT`, or control state | Preflight and converter fail explicitly. |

The one-state schema is the accepted C5G7 validation path. The `BURN` schema is
intended for a single depletion/history axis only; it is not a general
temperature/boron/control branch-library format.

## Required Root Items

Required attributes:

| Path | Type | Meaning |
| --- | --- | --- |
| `/attrs/energy_groups` | integer | number of energy groups `G` |
| `/attrs/legendre_order` | integer | highest scattering Legendre order `L` |

Required datasets:

| Path | Shape | Units/Order |
| --- | --- | --- |
| `/energy_bounds` | `(G + 1,)` | eV, ascending low-to-high |

The converter writes DONJON `ENERGY` as `energy_bounds[::-1]`. Cross-section
arrays are kept in OpenMC group-index order, which is high energy to low energy
for the group structures used here.

## Required Mixture Items

For each spatial domain:

```text
/mixtures/<domain_name>/
    total
    absorption
    scatter_matrix
```

Required datasets:

| Dataset | Shape | DONJON field |
| --- | --- | --- |
| `total` | `(G,)` | `NTOT0` |
| `absorption` | `(G,)` | used for balance checks and macrolib fields |
| `scatter_matrix` | `(L + 1, G_in, G_out)` or `(G_in, G_out, L + 1)` | `SIGSxx` and `SCATxx` |

Fission datasets are required only for domains with a physical fission source:

| Dataset | Shape | DONJON field |
| --- | --- | --- |
| `nu_fission` | `(G,)` | `NUSIGF` |
| `chi` | `(G,)` | `CHI` |

The writer suppresses fission fields when `nu_fission` or `chi` is effectively
zero. This avoids carrying Monte Carlo noise as a real fission spectrum in
non-fuel domains.

Recommended mixture attributes:

| Attribute | Type | Meaning |
| --- | --- | --- |
| `fissionable` | bool | source-domain hint |
| `scatter_format` | string | normally `legendre` |
| `scatter_axes` | string | normally `moment,from,to` |
| `volume` | float | spatial-domain volume |

## Optional Mixture Items

| Dataset | Shape | DONJON field |
| --- | --- | --- |
| `transport_total` | `(G,)` | `STRD` |
| `inverse_velocity`, `inverse-velocity`, `OVERV`, or `overv` | `(G,)` | `OVERV` |
| `volume` | scalar | mixture volume |
| `flux` or `flux_integral` | `(G,)` | `FLUX-INTG` when writing root `L_MACROLIB` |
| `h_factor`, `H-FACTOR`, `H_FACTOR`, `kappa_fission`, `kappa_fission_xs`, or `kappa_fission_cross_section` | `(G,)` | `H-FACTOR` |

If `transport_total` is absent and P1 scattering is present, the converter
derives:

```text
STRD = NTOT0 - sum_out(SCAT01)
```

If neither is available, `STRD` falls back to `NTOT0`.

## Experimental Multi-State Burnup Axis

The production validation line is still one state point by default. The
converter also has experimental plumbing for one global `BURN` axis, using this
layout:

```text
/state_points/BURN                       shape=(S,)
/mixtures/<domain_name>/states/00000001/
    total
    absorption
    nu_fission
    chi
    scatter_matrix
/mixtures/<domain_name>/states/00000002/
    ...
```

Root datasets named `/burnup_values` or `/burnup`, or matching root
attributes, are also accepted as the burnup axis. All mixtures must contain the
same number of states, and the burnup axis length must match that state count.
Only one burnup-axis definition may be present.

This is a one-parameter history path, not a general branch-library schema.
Additional `/state_points/*` axes such as `BORON`, `TEMP`, `COOLANT`, or control
state are rejected by both preflight and converter code. Add those only after the
MULTICOMPO `PARKEY/PARTYP/PARFMT/TREE` mapping has been extended and validated.

Mixture-level attributes such as `fissionable`, `scatter_axes`, and `volume`
are inherited by each state group unless overridden. State datasets use the
same required and optional fields as the one-state mixture schema.

When this layout is present, `openmc2donjon` writes `NPAR=1`, `PARKEY=BURN`,
`NVALUE=S`, one `CALCULATIONS` item per state, and a per-mixture `TREE` linking
calculation indexes to the burnup values. This path is unit-tested for
serialization, but it is not part of the accepted C5G7 physics validation yet.

The preflight validator checks this layout before conversion: all mixtures must
use the same state count, the `BURN` axis must exist for multi-state inputs, and
its length must match the state count. It also rejects unsupported branch axes
instead of silently ignoring them.

## Optional ADF Payload

Assembly discontinuity factors are stored under each mixture:

```text
/mixtures/<domain_name>/adf/<face_name>  shape=(G,)
```

Typical Cartesian face names are:

```text
FD_XMIN
FD_XMAX
FD_YMIN
FD_YMAX
```

When ADF datasets are present, the MULTICOMPO writer emits the embedded
`MACROLIB/ADF` payload and sets the corresponding DONJON state-vector flags.

## Scattering Convention

The dense scatter matrix is interpreted as:

```text
scatter_matrix[moment, from_group, to_group]
```

If the HDF5 stores OpenMC-style `(G_in, G_out, L + 1)`, the reader normalizes it
internally before writing.

The values are bare Legendre moments. `openmc2donjon` writes DRAGON/DONJON
`NJJS/IJJS/SCAT` triplets with contiguous incoming-group spans and descending
incoming-group order.

## Minimal Tree

```text
/attrs:
    energy_groups = G
    legendre_order = L
/energy_bounds
/mixtures/ASM_Y01_X01/
    total
    absorption
    nu_fission
    chi
    scatter_matrix
    transport_total          optional
    volume                   optional
    /adf/FD_XMIN             optional
    /adf/FD_XMAX             optional
    /adf/FD_YMIN             optional
    /adf/FD_YMAX             optional
/mixtures/ASM_Y01_X02/
    ...
```

Experimental burnup-axis variant:

```text
/attrs:
    energy_groups = G
    legendre_order = L
/energy_bounds
/state_points/BURN
/mixtures/ASM_Y01_X01/
    attrs: fissionable, scatter_axes, volume
    /states/00000001/
        total
        absorption
        nu_fission
        chi
        scatter_matrix
    /states/00000002/
        ...
```

## Preflight Checks

The packaged CLI can enforce the contract before writing:

```sh
openmc2donjon check mgxs_library.h5
```

The same preflight can be attached to conversion:

```sh
openmc2donjon mgxs_library.h5 -o out.mcompo.txt --check
```

The legacy helper wrapper still combines preflight and conversion for the
accepted C5G7 handoff checks:

```sh
PYTHONPATH=src python examples/donjon_openmc2donjon/convert_mgxs_with_preflight.py \
  examples/donjon_openmc2donjon/c5g7_assembly_p1_adf_production.h5 \
  --require-transport-dataset \
  --require-volume \
  --require-adf \
  --expected-adf-faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  -o /private/tmp/c5g7pa.mco
```

For experimental multi-state files, the same preflight path reports the detected
state count and `BURN` axis:

```sh
openmc2donjon check /path/to/multistate_mgxs.h5
```
