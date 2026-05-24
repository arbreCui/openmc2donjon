# openmc2donjon-web

Next.js front-end for the openmc2donjon web UI. Talks to the FastAPI
backend started by `openmc2donjon serve`.

Current pages cover the command catalog, direct converter workflow, HDF5
inspection, and SPH-loop audit viewing. Additional command families are
added as focused workflow pages rather than as a generic shell wrapper.

## Local development

Two terminals: one for the backend, one for the frontend.

**Backend** (from the repo root):

```sh
python -m pip install -e ".[web]"
openmc2donjon serve            # FastAPI on http://localhost:8000
openmc2donjon serve --mock     # serve fixture data instead of real APIs
```

**Frontend** (from this directory):

```sh
npm install
npm run dev                    # Next.js on http://localhost:3000
```

Open <http://localhost:3000> and the home page should report
`status: ok` from the backend.

If the backend listens somewhere other than the default
`http://localhost:8000`, copy `.env.local.example` to `.env.local` and
set `NEXT_PUBLIC_API_BASE_URL` accordingly.

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
    page.tsx          Home (reads /api/health)
    commands/page.tsx /commands (CLI/web command catalog)
    convert/page.tsx  /convert (direct HDF5 -> ASCII converter workflow)
    inspect/page.tsx  /inspect (path input + summary + mixture table)
    audit/page.tsx    /audit (SPH loop summary viewer)
    settings/page.tsx /settings (local browser preferences)
    globals.css       Design tokens, glass utility, grad-text, button primitives
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
