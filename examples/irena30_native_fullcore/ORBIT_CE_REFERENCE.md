# Strict full-core CE reference (21 D3 orbits)

This input is the full-core fine reference for native DRAGON SPH. It is not
the rejected OpenMC-MG Stage-3 experiment and it does not modify that archive.

`irena_orbit_ce_model.py` places all 91 heterogeneous IRENA assemblies behind
real radial-vacuum faces and reflective axial planes. The 21 global D3 orbit
records in `global_orbits.py` each own one reusable OpenMC wrapper universe and
one reusable cell-domain. Every member position reuses that wrapper, so MGXS
and the volume-flux CellFilter pool all orbit instances during transport. No
cross sections are averaged after the run.

Generate XML only (this command does not run OpenMC):

```sh
export IRENA_CE_COMPARE_DIR=/path/to/irena/ce_compare
export OPENMC_CROSS_SECTIONS=/path/to/openmc/cross_sections.xml
PYTHONPATH="$PWD/src:$PWD/examples/irena30_native_fullcore" \
  /path/to/openmc-python \
  examples/irena30_native_fullcore/build_orbit_ce_case.py \
  --case-dir /path/to/irena_orbit_ce
```

The external fine-assembly source must be selected explicitly with
`IRENA_CE_COMPARE_DIR`; no machine-specific fallback is used. CE nuclear data
is selected normally with `OPENMC_CROSS_SECTIONS`. After a statistically
qualified CE run, every formal handoff goes through Converter:

```sh
PYTHONPATH="$PWD/src" /path/to/openmc-python -m openmc2donjon.export_cli \
  --recipe examples/irena30_native_fullcore/export_orbit_recipe.py \
  --statepoint /path/to/irena_orbit_ce/statepoint.160.h5 \
  -o /path/to/handoff/mgxs_library.h5
```

The recipe exports ANL-24C-20MeV P0+P1 data using the consistent
nu-scatter matrix. Postprocessing attaches orbit-integrated
`openmc_volume_flux` and its standard deviation, raw energy-coverage evidence,
all 91 top-level position `kappa-fission`/`fission` rates and their standard
deviations (without orbit aggregation), OpenMC combined k-effective,
collision-balance K-infinity, finite-domain balance with the native OpenMC
leakage tally, and a complete 91-position / 21 orbit provenance map.

This route contains no ADF, zero-flux fill, blackening, floor, clipping,
post-hoc orbit averaging, or empirical/global eigenvalue coefficient.
