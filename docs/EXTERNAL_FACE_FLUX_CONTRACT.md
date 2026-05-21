# External Face-Flux Contract

This contract covers the direct production handoff for ADF/DF generation when a
low-order, nodal, SPN, or diffusion driver has already computed homogeneous
face fluxes.

The production chain is:

```text
OpenMC MGXS HDF5
OpenMC heterogeneous surface flux
external homogeneous face flux
  -> check-face-flux
  -> make-adf-sidecar --mode flux-ratio
  -> augment-adf
  -> L_MULTICOMPO or L_MACROLIB
```

The ADF definition is:

```text
ADF[mix, face, group] =
    heterogeneous_face_flux[mix, face, group]
  / homogeneous_face_flux[mix, face, group]
```

## Canonical HDF5

The preferred external denominator file is:

```text
/homogeneous_face_flux  float64, shape=(M, F, G)
/mixture_names          string,  shape=(M,)
/face_names             string,  shape=(F,)
attrs:
  schema = "openmc2donjon.external-face-flux.v1"
  source = free-form provenance label
```

`M` is the number of MGXS mixtures, `F` is the number of faces, and `G` is the
number of energy groups. The canonical axis order is mixture, face, group.

The `/homogeneous_face_flux` dataset should also carry `mixture_names` and
`face_names` attributes. Root datasets are accepted too, but dataset attributes
make the file self-describing if the payload is copied elsewhere.

The same loader also accepts:

- `/homogeneous/face_flux`
- explicit `FILE::/dataset/path` references
- shape `(M, G, F)` when face metadata and group count make the axes
  unambiguous
- mesh layouts `(Y, X, G, F)` and `(Y, X, F, G)` when a `mixture_names` mesh is
  present

For production, write the canonical `(M, F, G)` form unless there is a strong
reason to preserve a solver-native mesh layout.

## Ordering Rules

Mixture names must match the MGXS HDF5 `/mixtures` keys. A direct face-flux
input can be consumed in a different mixture order if the dataset declares
`mixture_names`; openmc2donjon reorders mixtures into MGXS order while loading.

Face order is stricter. When `--faces FD_XMIN,FD_XMAX,...` is supplied,
declared `face_names` must already match that requested order. If a solver
writes faces in a different order, adapt the file before running
`check-face-flux`.

For Cartesian examples the usual face names are:

```text
FD_XMIN, FD_XMAX, FD_YMIN, FD_YMAX
```

For hex examples, use the case's actual six boundary names consistently across
heterogeneous flux, homogeneous flux, ADF sidecar, and DONJON mapping.

Energy groups follow the OpenMC MGXS order used throughout this project:
group index increasing in HDF5 corresponds to descending energy. Do not reverse
face-flux group axes independently of the MGXS HDF5.

## Value Rules

Homogeneous face flux should be finite and positive. `check-face-flux` also
requires the heterogeneous surface flux and the ADF ratio to be finite and
positive.

If a real production reconstruction has known invalid bins, for example zero
heterogeneous surface flux on an inactive boundary or a nonpositive denominator
from a mixed-dual reconstruction diagnostic, acknowledge that explicitly:

```sh
openmc2donjon check-face-flux mgxs_library.h5 \
  --surface-flux openmc_surface_flux.h5::surface_flux/mean \
  --homogeneous-face-flux homogeneous_face_flux.h5::homogeneous_face_flux \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --invalid-fill 1.0 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --summary-json face_flux_check_summary.json
```

Use the same fill and clip policy when creating the sidecar:

```sh
openmc2donjon make-adf-sidecar mgxs_library.h5 \
  -o adf_sidecar.h5 \
  --mode flux-ratio \
  --surface-flux openmc_surface_flux.h5::surface_flux/mean \
  --homogeneous-face-flux homogeneous_face_flux.h5::homogeneous_face_flux \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --invalid-fill 1.0 \
  --clip-min 0.5 \
  --clip-max 2.0 \
  --adf-kind production \
  --adf-real true
```

The JSON summaries record the invalid-bin count, filled-bin count, selected
datasets, faces, and value ranges. Keep those summaries with the production
handoff bundle.

## Adapter Pattern

External solvers often write case-specific paths or native axis orders. Keep
that code outside the converter core and adapt into the canonical file above.

The adapter should:

1. Read MGXS mixture names and energy group count.
2. Read raw homogeneous face flux plus raw `mixture_names` and `face_names`.
3. Transpose raw values into `(M, F, G)`.
4. Reorder mixture and face axes into MGXS and canonical face order.
5. Reject non-finite or nonpositive values unless the production policy says
   otherwise.
6. Write `/homogeneous_face_flux`, `/mixture_names`, and `/face_names` with
   provenance attributes.
7. Run `check-face-flux` before building the ADF sidecar.

A runnable template is provided at:

```text
examples/external_face_flux_adapter/
```

The template intentionally starts from a raw solver file whose path, mixture
order, face order, and layout differ from the canonical contract.

## C5G7 DONJON Adapter

The C5G7 production validation uses the same pattern with a real DONJON source:

```text
DONJON L_FLUX/L_TRACK ASCII dumps
  -> scripts/extract_c5g7_donjon_face_flux.py
  -> c5g7_homogeneous_face_flux_donjon.h5
  -> check-face-flux
  -> make-adf-sidecar
```

`scripts/run_c5g7_donjon_face_flux_smoke.sh` regenerates the accepted C5G7
homogeneous denominator from local DONJON dumps and checks exact parity with the
accepted artifact. That script is a concrete adapter example for the current
C5G7 deck, not a general DONJON dump parser.
