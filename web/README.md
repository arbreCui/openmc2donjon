# openmc2donjon-web

Next.js front-end for the openmc2donjon web UI. Talks to the FastAPI
backend started by `openmc2donjon serve`.

This is the **M0 scaffold**: only a home page that confirms the backend
is reachable. Real CLI command pages land in later milestones.

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
| `npm run dev`     | Start the Next.js dev server with Turbopack.  |
| `npm run build`   | Production build.                             |
| `npm run start`   | Serve the production build locally.           |
| `npm run lint`    | Run ESLint (`next/core-web-vitals` profile).  |
| `npm run typecheck` | Run `tsc --noEmit`.                         |

CI runs `npm ci`, `npm run lint`, `npm run typecheck`, and
`npm run build` on every push and pull request as a blocking job.

> **Dev caveat: don't run `npm run build` while `npm run dev` is
> active.** Both share the `.next/` cache directory; a production
> build leaves it in a state the dev server can't reload from
> (you'll get `ENOENT: app-build-manifest.json` and a 500 page).
> If you need to verify the build locally, either stop the dev
> server first (`kill $(lsof -ti:3000)`), or build into a
> throwaway dir: `next build --distDir .next-build`. After an
> accidental collision, `rm -rf .next` and restart `npm run dev`.

## Layout

```
web/
  app/                Next.js App Router pages
    layout.tsx        Root layout + primary nav
    page.tsx          Home (reads /api/health)
    inspect/page.tsx  /inspect (path input + summary + mixture table)
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
