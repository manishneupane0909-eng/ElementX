# Fabrivium public demo (static)

The public site is the Fabrivium frontend running in a read-only mode with **no backend**. Everything
it shows is a snapshot of what the analysis backend returned for two bundled example files. The
GitHub repository and Python services still use the historical ElementX identifiers.

| | |
|---|---|
| Switch | `VITE_DEMO_MODE=true` (set for `--mode demo` by `frontend/elementx-frontend/.env.demo`) |
| Data | `frontend/elementx-frontend/public-demo/demo/*.json` (about 0.3 MB) |
| Generator | `backend/scripts/build_demo_data.py` |
| Static host | `render.demo.yaml` (a static site; new names; the existing `render.yaml` is untouched) |
| Live site | <https://www.fabrivium.com> |

## What is real, and what is not

| Example | Kind | Source |
|---|---|---|
| Fe2CoGe, annealed 900 °C for 48 h | **Real laboratory measurement** (Quantum Design VersaLab VSM; ten M-H loops and one M-T sweep) | `backend/tests/fixtures/Fe2CoGe_annealed_48hrs_900C_M_H_M_T.dat` |
| Synthetic XRD test pattern | **Synthetic**, a hand-written software test fixture. It is not a laboratory measurement and is not attached to the Fe2CoGe sample. | `backend/tests/fixtures/two_column_xrd_test.xy` |
| Materials Explorer entries | Reference data from the Materials Project (CC BY 4.0), retrieved on the date shown in the app | Materials Project API through `MaterialsClient` |
| Physics Copilot | **Recorded stored-record readouts.** No language model runs. | `/api/research-copilot/chat` with the model switched off |

No number in the demo is typed in or computed in the browser. The M-H and M-T values, loop
summaries, mass-normalised values and XRD maxima are the backend pipeline's output, stored as JSON.

## Provenance and redaction

* The raw instrument files are **not** published (`manifest.raw_instrument_files_published` is
  `false`). Only the derived analysis is.
* The original `.dat` header lists five instrument serial numbers (`COIL_`, `MOTOR_`, `OVEN_`,
  `PREAMP_` and `VSM_SERIAL_NUMBER`). The public snapshot **removes those five metadata fields and
  nothing else**. The change is listed in the manifest (`redactions`) and in the experiment's
  provenance panel in the app ("Changes in this public copy").
* The unchanged original remains at `backend/tests/fixtures/` because the backend tests and the
  snapshot generator need it. It is tracked in git, and the repository is public, so the five serial
  numbers are visible in that file and in the earlier commits that added it on the feature branches.
  The published demo JSON does not contain them. Cleaning them out of the repository means replacing
  the fixture and rewriting history, which has not been done.
* Each experiment records the SHA-256 and size of the unmodified source file.
* The header carries the instrument's file title and mass entry, a file-open date and software
  versions. No operator name, institution or path was found in it.
* Record dates (for example "Record created 10/8/2026") are fixed constants so the snapshots are
  reproducible. They are not measurement dates.

## Regenerating and checking the snapshots

```bash
# from backend/ (venv active)
python -m scripts.build_demo_data            # regenerate (reuses materials.json)
python -m scripts.build_demo_data --check    # re-run the real pipeline and compare, writing nothing
python -m scripts.build_demo_data --refresh-materials   # re-query Materials Project (needs MP_API_KEY)
```

`--check` drives the real FastAPI routes against a throw-away database, with ids and timestamps
fixed and the language model forced off, then compares every value with the committed files
(relative tolerance 1e-9). It does not compare the Materials Project file (network and key) or the
informational `environment` block.

From `frontend/elementx-frontend`:

```bash
npm run check:demo    # hashes, schema, redaction, synthetic labelling, no Ms/Tc keys, Copilot labels
npm run build:demo    # check:demo + type-check + demo build + bundle credential scan + dist check
```

The backend suite also runs the snapshot check (`backend/tests/test_demo_snapshots.py`).

## Run locally

```bash
cd frontend/elementx-frontend
npm install
npm run dev:demo        # http://localhost:5173/  (no backend needed)
# or a production-style preview
npm run build:demo && npx vite preview --mode demo
```

`/#explore` opens the workspace directly, and `/#about` opens the About page. These are hash routes, so
they need no server rewrite rule, and the browser's back and forward buttons move between the start
page, the About page and the workspace.

`/schedule` is a public booking path (not a hash route). The landing and About pages link to it with
the label “Schedule a Conversation”. Opening `/schedule` or `/schedule/` sends the browser to
<https://calendly.com/manishneupane0909/30min>. Calendly is not embedded.

The demo build includes `public-demo/_redirects` (Cloudflare Pages) and
`public-demo/schedule/index.html` as a fallback page. `npm run build:demo` copies both into `dist/`.
Local `vite` demo/preview also 302s `/schedule` through a small plugin in `vite.config.ts`.

On **Cloudflare Pages**, the `_redirects` file is the rule that makes
<https://www.fabrivium.com/schedule> open Calendly. Verify `dist/_redirects` after a demo build.

A legacy Render static site is not the public host. Do not change those services for this rebrand.

## What is disabled, and why

| Disabled | Reason |
|---|---|
| Sign-in and registration | No accounts exist; the landing page has one "Explore Demo" button |
| Creating or saving samples; adding experiments | Example records are read-only; there is no database |
| File uploads (magnetometry, XRD, CIF) | Phase 1 is static only |
| Live Gemini and free-text Copilot questions | No key is shipped and no model runs; replies are recorded readouts |
| Live Materials Project queries | The key must not be in the browser; a curated list is bundled |

Disabled controls are removed from the screen rather than shown greyed out. `authFetch` also throws
in demo mode, so a stray backend call fails loudly instead of reaching a network.

## Deploy (Cloudflare Pages)

The public site is Cloudflare Pages, root `frontend/elementx-frontend`, build `npm ci && npm run build:demo`,
output `dist`. `_redirects` in that output sends `/schedule` to Calendly.

A historical Render static site still exists. Do not change those services for this rebrand.

**Cost.** Render static sites are free (bandwidth and build-minute allowances apply; check current
limits). The demo uses no free web-service instance hours, no spin-down and no keep-alive pings.

**Rollback.** Redeploy a previous commit from the static site's *Events* tab, or point the site at
the previous branch. Deleting the static site does not affect any other service.

## Attribution

Materials Project data are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The app shows the source, licence and
retrieval date next to the data.
