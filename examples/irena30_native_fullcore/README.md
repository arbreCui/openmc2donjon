# IRENA-30 full-core physical handoff

This directory contains IRENA-specific examples, not product defaults.  The
reactor has 91 physical positions and five material labels, but neither number
is assumed by Converter or by a general project.

## Current physical route

The production candidate is a direct full-core equivalence calculation:

1. model all 91 heterogeneous assemblies in continuous-energy OpenMC with the
   real radial-vacuum and axial-reflective boundaries;
2. pool reaction rates and integrated flux *during transport* on the 21 exact
   global D3 symmetry orbits declared in `global_orbits.py` (or retain 91
   independent position domains);
3. pass the exported HDF5 through Converter to obtain the reference MACROLIB;
4. solve native DRAGON SPH on the same 91-position coarse geometry;
5. validate the final DONJON result jointly against OpenMC k-effective,
   leakage, and normalized 91-position power, including statistical and
   numerical-convergence evidence.

The 21 orbits are global full-core symmetry classes.  They must not be
replaced by the older 13 local neighbor signatures: six of those signatures
merge positions that are not related by a symmetry of the complete loaded
core.  Likewise, averaging already-collapsed cross sections after transport
is not equivalent to transport-time pooling and is forbidden here.

`irena_orbit_ce_model.py` and `build_orbit_ce_case.py` generate the strict fine
reference.  `export_orbit_recipe.py` is the mandatory Converter input recipe.
`write_fullcore_native_sph_deck.py --mapping d3-orbits` writes the matched
coarse SPH deck.  See `ORBIT_CE_REFERENCE.md` for commands and exported
evidence.

For the web runner, all five `SEQ_ASCII ... FILE` arguments are paths relative
to the Project component's declared `working_directory`. Put the converted
reference under that directory and name outputs there as well; the runner
snapshots inputs and archives newly created outputs without writing them back.
Absolute paths, `..`, dynamic `FILE` values, and external `PROCEDURE/*.c2m`
are intentionally rejected at this boundary.

This route uses SPH only.  It contains no ADF, zero-flux fill, blackening,
cross-section floor, factor clipping, frozen energy group, post-hoc orbit
averaging, or empirical/global eigenvalue multiplier.  A normal program exit
is not acceptance: every SPH iteration, one-speed inner solve, and final
transport solve must have auditable convergence evidence.

No acceptable IRENA CE-fine -> SPH -> full-core result is claimed until all
of the gates in step 5 pass on one hash-linked run.

### Final acceptance command

`validate_orbit_fullcore.py` keeps the two DONJON editions physically
separate.  The `OUT: ... INTG IN` MACROLIB supplies group-wise
`H-FACTOR * FLUX-INTG` for all 91 physical positions.  The
`EDI: ... MERG MIX COND SAVE` object is a 21-orbit aggregate used only for
global neutron-balance and leakage closure; it is never expanded into a
91-position power distribution.

```sh
python examples/irena30_native_fullcore/validate_orbit_fullcore.py \
  --physics-summary /path/to/physics_summary.json \
  --reference-h5 /path/to/mgxs_orbits.h5 \
  --region-verify /path/to/fullcore_91_region.macrolib.txt \
  --edi /path/to/fullcore_21_orbit.edi.txt \
  --result-listing /path/to/fullcore.result \
  --summary /path/to/fullcore_physics_summary.json
```

The hard decision includes native-SPH/final-solver convergence, statistical
k-effective, leakage, normalized 91-position power RMS and maximum error,
and the absence of ADF, empirical factors, clipping, floors, frozen groups,
and zero-bin filling.  A 21-entry edition cannot satisfy the power input
contract even when its orbit averages look acceptable.  The final evidence
records SHA-256 for the native summary, OpenMC handoff, both DONJON editions,
and the original result listing, and verifies that the native summary names
the same HDF5 and listing supplied to the final validator.

## Historical component-first diagnostic

`run_fullcore.sh`, `build_position_library.py`, and `write_donjon_decks.py`
preserve the earlier five-component experiment.  It qualified local
seven-assembly colorsets and copied five component records onto the 91
positions.  That route is useful for diagnosing component-library mechanics,
but it is not the current IRENA full-core production route:

- CSD and PNL local cases did not establish an acceptable physical SPH result;
- one record per material label cannot represent the distinct global leakage
  environments;
- the older 13 local signatures also overmerge six global classes.

The legacy runner therefore must not be cited as a full-core physics
acceptance even if DONJON terminates.  Its five labels and 91-position map are
facts about this example only; arbitrary users may have one component, many
components, another map, or no full-core workflow at all.
