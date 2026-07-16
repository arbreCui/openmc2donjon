# IRENA SPH Stage 3 — Fine Full Core vs Assembly-Homogenized Full Core

> **Archived rejected research line — not the current product route.** This
> OpenMC-MG-side Stage 3 calculation is retained only as a diagnostic and
> requires `ALLOW_REJECTED_FULLCORE_SPH=1`. The current IRENA candidate keeps
> all 91 fine positions and uses either 91 independent domains or 21 exact D3
> orbits pooled during OpenMC transport, followed by Converter and native
> DRAGON full-core SPH. The older five-component reuse map is withdrawn too.

Third stage of the archived OpenMC-side SPH research route for IRENA-30: full-core
equivalence on the 91-hex 2D ARI ZREFL core.  Unlike Stages 1/2
(single-assembly and colorset), the fine model here is the COMPLETE core
in continuous energy — a model that has no DRAGON counterpart — and the
coarse model is still the COMPLETE 91-position core, but each top-level core
position is homogenized into one hexagonal node — exactly the DONJON full-core
layout. The 91 positions are not all fuel assemblies.
Within this archived diagnostic, the only permitted correction is the
rate-preserving CE/MG SPH fixed-point
iteration.  It produces position/group factors from paired flux tallies and
ties statistically equivalent positions over the core's exact 120-degree
symmetry orbits. Eigenvalue fitting and post-hoc global multipliers are
forbidden. No Stage 3 SPH result is currently accepted.

## Model roles

There are deliberately three calculations, but only two geometries:

| calculation | geometry | purpose |
| --- | --- | --- |
| OpenMC CE | **fine**, fuel pins and absorber bundles explicit in their corresponding core positions | reference truth and homogenized MGXS/flux tallies |
| OpenMC MG | **assembly-scale homogenized full core**, all 91 core positions retained and each position represented by one homogeneous hex node | isolate the CE-to-MG homogenization/SPH error without changing solver family |
| DONJON | **assembly-scale homogenized full core**, the same 91-position node layout | deterministic consumer/closure calculation |

Here, "coarse" never means a single-assembly calculation: it means that the
internal heterogeneous geometry of each core position has been homogenized
while the whole 91-position core is retained. OpenMC MG must use this
assembly-scale homogenized full-core geometry. If it retained the fine pin
geometry, an OpenMC CE/MG difference would not predict what DONJON consumes.

```text
1. CE truth         : explicit-91-hex full core, assembly-resolved CE
                      geometry (pin lattices, CSD B4C bundles) from the
                      IRENA workspace colorset infrastructure; radial
                      vacuum on the 66 outer faces, 10 cm axial slab,
                      reflective z.  The 91 top-level hex cells are the
                      MGXS cell domains (same names/positions/order as
                      the accepted MG benchmark irena30_zrefl_hex).
2. MG full core     : mgxs.Library.create_mg_mode() -> the complete core
   (homogenized)      with 91 core-position hex nodes, same
                      boundaries = the DONJON full-core layout.
                      SPH: iterative CE-flux/MG-flux rate-preserving
                      updates over the physical 91 x 33 table.
3. DONJON consumer  : corrected handoff -> L_MULTICOMPO -> NCR: ->
                      SNT SN8 (HEXZ 91 SIDE 10.1036 SPLITL 2), closed
                      against the CE truth k.
```

## Run

```sh
export ALLOW_REJECTED_FULLCORE_SPH=1
export IRENA_CE_COMPARE_DIR=/path/to/irena/ce_compare
export IRENA30_DIR=/path/to/irena/workspace
export IRENA30_MACROLIB=/path/to/irena/build/macrolib.h5
export OPENMC_CROSS_SECTIONS=/path/to/openmc/cross_sections.xml
export OPENMC2DONJON_ROOT=/path/to/dragon-5.1
bash examples/irena30_sph_stage3_fullcore/run_stage3.sh
```

Knobs (environment):

