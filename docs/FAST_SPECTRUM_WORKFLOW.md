# Fast-Spectrum Production Workflow

Fast-reactor cases need two things on top of the standard conversion flow:
a zero-flux fill before the input contract will accept the export, and —
when the coarse model must be equivalence-corrected — the rate-preserving
SPH loop with its fast-spectrum regularization. This page is the standard
route; the IRENA examples referenced at the bottom are its runnable,
validated instances.

## 1. Why the fill exists

A fast core has exactly zero Monte Carlo flux in the thermal groups of a
fast group structure (for ECCO-33: the bottom few groups), so their
flux-weighted tallies are `0/0 -> 0` at any statistics, and near-thermal
micro-flux bins can tally a positive `total` with a noise-level
nonpositive `transport_total`. The input contract rightly rejects both.
The fill substitutes those bins with the exact material data from the MG
macrolib the case is built around, recording the touched groups in the
`zero_flux_filled_groups` mixture attribute.

One-step (export, fill, check, convert in a single command):

```sh
openmc2donjon-from-openmc \
  --recipe my_recipe.py --statepoint statepoint.h5 \
  --fill-macrolib macrolib.h5 \
  --run-dir runs/case --check
```

The run summary records the fill (`zero_flux_fill_macrolib`,
`zero_flux_fill_total_bins`; schema v4). The standalone command is
`openmc2donjon fill-zero-flux` (same semantics, `--label-attr` selects the
mixture attribute naming the macrolib material).

## 2. Equivalence: the rate-preserving SPH loop

When per-region homogenization has a real defect to correct (absorbers,
reflectors), run the OpenMC-side CE/MG SPH loop with:

- `--sph-target rate` — the classic Hebert/DRAGON rate-preserving update.
  Its fixed point reproduces the CE reaction rates, so the corrected
  coarse model's k RECOVERS toward the CE reference instead of drifting
  (measured on the IRENA colorsets: the CSD absorber climbs from
  -423 pcm back to -78 pcm; the flux target drifts to -860 pcm on the
  same case). See `examples/irena30_sph_stage2_csd/README.md` for the
  full numbers.
- `--zero-flux-policy identity` and `--flux-floor-rel 1e-3` — matched
  zero bins and micro-flux bins are frozen: don't fit Monte Carlo noise.
- `--freeze-groups ...` — explicit switch-off for bins with no rate
  fixed point (chi-driven top groups; the established IRENA CSD practice
  of disabling group 31).

Validated prescriptions:

| Case class | Prescription |
| --- | --- |
| Pb reflector (pnl_ext) | rate, freeze {1, 31}, 2-3 iterations |
| B4C absorber (csd_int) | rate, freeze {1, 2, 31}, >= 8 iterations |

## 3. Getting the factors into DONJON

`NCR:` contains no SPH handling — `NSPH` records inside a `L_MULTICOMPO`
are inert archive metadata (verified against the DONJON sources and
numerically; see `docs/HDF5_INPUT_CONTRACT.md`). Two routes work:

1. Root `L_MACROLIB` output: its `GROUP/*/NSPH` records are read by
   `DSPH:` and applied by `MAC:`.
2. `openmc2donjon apply-sph`: fold the factors into the cross sections
   first, then convert to either format for any consumer. The
   MULTICOMPO + `NCR:` production route requires this pre-application.

### Bringing your own DONJON deck

The converter deliberately does not generate DONJON geometry from the
handoff — the low-order geometry, tracking, and solver are user-supplied
by design. The web `/donjon` guide turns the converter output path into
an editable deck skeleton: Cartesian TRIVAT diffusion/SPN, or the
hexagonal `HEXZ` + `SNT` / TRIVAC `MCFD 1` patterns whose validated
references are the accepted benchmark decks written by
`examples/irena30_zrefl_hex/write_donjon_decks.py`. The one contract to
keep when editing: the `GEO:` MIX numbering must follow the multicompo
mixture order (the `mixture_names` dataset of the handoff HDF5).

## 4. Runnable, validated instances

- `examples/irena30_zrefl_hex` — the accepted 91-hex benchmark
  (fill + convert + DONJON SN8; k within Monte Carlo statistics, power
  shape 1.27 % worst / 0.47 % RMS).
- `examples/irena30_sph_stage1` — single fissile assembly CE/MG loop
  (convergence study; damping 0.5 x 4 iterations).
- `examples/irena30_sph_stage2_csd` — CSD/PNL colorsets
  (`IRENA_SPH2_CASE`), rate-mode results and core-level closure.
