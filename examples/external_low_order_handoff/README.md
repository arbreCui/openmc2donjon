# External Low-Order Handoff Example

This example shows the production ADF/DF interface when a low-order or nodal
solver has already produced volume flux and boundary net current data.

It is not a reactor benchmark. It is a deterministic handoff example that
exercises the user-facing data contract:

- MGXS HDF5 input with two spatial mixtures.
- External raw driver HDF5 using case-specific dataset paths.
- Raw face order and mixture order that differ from the MGXS order.
- Raw net current marked `positive inward`, converted to the project canonical
  `positive outward` convention.
- Homogeneous face-flux reconstruction.
- Heterogeneous/homogeneous face-flux contract check.
- Flux-ratio ADF sidecar generation, ADF injection, and DONJON ASCII readback.

Run it from the repository root:

```sh
bash examples/external_low_order_handoff/run_smoke.sh
```

By default it writes all generated artifacts under:

```text
/private/tmp/openmc2donjon_external_low_order_handoff/
```

Override the output directory or Python executable if needed:

```sh
RUN_DIR=/tmp/my_low_order_handoff \
PYTHON_BIN=/path/to/python \
bash examples/external_low_order_handoff/run_smoke.sh
```

The generated raw driver deliberately uses nonstandard paths:

```text
/solver/scalar_flux
/solver/boundary_current_density
```

The root attributes `volume_flux_dataset` and `net_current_dataset` tell
`make-low-order-driver --raw-driver` where to find them. The current dataset
declares `sign_convention = positive inward`, so the canonical driver written
by openmc2donjon stores `/net_current_density` as positive outward.

The key production chain is:

```sh
openmc2donjon make-low-order-driver mgxs_library.h5 \
  -o low_order_driver.h5 \
  --raw-driver external_solver_raw_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX

openmc2donjon check-low-order-driver \
  mgxs_library.h5 low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --face-widths 1.0

openmc2donjon make-homogeneous-face-flux mgxs_library.h5 \
  -o homogeneous_face_flux.h5 \
  --volume-flux low_order_driver.h5 \
  --net-current low_order_driver.h5 \
  --faces FD_XMIN,FD_XMAX,FD_YMIN,FD_YMAX \
  --face-widths 1.0

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
  --adf-kind external-low-order-example \
  --adf-real true
```
