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
| 5 | `/builder` | Bundle the HDF5, ASCII output, and `convert_summary.json`. |
| 6 | `/donjon` | Generate a starter DONJON ingest/solve deck from the bundle metadata. |

You do **not** need to visit every page.

## What Each Page Is For

| Page | Use it when | Required for direct conversion? |
| --- | --- | --- |
| Home | You want shortcuts to demos and major workflows. | No |
| Convert | You want HDF5 -> `.mcompo.txt` or `.macrolib.txt`. | Yes |
| Inspect | You want to look inside the HDF5: groups, mixtures, mesh ID, XS curves, scatter matrix. | No, but recommended before a new case |
| Builder | You want a shareable delivery bundle with manifest and hashes. | Recommended |
| DONJON | You want a starter DONJON deck and `NCR`/`MACROLIB` loading hints. | Recommended |
| Equivalence | You already have ADF/SPH data or want CLI commands to build sidecars. | No |
| Commands | You want command reference and deep links. | No |

## Direct Conversion In The Web UI

1. Start the backend:

   ```sh
   openmc2donjon serve
   ```

2. Start the frontend from the `web/` directory:

   ```sh
   npm run dev
   ```

3. Open <http://localhost:3000/convert>.

4. Fill:

   - input HDF5: `mgxs_library.h5`
   - output ASCII: usually `out.mcompo.txt` for a mapped library, or
     `out.macrolib.txt` for direct macrolib consumption
   - format: `L_MULTICOMPO` for mapped mixtures, `L_MACROLIB` for direct
     macrolib handoffs
   - enable production checks for real handoffs

5. Click dry-run first.

6. If the dry-run passes, click Convert.

7. After conversion, use the result actions:

   - Preview ASCII: sanity-check the LCM text blocks.
   - Bundle handoff: create a manifest-backed delivery directory.
   - Open DONJON guide: generate a starter DONJON deck from the ASCII output and
     bundle metadata.

The important output files are:

| File | Meaning |
| --- | --- |
| `out.mcompo.txt` | DONJON/DRAGON ASCII `L_MULTICOMPO`. |
| `out.macrolib.txt` | DONJON/DRAGON ASCII `L_MACROLIB`. |
| `convert_summary.json` | Machine-readable conversion summary: format, output path, dry-run/convert status, preflight decision, production flag. |
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
  --summary-json convert_summary.json
```

Use MACROLIB instead:

```sh
openmc2donjon mgxs_library.h5 \
  --format macrolib \
  -o out.macrolib.txt \
  --check \
  --production \
  --summary-json convert_summary.json
```

## What The Converter Does And Does Not Do

The converter does:

- read the OpenMC-facing MGXS HDF5 contract;
- preserve mixture/domain order;
- write DRAGON/DONJON ASCII `L_MULTICOMPO` or `L_MACROLIB`;
- carry optional ADF/DF and SPH/NSPH blocks if they already exist in the HDF5;
- run production preflight checks when requested;
- write `convert_summary.json` for downstream bundle/DONJON pages.

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

Current SPH consumption status:

- OpenMC-side SPH factors are written to the augmented HDF5 as explicit
  `NSPH` data.
- `L_MACROLIB` writes those factors as `GROUP/*/NSPH`; DONJON `DSPH:`/`MAC:`
  consumes this route directly.
- `L_MULTICOMPO` can carry the `NSPH` metadata, but DONJON `NCR:` does not
  currently promote those OpenMC-side factors into non-unity `GROUP/*/NSPH`
  values in the extracted macrolib.  For a DONJON SPH demonstration, choose
  `--format macrolib`.

## ADF/SPH: When To Care

Start with direct conversion first.

Use `/equivalence` only when you already know you need equivalence factors:

- ADF/DF: discontinuity factors, usually for diffusion/SPN nodal interfaces.
- SPH/NSPH: flux-equivalence factors, often preferred when the downstream
  DONJON method cannot consume ADF directly.

The `/equivalence` page is currently a command builder. It helps construct
sidecar/augmentation CLI commands, but it does not execute the physics workflow
inside the browser.

For production SPH in this project, OpenMC MG is the equivalence operator:
generate factors upstream from an OpenMC CE reference versus an OpenMC MG macro
calculation on the selected group structure with the same geometry and output
regions. The MG macro calculation can use OpenMC Hn histogram angular
representation to better retain anisotropic scattering effects while the
converter-facing handoff remains ordinary Pn/Legendre for DONJON. A single
assembly usually does not need SPH; colorsets and full-core macro models need
one factor per output region and energy group. Use `make-openmc-sph-sidecar` to
turn the CE/MG flux comparison into both an auditable CSV table and an SPH
sidecar, then use `augment-sph` to inject that sidecar before returning to
`/convert`.

Practically, the CE run may tally both representations:

```text
P3 Legendre MGXS   -> DONJON handoff
Hn histogram MGXS  -> OpenMC MG macro solve -> SPH factor generation
```

There is no Hn-to-Legendre conversion step in the normal workflow. The Hn data
improves the OpenMC MG flux used to compute SPH; DONJON receives directly
tallied Pn/Legendre MGXS plus explicit `NSPH` factors. DONJON consumes the
precomputed equivalence data; it is not the feedback operator in this route.

For downstream DONJON consumption of OpenMC-side SPH today, convert the
augmented HDF5 with `--format macrolib` so that the SPH factors appear as
`GROUP/*/NSPH`.

## Hexagonal Cases

The converter is geometry-agnostic. It does not need an OpenMC hex mesh object.
It needs a stable set of MGXS domains:

```text
one OpenMC domain -> one HDF5 mixture -> one DONJON mixture
```

For hexagonal examples in this repository, we use OpenMC cell-domain / lattice
domain style handoffs. The accepted validation status is:

- C5G7 assembly-wise is the accepted OpenMC -> DONJON k-effective validation.
- Hex is implemented as a converter/modeling capability smoke.
- There is not yet an accepted public hex benchmark in this repository.

## OpenMC Branch Used For Hex Work

Current local OpenMC hex examples do **not** depend on
`https://github.com/ebknudsen/openmc`.

The local OpenMC checkout used for the repository examples is the official
OpenMC repository:

```text
remote: https://github.com/openmc-dev/openmc.git
checkout: /Users/wen/openmc-workspace/src-v0.15.0
rev: 55b52b7ef
```

The hex minicase uses standard OpenMC hex-lattice/cell-domain modeling. If a
future workflow needs a true hex mesh tally API, the external branch may become
useful, but the current converter and web workflow do not require it.
