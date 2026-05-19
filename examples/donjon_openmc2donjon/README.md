# OpenMC-to-DONJON Data Workspace

This directory is the DONJON-side handoff workspace for the OpenMC to
openmc2donjon to DONJON path.

Current validation scope:

- C5G7 assembly-wise is the accepted physics validation line.
- Hex support has been implemented at the capability/prototype level.
- No suitable accepted hex benchmark is kept in this workspace yet.

Spatial mapping:

- one OpenMC MGXS domain produces one homogenized cross-section set;
- one cross-section set is written as one DONJON mixture;
- the DONJON input places that mixture back at the corresponding component or
  assembly position.

The accepted C5G7 path is assembly-wise. Components are not merged just because
they share a material label; different positions keep different mixtures so the
OpenMC spatial and environment effects are retained.

Main entries:

- `c5g7_validation/` - C5G7 validation decks, summary script, and acceptance runner.
- `case_manifests/c5g7_production_diffusion.json` - manifest-driven C5G7 handoff case.
- `case_runs/delivery_c5g7/` - latest generated C5G7 handoff case output.
- `run_acceptance.sh` - top-level C5G7 acceptance.
- `run_handoff_smoke.sh` - DONJON consumer smoke for the accepted C5G7 path.
- `run_production_pipeline_smoke.sh` - regenerate fresh C5G7 outputs and rerun DONJON.
- `accepted_baseline_manifest.json` - machine-readable accepted C5G7 baseline.

The original DRAGON/DONJON benchmark directories are outside this handoff
workspace and are not managed here.
