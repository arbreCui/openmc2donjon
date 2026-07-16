# openmc2donjon User README

This page is the short user-facing path. It answers one question:

> I already have, or can generate, an OpenMC MGXS HDF5 handoff. What do I click
> or run to get a DONJON-ready ASCII file?

## The Main Path

For most users, the workflow is:

```text
MGXS HDF5
  -> Convert dry-run
  -> Convert
  -> Preview ASCII
  -> Bundle delivery files
  -> Open DONJON guide
```

The web UI pages map to that path:

| Step | Page | What the user does |
| --- | --- | --- |
| 1 | `/convert` | Pick the input `mgxs_library.h5`, output path, and format. |
| 2 | `/convert` | Run dry-run with production checks. No file is written. |
| 3 | `/convert` | If dry-run passes, run Convert. This writes the ASCII handoff. |
| 4 | `/convert` | Preview the ASCII LCM text before sending it downstream. |
| 5 | `/convert` | Use **Bundle handoff** to package the HDF5, ASCII output, and Converter receipt. |
| 6 | `/donjon` | Generate a starter DONJON ingest/solve deck from the bundle metadata. |

You do **not** need to visit every page.

## What Each Page Is For

| Page | Use it when | Required for direct conversion? |
| --- | --- | --- |
| Home | You want the product boundary and the shortest route into each workflow. | No |
| Converter | You want HDF5 -> `.mcompo.txt` or `.macrolib.txt` plus its receipt. | Yes |
| Inspect | You want to look inside the HDF5: groups, mixtures, mesh ID, XS curves, scatter matrix. | No, but recommended before a new case |
| Projects | You want to coordinate repeated or multi-component Converter runs. | No |
| Builder | You want to assemble and copy an advanced CLI command; the page does not execute it. | No |
| DONJON | You want a starter DONJON deck and `NCR`/`MACROLIB` loading hints. | Recommended |
| SPH | After Converter, your declared coarse model needs physical equivalence. | No |
| PyGan | You want optional writer diagnostics and ASCII-vs-PyGan semantic validation. | No |
| Commands | You want command reference and deep links. | No |

## Direct Conversion In The Web UI

1. Install the Web dependencies from a fresh checkout:

   ```sh
   python -m pip install -e ".[web]"
   cd web
   npm ci
   cd ..
   ```

2. Start the backend from the repository root:

   ```sh
   openmc2donjon serve
   ```

3. Start the frontend in another terminal:

   ```sh
   cd web
   npm run dev
   ```

4. Open <http://localhost:3000/convert>.

5. Fill:

   - input HDF5: `mgxs_library.h5`
   - output ASCII: usually `out.mcompo.txt` for a mapped library, or
     `out.macrolib.txt` for direct macrolib consumption
   - format: `L_MULTICOMPO` for mapped mixtures, `L_MACROLIB` for direct
     macrolib handoffs
   - enable production checks for real handoffs

6. Click dry-run first.

7. If the dry-run passes, click Convert.

8. After conversion, use the result actions:

   - Preview ASCII: sanity-check the LCM text blocks.
   - Bundle handoff: create a manifest-backed delivery directory.
   - Open DONJON guide: generate a starter DONJON deck from the ASCII output and
     bundle metadata.

The important output files are:

| File | Meaning |
| --- | --- |
| `out.mcompo.txt` | DONJON/DRAGON ASCII `L_MULTICOMPO`. |
| `out.macrolib.txt` | DONJON/DRAGON ASCII `L_MACROLIB`. |
| `<output>.convert.json` | Web-generated, hash-linked Converter receipt. A CLI user chooses this path with `--summary-json`. |
| `bundle/manifest.json` | Delivery bundle manifest with artifact paths, sizes, hashes, and summary metadata. |

## Direct Conversion On The CLI

Dry-run with production checks:

```sh
openmc2donjon mgxs_library.h5 \
  -o out.mcompo.txt \
  --check \
  --production \
  --dry-run
```

Convert and write a summary JSON:

```sh
openmc2donjon mgxs_library.h5 \
  -o out.mcompo.txt \
  --check \
  --production \
  --summary-json out.mcompo.txt.convert.json
```

Use MACROLIB instead:

```sh
openmc2donjon mgxs_library.h5 \
  --format macrolib \
  -o out.macrolib.txt \
  --check \
  --production \
  --summary-json out.macrolib.txt.convert.json
```

## What The Converter Does And Does Not Do

