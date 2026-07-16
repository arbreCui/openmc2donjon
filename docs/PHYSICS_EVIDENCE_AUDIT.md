# Physics Evidence Audit

Date: 2026-07-16

## Current conclusion

The local workspace does not yet contain an accepted IRENA continuous-energy
fine -> SPH -> full-core physics closure.

```text
OpenMC CE fine -> Converter -> native DRAGON SPH -> DONJON SN or SPN
```

The earlier IRENA `pnl_ext` and `int_ext` summaries reported converged SPH
fixed points, but their DONJON listings contain final one-speed transport
nonconvergence markers despite reaching the program's normal end. They are
therefore withdrawn as physics passes. The records remain useful negative
evidence under `.openmc2donjon-runs/`, but the backend and frontend now reject
them.

Those local records are also not valid inputs for the declared IRENA 91-node core: their
top-level colorset side is 9.9950212 cm, whereas the full-core node side is
10.1036 cm and includes an additional catch-all sodium annulus in the assembly
universe. The project contract now rejects this mismatch explicitly. The
full-core component reruns use 10.1036 cm for both fine colorset domains and
the native-SPH coarse geometry; no geometric dilution correction is inferred.

The product must therefore keep these statements separate:

- Converter contract pass: the declared HDF5 can be converted.
- Writer pass: the selected writer produced the expected LCM semantics.
- DONJON ingest pass: DONJON read the converted object.
- Physics evidence present: CE/MG flux, SPH, or reaction-rate diagnostics exist.
- Physics equivalence pass: a declared reference, target, uncertainty treatment,
  and tolerance all pass.
- Reactor validation pass: a component or full-core benchmark passes its
  declared acceptance criteria.

No earlier layer implies a later one.

## Evidence found

### Preserved May archive

An external DRAGON/DONJON validation workspace preserves a directory named
`openmc_ce_mg_33g_sph_minicase_accepted` with real MGXS HDF5, CE/MG flux
files, an SPH sidecar, converted ASCII, and a DONJON listing. That external
archive is not shipped in this repository.

It is useful handoff evidence, but its `openmc_sph_summary.json` records the
old update direction:

```text
previous_sph * (normalized_mg_flux / ce_flux) ** damping
```

That direction was later invalidated because the apply path divides cross
sections by NSPH. This archive must not be presented as accepted SPH physics.

### July post-fix records

`examples/openmc_ce_mg_33g_sph_minicase/PRODUCTION_EVIDENCE.md` records
post-fix runs using:

```text
previous_sph * (ce_flux / normalized_mg_flux) ** damping
```

The bundled web JSON mirrors one of those recorded runs. The original
statepoints, MGXS, sidecars, summaries, and corrected MACROLIB files from the
ephemeral system temporary directory are no longer present. The fixture is
therefore a report/UI snapshot, not live reproducible evidence.

A surviving DONJON consume listing proves that DONJON consumed NSPH in that
specific smoke. It does not reconstruct the missing OpenMC source evidence
and it is not a component or full-core physics acceptance result.

## Withdrawn July local native closures

The local runs corrected several input-contract errors found during audit:

- ANL-23C stopped at 10 MeV and lost nonzero fast reaction rate. The accepted
  `anl_24c_20mev` mesh restores the 10--20 MeV group; the Converter
  rate-balance eigenvalue then moved to -3.49 pcm from OpenMC.
- Their declared coarse hex side is 9.9950212 cm, matching that local OpenMC
  assembly envelope but not the 10.1036 cm full-core node.
- The OpenMC white boundary is represented explicitly in the coarse deck.

No ADF, global empirical multiplier, clipping, floor, frozen group, or
zero-bin fill was used. That does not override solver failure or geometry
mismatch. The backend and web UI now audit raw final-transport warnings,
negative-factor resets, oscillation stops, and whether every one-speed solve
has a provable convergence contract before showing a physics pass.

The INT/EXT run exposed a statistical-contract defect in the first validator:
it compared the Converter reaction-rate balance against the OpenMC combined
eigenvalue using only the latter estimator's uncertainty. The fine model now
tallies unfiltered absorption, nu-fission, and the excess-neutron contributions
from `(n,2n)`, `(n,3n)`, and `(n,4n)`. Because the statepoint does not retain
cross-score covariance, their uncertainty is propagated with a conservative
triangle bound. For INT/EXT the direct balance is 1.37925581 and the Converter
balance is 1.37928554 (about 3 pcm apart); neither XS nor eigenvalue is rescaled.

The audit also separated two eigenvalue meanings. Converter's MACROLIB
`K-INFINITY` is a collision balance and must not be compared directly with a
finite vacuum-domain `keff`. In the audited PNL case, the Converter collision
balance matched the direct OpenMC collision tally by about 1 pcm; including
OpenMC leakage brought the finite balance within about 10 pcm of the CE
eigenvalue. The large earlier discrepancy was missing leakage, not a justified
cross-section correction.

## Required next closure

Region and component counts must come from the selected model or manifest;
they must not be hard-coded to the five labels of the IRENA example. A
standalone component user can still qualify a matched component geometry. For
IRENA full-core acceptance, however, the next route is the direct 91-position
fine model, not copying five local component records.

1. Preserve the heterogeneous OpenMC CE model, statepoint, MGXS, tallies,
   energy boundaries, region map, volumes, uncertainties, and hashes.
2. Send the exact integrated flux, rates, group structure, and mapping through
   Converter to produce the uncorrected reference MACROLIB. Preserve hashes and
   compare writers when PyGan is selected.
3. Build the DRAGON/DONJON coarse model with the exact homogenized regions,
   solver convention, leakage/boundary treatment, and mixture mapping. An
   OpenMC MG calculation may be recorded as a predictor, but it cannot replace
   this downstream coarse solve.
4. Run native DRAGON SPH with its equation and convergence target declared
   before execution. No empirical global multiplier or numerical exemption is
   allowed.
5. Run DONJON verification on the matching coarse component with identical
   geometry, boundary conditions, groups, solver, and normalization.
6. Compare reaction rates by region and group, normalized flux shape, balance,
   and k-effective where meaningful. Apply Monte Carlo uncertainty and
   predeclared tolerances. A k-effective number alone is not acceptance.
7. Preserve the complete evidence bundle in a durable project directory, then
   mark only the layers that actually passed.

The IRENA implementation under `examples/irena30_native_fullcore/` now keeps
all 91 heterogeneous assemblies in OpenMC and either retains 91 independent
domains or pools tallies during transport on 21 exact global D3 symmetry
orbits. The older 13 local neighbor signatures overmerge six global classes;
the five-material component route overmerges further and remains diagnostic
only. The Converter reference, native full-core SPH, and DONJON result must
then pass joint k-effective, leakage, normalized 91-position power,
statistical-quality, and numerical-convergence gates. IRENA's counts remain
example data, never product defaults.

## Product implication

Converter remains the required handoff core. OpenMC MGXS, SPH, Project, PyGan,
and DONJON are modules around it. The UI must show evidence provenance and the
five evidence layers on every result page; fixtures and missing source
artifacts must never receive a physics PASS.