| knob | default | meaning |
| --- | --- | --- |
| `RUN_ROOT` | `${TMPDIR:-/tmp}/o2d_irena30_stage3` | working tree |
| `IRENA_PARTICLES/BATCHES/INACTIVE/SEED` | 50000/130/30/47 | CE truth run |
| `MG_PARTICLES/BATCHES/INACTIVE` | 200000/130/30 | MG twin runs (seed 31+iter) |
| `SPH_STRATEGY` | `rate-preserving` | the only allowed route; empirical global scaling is rejected |
| `SPH_ITERATIONS` | 4 | CE/MG fixed-point iterations before final evaluation |
| `SPH_START_ITER` | 1 | resume at this iteration; use `SPH_ITERATIONS+1` for finalization only |
| `SPH_TARGET` | `rate` | required diagnostic reaction-rate-preserving fixed-point target |
| `SPH_DAMPING` | 0.5 | numerical relaxation of the physical update; never a fitted correction |
| `SPH_TIE_120` | 1 | tie any local factors over three-member 120-degree orbits before use |
| `MAX_CE_FLUX_REL_STD`, `MAX_MG_FLUX_REL_STD` | 0.20 | flux std-dev gates |
| `MAX_SPH_UPDATE_RESIDUAL` | 0.02 | required convergence gate on `abs(raw update - 1)` |
| `FILL_MAX_TOTAL_REL_STD` | 0.5 | replace statistically unresolved total-XS bins from the material macrolib |
| `FILL_MAX_SCATTER_ROW_OVERSHOOT_REL` | 0.01 | replace bins whose P0 scatter row is more than 1% above total |
| `EVALUATE_FINAL_SPH` | 1 | run an MG twin that consumes the final sidecar exactly |
| `RUN_DONJON` | 1 | run the DONJON SN8 closure leg (0 = OpenMC only) |
| `MCO_CHECK` | 1 | `--check` on multicompo conversion (0 for smoke stats) |
| `OPENMC_THREADS` | 8 | |

Local inputs (not shipped):

- `IRENA_CE_COMPARE_DIR` (required when the CE statepoint is not reused):
  `colorset_common.py` + `openmc_colorset.py` (CE materials and assembly
  universes, including the CSD B4C pin bundle).
- `IRENA30_DIR` (required when the CE statepoint is not reused):
  `geometry_91hex.py`, the authoritative ring/position layout (28 INT +
  3 DSDF ring 1 + 6 CSD ring 3 pos 0,3,6,9,12,15 + 24 EXT + 30 PNL).
- `IRENA30_MACROLIB` (required): source
  for the zero-flux thermal-group fill of the DONJON handoff.
- CE nuclear data via `OPENMC_CROSS_SECTIONS`; DONJON via `DONJON_DIR` or
  `OPENMC2DONJON_ROOT` when `RUN_DONJON=1`. `python3` and `openmc` are taken
  from `PATH` unless `PYTHON_BIN` or `OPENMC_EXEC` overrides them.

## Geometry adaptation notes

- **Explicit-91-hex with segment-shared planes.**  Planes are shared per
  face SEGMENT (vertex-pair key), the `openmc_explicit7_probe.py`
  technique scaled to 91 hexes: each interior face is one transmission
  plane referenced by both neighbours; each of the 66 outer faces is a
  vacuum plane referenced only by its own hex.  Sharing by infinite line
  would be wrong — outer faces are co-linear with interior faces of
  hexes deeper in the array (see the `geometry_91hex.py` docstring), and
  a shared vacuum plane would kill particles crossing the interior
  segments.
- **Hex orientation.**  The core cells are flat-top hexagons (face
  normals at 30 + 60k degrees), matching both `geometry_91hex` and the
  colorset assembly prisms (`hex_prism(orientation="x")`), so the CE
  assembly universes drop in without rotation; each hex cell translates
  its (origin-built) assembly universe to the hex centre.
- **Pitch margin.**  The colorset assembly envelope edge is
  ~9.9950 cm (`lattice_box_edges()[-1]`, GLOW lattice-box spec) while
  the core hex cell edge is 10.1036 cm (DRAGON `SIDE`, pitch 17.5 cm).
  The ~0.109 cm edge margin is filled with sodium by the assembly
  universes' `*_lattice_cell_catchall` cells, consistent with the core
  deck's 17.5 cm assembly pitch.
- **Axial slab.**  z in [0, 10] cm, reflective — the accepted
  benchmark's 2D ARI ZREFL slab (the colorset models used ±50 cm; the
  assembly universes are z-invariant so only the bounding planes move).
- **Homogenization volume** is the full hex cell,
  sqrt(3)/2 · 17.5² · 10 cm³, matching the DONJON HEXZ cell.

## Group ordering

