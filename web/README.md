# openmc2donjon-web

Next.js front-end for the openmc2donjon web UI. Talks to the FastAPI
backend started by `openmc2donjon serve`.

The primary UI is Converter-centered and manifest-driven. A standalone user can
convert one OpenMC MGXS HDF5 directly. A durable project adds
`openmc2donjon.project.json` to declare any number of components, each input
contract and output path, plus the project's downstream consumer. The current
IRENA candidate is one 91-position fine reference with either 91 independent
domains or 21 exact D3 orbits pooled during transport; it starts on HOLD. The
older five-colorset reuse map is a withdrawn diagnostic, not an executable
product or acceptance route. Command catalogs, builders, and PyGan diagnostics
remain under advanced tools.

The primary physical-equivalence route is Converter reference MACROLIB ->
native DRAGON `SPH:` -> independent validation. That native-SPH acceptance
route forbids ADF substitution and fitted empirical/global eigenvalue
coefficients. Generic ADF/DF carry and sidecar helpers remain advanced support
tools for other explicitly declared workflows; they do not weaken the
native-SPH policy.

## Local development

From a fresh checkout, install the Python package and Web dependencies:

```sh
git clone https://github.com/arbreCui/openmc2donjon.git
cd openmc2donjon
python -m pip install -e ".[web]"
cd web
npm ci
cd ..
```

Then use two terminals: one for the backend, one for the frontend.

**Backend** (from the repo root):

```sh
openmc2donjon serve            # FastAPI on http://localhost:8000
openmc2donjon serve --mock     # serve fixture data instead of real APIs
```

The default bind address is `127.0.0.1`, so live-mode file browsing and
conversion stay local to the current machine. If you intentionally bind the
backend to a non-loopback address such as `0.0.0.0`, set a workspace root:

```sh
openmc2donjon serve --host 0.0.0.0 --workspace-root /path/to/openmc-runs
```

Without `--workspace-root`, non-loopback live mode refuses to start unless
`--unsafe-remote` is passed explicitly. When a workspace root is active, the
Web file browser treats `~` as that workspace root, not as the operating-system
home directory.

**Frontend** (from this directory):

```sh
cd web
npm run dev                    # Next.js on http://localhost:3000
```

Open <http://localhost:3000>. The home page presents the product boundary;
live backend status appears on the workflow pages that need it.

If the backend listens somewhere other than the default
`http://localhost:8000`, copy `.env.local.example` to `.env.local` and
set `NEXT_PUBLIC_API_BASE_URL` accordingly.

### PyGan backend demo

The Web UI reflects the Python environment used to start the backend:

- `/convert` calls `/api/health` and reports whether PyGan is importable.
- If PyGan is available, the writer selector enables the PyGan backend.
- `/pygan` shows the built-in ASCII writer as the default ready backend and
  PyGan as an optional backend. It then reports the PyGan doctor result, module
  import paths, and a runnable semantic writer comparison report.
- After a successful PyGan conversion, the result panel shows `Validate PyGan`
  and opens `/pygan` with the comparison inputs prefilled.

For a PyGan-focused demo, start the backend from the same Python environment
where `openmc2donjon pygan-doctor` reports `pygan_backend=available`.
If PyGan is unavailable, the Web UI should still make it clear that the normal
ASCII writer path remains usable.

## Scripts

| Command           | What it does                                  |
| ----------------- | --------------------------------------------- |
| `npm run dev`           | Start the Next.js dev server with Turbopack.                                |
| `npm run build`         | Production build into `.next/` (used by CI).                                |
| `npm run build:verify`  | Same build but into `.next-build/`, safe to run alongside `npm run dev`.    |
| `npm run start`         | Serve the production build locally.                                         |
| `npm run lint`          | Run ESLint (`next/core-web-vitals` profile).                                |
| `npm run typecheck`     | Run `tsc --noEmit`.                                                         |

CI runs `npm ci`, `npm run lint`, `npm run typecheck`, and
`npm run build` on every push and pull request as a blocking job.

> **Dev caveat: don't run `npm run build` while `npm run dev` is
> active.** Both share the `.next/` cache directory; a production
> build leaves it in a state the dev server can't reload from
> (you'll get `ENOENT: app-build-manifest.json` and a 500 page).
> Use `npm run build:verify` instead — it sets `NEXT_DIST_DIR=.next-build`
> via `next.config.ts`, so the verification build lives in
> `.next-build/` and `.next/` stays untouched. CI still uses the
> plain `npm run build`. After an accidental `.next/` collision, run
> `rm -rf .next` and restart `npm run dev`.

## Layout

```
web/
  app/                Next.js App Router pages
    layout.tsx        Root layout + primary nav
    page.tsx          Home (product boundary + direct Converter quick start)
    commands/page.tsx /commands (CLI/web command catalog)
    convert/page.tsx  /convert (generic HDF5 -> checked object + receipt)
    openmc/page.tsx   /openmc (generic OpenMC handoff preparation)
    equivalence/      /equivalence (native DRAGON SPH runner/validator; optional OpenMC-side and ADF support)
    donjon/page.tsx   /donjon (generic consumer guide; IRENA template mode optional)
    inspect/page.tsx  /inspect (read-only generic HDF5 structure + MGXS visualizations)
    projects/page.tsx /projects (create, edit, and inspect manifest-driven projects)
    pygan/page.tsx    /pygan (doctor + runnable semantic writer comparison)
    docs/page.tsx     /docs (product boundary and guide entry points)
    builder/page.tsx  /builder (non-mutating CLI builders; commands run in a shell)
    settings/page.tsx /settings (local browser preferences)
    globals.css       Design tokens, surfaces, workflow steps, button primitives
  components/
    Nav.tsx           Top sticky nav
    inspect/          Inspect-page presentational pieces
      Summary.tsx        Path / mesh badge / 8-stat grid / detail rows / issues
      MixtureTable.tsx   Per-mixture roster table
      CrossSectionPlot.tsx  log-log Plotly chart (4 reaction-rate series)
      formatEnergy.ts    eV / keV / MeV unit formatter
  lib/
    api.ts            Typed fetch client for the FastAPI backend
    usePlotlyPlot.ts  Lifecycle hook: lazy import + newPlot + purge
  types/
    plotly.d.ts       Ambient module for `plotly.js-dist-min`
  tailwind.config.ts
  tsconfig.json
  next.config.ts
  postcss.config.js
  .env.local.example
```

## Conventions

- The FastAPI backend lives in `../src/openmc2donjon/web/` and is started
  via the `openmc2donjon serve` subcommand.
- Mock mode is a CLI flag on the backend, not an environment variable on
  the frontend. The frontend just calls `/api/health` and renders whatever
  the backend reports.
- Design tokens (CSS variables on `:root`, `.glass`, `.grad-text`,
  `.btn-*`) are shared with the broader project visual language and
  should be used in preference to ad-hoc colors.