The converter does:

- read the OpenMC-facing MGXS HDF5 contract;
- preserve mixture/domain order;
- write DRAGON/DONJON ASCII `L_MULTICOMPO` or `L_MACROLIB`;
- carry optional ADF/DF and SPH/NSPH blocks if they already exist in the HDF5;
- run production preflight checks when requested;
- write the hash-linked receipt requested with `--summary-json`; the Web UI
  supplies `<output>.convert.json` automatically.

The converter does not:

- create physically correct homogenization corrections by itself;
- replace a real OpenMC/DRAGON/DONJON equivalence workflow;
- make ADF or SPH mandatory;
- require a special OpenMC fork for hexagonal cell-domain workflows.

## MULTICOMPO vs MACROLIB

`L_MULTICOMPO` is not a microscopic cross-section library.  In this project it
is a DONJON/DRAGON container for homogenized macroscopic mixtures, calculation
states, branch metadata, ADF/DF data, and other handoff fields.  DONJON usually
extracts a working `L_MACROLIB` from it with `NCR:`.

`L_MACROLIB` is already the working macroscopic library: groups, mixtures,
cross sections, scattering, optional ADF, and optional `GROUP/*/NSPH` factors.
Use it when the next DONJON step expects a macrolib directly.

Current physical SPH handoff status:

- Converter first writes the uncorrected reference `L_MACROLIB` and its
  hash-linked receipt from the model-declared HDF5;
- native DRAGON `SPH:` solves the project-declared coarse geometry with SN or
  SPN and writes the corrected `NSPH` MACROLIB;
- `validate-native-sph` binds the OpenMC reference, Converter receipt, native
  solver listing, corrected object, and DONJON verification evidence;
- choose `L_MULTICOMPO` or `L_MACROLIB` according to the downstream model, not
  because SPH imposes one universal object type.

## Physical SPH: When To Care

Start with direct conversion first.

Use `/equivalence` only when the homogenized model requires physical SPH. The
primary route is fine OpenMC reference -> Converter reference MACROLIB ->
native DRAGON SPH on the matching coarse geometry -> DONJON verification.
Whether a single assembly needs SPH is a model decision, not a geometry rule;
the fine and coarse domains, boundaries, group structure, and observable must
describe the same declared problem.

OpenMC CE/MG `make-openmc-sph-sidecar` + `apply-sph` remains an optional
alternate or cross-check. When a project explicitly chooses it, the OpenMC MG
macro calculation uses the same geometry and output regions as the CE
reference, may use Hn histogram angular representation internally, and must
iterate the rate-preserving update to convergence before Converter. That route
does not make OpenMC MG the universal production operator, and it cannot replace
a project-required native DRAGON/DONJON coarse solve.

For that optional OpenMC MG route, the CE run may tally both representations:

```text
P3 Legendre MGXS   -> DONJON handoff
Hn histogram MGXS  -> OpenMC MG macro solve -> SPH factor generation
```

There is no Hn-to-Legendre conversion step in the optional route. The Hn data
improves only the OpenMC MG flux used to compute its alternate SPH factors;
DONJON receives directly tallied Pn/Legendre MGXS with the converged correction
already folded into the handoff cross sections. This alternate path does not
change the primary native-DRAGON product route.

## Hexagonal Cases

The converter is geometry-agnostic. It does not need an OpenMC hex mesh object.
It needs a stable set of MGXS domains:

```text
one OpenMC domain -> one HDF5 mixture -> one DONJON mixture
```

For hexagonal examples in this repository, we use OpenMC cell-domain / lattice
domain style handoffs. The validation status is:

- C5G7 assembly-wise is the accepted OpenMC -> DONJON k-effective validation.
- The IRENA-30 ZREFL 91-position OpenMC-MG -> Converter -> DONJON SN8 line is
  an accepted downstream mapping and transport-mechanics baseline.
- That multigroup baseline is not an accepted continuous-energy fine -> native
  DRAGON SPH -> full-core physics result; the strict candidate remains on HOLD.

## OpenMC Branch Used For Hex Work

The current hex examples use the standard APIs from the official
[OpenMC repository](https://github.com/openmc-dev/openmc) and do **not** depend
on a private or project-specific OpenMC fork.

The hex minicase uses standard OpenMC hex-lattice/cell-domain modeling. If a
future workflow needs a true hex mesh tally API, the external branch may become
useful, but the current converter and web workflow do not require it.
