# DONJON SPH Loop Adapter

This example is a small template for connecting `openmc2donjon run-sph-loop`
to a DONJON low-order solve.  The default smoke is intentionally synthetic:
`fake_donjon_driver.py` writes a deterministic `L_FLUX` dump so the adapter
contract can be tested without a local DONJON deck.

Run it with:

```sh
bash examples/donjon_sph_loop_adapter/run_smoke.sh
```

The generated config demonstrates the production contract:

- `solver.command` consumes `{ascii_input}` and writes `{result}`.
- `map_h5` maps OpenMC/DONJON mixtures to one-based DONJON scalar flux IDs.
- `postprocess.command` can replace `{workflow_ascii}` with a DONJON-corrected
  handoff at `{output}` after each SPH update.
- placeholders available to commands include `{iteration}`, `{iteration1}`,
  `{loop_dir}`, `{solve_dir}`, `{workflow_dir}`, `{input_h5}`,
  `{ascii_input}`, `{result}`, `{previous_sph}`, `{workflow_ascii}`,
  `{sph_sidecar}`, `{augmented_h5}`, and `{output}`.

For a real case, write the config with the package CLI and provide the
case-specific DONJON solve deck that dumps scalar volume fluxes.

## Real DONJON Runner

For production wiring, use `make-donjon-sph-loop-config`.  It writes a
`run-sph-loop` config that calls the packaged `openmc2donjon.donjon_deck_runner`
for both phases:

```sh
openmc2donjon make-donjon-sph-loop-config \
  --output loop.json \
  --output-dir runs/sph_loop \
  --mgxs mgxs_library.h5 \
  --flux-map flux_map.h5 \
  --solve-template solve_lflux_dump.x2m.in \
  --flux-ratio-tolerance 1e-4 \
  --sph-change-tolerance 1e-4 \
  --donjon-root /path/to/dragon-5.1/Donjon
```

If the reference flux is not stored in `flux_map.h5::openmc_volume_flux`, add
`--reference-flux reference_flux.h5::dataset`.

When tolerances are set, `run-sph-loop` records per-iteration flux-ratio and
SPH-change residuals in `sph_loop_summary.json` and stops early once both are
below tolerance after `--min-iterations`.

Those tolerances are convergence targets, not production acceptance gates. Add
`--fail-on-nonconvergence` when a run that reaches `--iterations` without
meeting the targets should return non-zero. If you also use
`--acceptance-preset production`, the production gates check the handoff/audit
quality; they do not by themselves require SPH convergence. Add
`--acceptance-require-converged` or explicit residual acceptance limits when
the summary itself must fail on nonconvergence.

The runner stages the current ASCII macrolib under a short `/tmp` path, renders
an `.x2m` deck under
`$DONJON_ROOT/data/openmc2donjon/case_runs/donjon_sph_loop_adapter/`, runs
`rdonjon -q`, then copies the DONJON listing or corrected macrolib back to the
path requested by `run-sph-loop`.

Each `donjon_volume_flux_summary.json` records the flux map kind, selected
scalar IDs, per-mixture flux ranges, duplicate-ID warnings, and mesh coverage
diagnostics.  For `/kn` maps, nonpositive mesh IDs are allowed for inactive
cells and are written as `NaN` in `mesh_volume_flux`.

Templates:

- `templates/solve_lflux_dump.x2m.in` is a minimal runnable 1x2 Cartesian
  solve-side template.  Replace the geometry/tracking/solve body with the real
  DONJON model and keep
  `UTL: FLUX :: IMPR STATE-VECTOR * DUMP ;`.
- the default apply template is packaged at
  `src/openmc2donjon/templates/apply_nsph_mac.x2m.in`; override it with
  `--apply-template` only when your DONJON workflow needs custom `DSPH`/`MAC`
  postprocessing.
