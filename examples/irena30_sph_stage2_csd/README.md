# IRENA local colorset SPH research

This directory preserves local seven-assembly IRENA colorset studies.  A
colorset is a valid qualification unit only when its fine and coarse geometry,
boundary conditions, homogenization volumes, and physical observable are the
same problem.  A converged local result is not automatically a full-core
component library.

The strict candidate route is:

```text
OpenMC CE fine colorset
  -> declared domain/component collapse
  -> Converter reference MACROLIB
  -> native DRAGON SPH on the matched coarse colorset
  -> final DONJON SN or SPN verification
```

Run a declared example case with:

```sh
bash examples/irena30_sph_stage2_csd/run_native_colorset_component.sh int_ext
```

Example labels include `int_ext`, `ext_int`, `csd_int`, `dsdf_int`, and
`pnl_ext`; they are benchmark data, not product defaults.  Signature mode may
instead declare any center and six neighbors explicitly.  Converter itself
accepts arbitrary user models and domain counts.

The runner uses ANL-24C-20MeV data, a Converter reference MACROLIB, native
DRAGON SPH, and matched node dimensions.  It forbids ADF, global eigenvalue
factors, zero-bin fill, floors, frozen groups, clipping, and post-hoc fitted
corrections.  Livolant is the default SN inner acceleration because DRAGON 5.1
prints auditable failure markers for that path.  Explicit GMRES results are
not production evidence until every one-speed solve can be proven converged;
the current DRAGON SNGMRE path can exhaust MAXIT without a failure marker.

There is currently no accepted IRENA local colorset SPH result.  Earlier
PNL/EXT and INT/EXT summaries are withdrawn as physics passes because their
listings contain unconverged final transport solves.  Earlier open-boundary
comparisons also confused collision `K-infinity` with finite-domain `keff`;
the validator now requires OpenMC leakage and the finite balance whenever a
vacuum boundary is declared.

For the actual IRENA full-core candidate, local material labels and the older
13 neighbor signatures are insufficient: they merge positions that are not
related by a symmetry of the loaded core.  The current route in
`examples/irena30_native_fullcore/` models all 91 fine assemblies and uses
either 91 independent domains or 21 exact global D3 symmetry orbits pooled
during OpenMC transport.

## Archived exploratory route

`run_stage2.sh` and the older charter/result files reproduce historical
OpenMC-MG-side experiments.  They used combinations of identity substitution,
flux floors, frozen groups, clipping, or incomplete energy coverage.  They are
retained as negative/research evidence only; `ALLOW_LEGACY_SPH2=1` is required
to run them, and their output must never be marked production-ready.
