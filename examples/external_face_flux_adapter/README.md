# External Face-Flux Adapter Example

This example shows the direct production handoff when an external low-order,
nodal, or SPN driver has already computed the homogeneous face flux that should
be used as the ADF/DF denominator.

It is not a reactor benchmark. It is a deterministic adapter example that
exercises the user-facing data contract:

- MGXS HDF5 input with two spatial mixtures.
- External solver HDF5 using a case-specific dataset path.
- Raw mixture order and face order that differ from the MGXS/ADF order.
- Raw dataset layout `(mixture, group, face)`.
- Adapter output in canonical `/homogeneous_face_flux` layout
  `(mixture, face, group)`.
- Heterogeneous/homogeneous face-flux contract check.
- Flux-ratio ADF sidecar generation, ADF injection, and DONJON ASCII readback.

Run it from the repository root:

```sh
bash examples/external_face_flux_adapter/run_smoke.sh
```

By default it writes generated artifacts under:

```text
/private/tmp/openmc2donjon_external_face_flux_adapter/
```

The generated raw driver deliberately uses a nonstandard path:

```text
/solver/face_flux
```

The adapter template reads the raw `mixture_names` and `face_names`, reorders
both axes into MGXS/canonical face order, and writes:

```text
/homogeneous_face_flux  shape=(M, F, G)
/mixture_names
/face_names
```

The key production chain is:

```sh
python examples/external_face_flux_adapter/adapt_face_flux.py \
  mgxs_library.h5 external_solver_raw_face_flux.h5 \
  -o homogeneous_face_flux.h5 \
  --dataset solver/face_flux \
  --layout MGF \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX

openmc2donjon check-face-flux mgxs_library.h5 \
  --surface-flux openmc_surface_flux.h5::detector/surface_phi \
  --homogeneous-face-flux homogeneous_face_flux.h5::homogeneous_face_flux \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX

openmc2donjon make-adf-sidecar mgxs_library.h5 \
  -o adf_sidecar.h5 \
  --mode flux-ratio \
  --surface-flux openmc_surface_flux.h5::detector/surface_phi \
  --homogeneous-face-flux homogeneous_face_flux.h5::homogeneous_face_flux \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --adf-kind production \
  --adf-real true
```