The CE export recipe does NOT pass `order_groups="decreasing"` (deviation
from the zrefl recipe): that override compensates the ascending group
order of MULTI-GROUP-mode statepoints; on the CE statepoint used here the
mgxs default already satisfies the converter contract (index 0 = highest
energy), following Stage 2.  Verified in the smoke gate via the exported
chi (fission spectrum weight in the top fast groups).

## Current status (2026-07-15)

**NOT ACCEPTED.**  The former uniform 1.0082 result was obtained by matching
the full-core eigenvalue rather than by solving the SPH fixed-point equations.
It has been withdrawn from the frontend, web execution API, and Stage 3 run
script. It remains mentioned here only as rejected historical evidence and
must not be used as a correction.

The permitted rate target is

```text
NSPH(n+1) = NSPH(n) [phi_MG(n) / (NSPH(n) phi_CE)]^alpha
Sigma'    = Sigma / NSPH
```

At convergence, `phi_MG = NSPH phi_CE`, so each corrected macroscopic
reaction rate satisfies `Sigma' phi_MG = Sigma phi_CE`.  `k-effective` is
checked only after the factors have converged; it never enters this equation.
Any physical acceptance also forbids frozen groups, relative flux floors, and
factor clips.
If a nonzero tally bin is unresolved, the run must increase statistics or fail.

The original DONJON `NaN` was separately traced to micro-flux P1 MGXS noise:
36 P0 scatter rows exceeded total, with a worst overshoot of 44%.  The two
fill uncertainty/stability criteria above replace each unresolved whole group
from the exact material macrolib.  Both uncorrected and corrected handoffs now
pass conversion and reach a finite, normal DONJON end.

| quantity | result |
| --- | ---: |
| OpenMC CE truth | 1.146150 ± 0.000162 |
| OpenMC MG, uncorrected | 1.149066 (`+254.4 pcm`) |
| DONJON SN8, uncorrected | 1.148551 (`+209.5 pcm`) |
| Physical rate-SPH after eight recorded updates | MG `+408.4 pcm`; DONJON `+336.6 pcm`; update residual 13.4% |
| Stage 3 decision | **NOT ACCEPTED** |

The recorded physical iteration had not converged and worsened both OpenMC-MG
and DONJON eigenvalue closure. This entire Stage 3 route is now permanently
withdrawn: even a later diagnostic rerun that passes its local numerical gates
cannot become an IRENA physics acceptance. Future acceptance belongs to the
current 91-position or exact 21-D3-orbit transport-pooled route through
Converter, native DRAGON full-core SPH, and DONJON. The machine-readable
withdrawn diagnostic is `$RUN_ROOT/stage3_closure.json`.

No ADF path exists in this archived workflow: the DONJON `SNT` consumer reads
the SPH-corrected multicompo cross sections directly. It remains diagnostic
evidence only and cannot supply factors to the current product route.

## Closure numbers to record

All deltas in pcm vs the CE truth k (`compare_keff.py`, summary JSON at
`$RUN_ROOT/stage3_closure.json`):

1. **CE truth k** (± MC sigma) — the reference; has no MG/DONJON
   counterpart bias.
2. **Uncorrected MG twin k** (iteration 1) — the full-core
   per-position homogenization defect.
3. **Corrected MG twin k** (`mg_case_sph_final`) — residual defect from a
   run that consumes the final converged rate-preserving SPH sidecar.
4. **DONJON SN8 uncorrected k** — layout benchmark leg (also isolates
   MG-MC vs SN solver spread; the accepted MG-vs-DONJON benchmark pair
   is 1.1922318 ± 25 pcm vs 1.192125).
5. **DONJON SN8 corrected k** — the product closure number.
6. **Recovered-defect metric** — (corrected − uncorrected) /
   (CE − uncorrected), fraction of the homogenization defect recovered
   (Stage 2 CSD colorset recovered −423 → −78 pcm for scale).

The eigenvalue is a closure observable, never a fitting target. Leakage and
power shape are mandatory co-gates, and the DONJON pair verifies that the
same converged SPH handoff transfers to the deterministic consumer.

## Low-statistics smoke policy

A low-particle SPH smoke is intentionally not offered: it would require flux
floors, group freezes, relaxed uncertainty gates, or clipped factors and could
therefore create a numerically convenient but nonphysical sidecar. Geometry
and file plumbing remain covered by unit/integration fixtures; a Stage 3
physics result must use statistics sufficient to pass the declared gates.
