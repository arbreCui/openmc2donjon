# IRENA-30 ZREFL 91-Hex Accepted Benchmark

This example runs the full hex production workflow on a real reactor case:
the IRENA-30 sodium-cooled small modular fast reactor, 91-hex core, in its
2D ARI ZREFL configuration (all control rods inserted, single 10 cm axial
slab, axial reflective, radial vacuum).

```text
OpenMC-MG 33g transport (91 explicit hexes, 5 materials)
  + per-position MGXS tallies (91 cell domains)
  -> openmc2donjon L_MULTICOMPO (91 mixtures, P1)
  -> DONJON NCR: + SNT: SN8 transport   (primary k-eff comparison)
       + EDI: MERG MIX COND             (per-position nu-fission rates)
  -> DONJON NCR: + TRIVAC MCFD diffusion (coarse-mesh diagnostic)
```

Two field checks gate the run: the SN8 k-eff delta against the paired
OpenMC run, and the normalized per-position nu-fission (fission source)
distribution over the 52 fuel hexes — DONJON's `NUSIGF * FLUX-INTG` from
the mixture-merged one-group edition vs the statepoint's own nu-fission
reaction-rate tallies (`OPENMC2DONJON_IRENA_POWER_MAX_REL`, default 2%
worst position, and `OPENMC2DONJON_IRENA_POWER_MAX_RMS`, default 1% RMS).

The paired OpenMC run's own k-effective is the reference, so the comparison
is a clean code-to-code check on the same 33-group cross sections: OpenMC
Monte Carlo MG transport vs DONJON deterministic transport, with the
converter in between. One OpenMC hex cell domain maps to one DONJON mixture
in DRAGON HEXZ ring/position order (`R{ring}P{pos}_{label}`).

## Local inputs (not shipped in this repository)

- `IRENA30_DIR` (default `/Users/wen/openmc-workspace/irena`):
  the IRENA workspace providing `geometry_91hex.py`.
- `IRENA30_MACROLIB` (default `$IRENA30_DIR/build/macrolib.h5`):
  the 33-group OpenMC MG macrolib (INT/EXT/CSD/DSDF/PNL).
- A local DRAGON/DONJON checkout with `Donjon/rdonjon`
  (default `/Users/wen/dragon-5.1`, override `OPENMC2DONJON_ROOT`).

## Run

```sh
bash examples/irena30_zrefl_hex/run_zrefl_keff.sh
```

Defaults: 50k particles x 130 batches (30 inactive), OpenMC k-eff sigma
~25 pcm. The SN8 delta is gated at `OPENMC2DONJON_IRENA_MAX_DELTA_PCM`
(default 300 pcm); the MCFD diffusion result is reported as a diagnostic
only (single mesh point per hex, so it carries a large spatial
discretization bias on 17.5 cm fast-reactor hexes).

## Multi-group-mode gotchas this example encodes

1. **Group order.** OpenMC *multi-group-mode* statepoints return mgxs
   arrays in ascending-energy order — the opposite of CE-mode statepoints.
   The recipe passes `xs_kwargs={"order_groups": "decreasing"}` so the
   exported HDF5 follows the converter contract (index 0 = highest energy).
   Without this the multicompo scatter matrix becomes upscatter-dominated
   and DONJON's flux solve diverges to NaN.
2. **Zero-flux thermal groups.** A fast core has literally zero Monte Carlo
   flux in the thermal groups of the 33-group structure, so their
   flux-weighted tallies are 0/0 -> 0 at any statistics and the input
   contract rejects the file (`transport_total must be positive`).
   `fill_zero_flux_groups.py` substitutes the exact material data from the
   MG macrolib for those groups and records the filled group indices in the
   `zero_flux_filled_groups` mixture attribute. (Track-length estimators
   such as `total`/`absorption` reproduce the macrolib to machine precision
   wherever flux is nonzero; analog scatter-matrix rows stay noisy in
   near-zero-flux epithermal groups, which the k-eff comparison shows is
   immaterial.)
3. **DONJON path length.** `SEQ_ASCII ... FILE` paths are truncated at 72
   characters; the staged multicompo is copied to a short `/private/tmp`
   path before deck generation.
4. **Hex discretizations.** SNT/DUAL solvers want `SPLITL` lozenge
   splitting; TRIVAC `MCFD` requires *unsplit* hexes
   (`NEIGHB: INVALID NUMBER OF HEXAGONS` otherwise).

## Status

**Accepted** (see `docs/ROADMAP.md` and
`examples/donjon_openmc2donjon/accepted_baseline_manifest.json`): both
gates passed in one `run_zrefl_keff.sh` invocation, and the locked
summaries live under the local workspace's `irena30_zrefl_accepted/`
directory, checked by the baseline manifest validation.

| Gate | Result | Threshold |
| --- | --- | --- |
| SN8 k-eff vs paired OpenMC (1.192232 +/- 21 pcm) | 1.192125, **-9.0 pcm** | 300 pcm |
| Power shape, worst fuel position | **1.27 %** (R4P21_EXT) | 2 % |
| Power shape, RMS over 52 fuel positions | **0.47 %** | 1 % |

The TRIVAC MCFD diffusion diagnostic (+2532 pcm) is reported but not
gated: one mesh point per 17.5 cm hex is far too coarse for a fast core,
and it documents why the transport solver is the meaningful consumer.

Different-seed robustness (`IRENA_SEED=20260707`): OpenMC
1.192715 +/- 23 pcm, SN8 delta +28.6 pcm, power shape 1.40 % worst /
0.56 % RMS — both gates pass away from the accepted run's seed. The
worst position is consistently the low-power edge hex R4P21_EXT.
