# ElementX portfolio demo (static)

The portfolio demo is the redesigned ElementX frontend running in a read-only mode with **no
backend**. Everything it shows is a snapshot of what the real ElementX backend returned for two
bundled example files.

| | |
|---|---|
| Switch | `VITE_DEMO_MODE=true` (set for `--mode demo` by `frontend/elementx-frontend/.env.demo`) |
| Data | `frontend/elementx-frontend/public-demo/demo/*.json` (about 0.3 MB) |
| Generator | `backend/scripts/build_demo_data.py` |
| Static host | `render.demo.yaml` (a static site; new names; the existing `render.yaml` is untouched) |

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
* The unchanged original remains at `backend/tests/fixtures/`. It is already tracked in git, so it
  is visible in the repository and its history if the repository is public. If the identifiers
  should not be public, make that decision separately (replace the fixture, or keep the repository
  private); this demo does not rewrite history.
* Each experiment records the SHA-256 and size of the unmodified source file.
* The header carries the instrument's file title and mass entry, a file-open date and software
  versions. No operator name, institution or path was found. Review it yourself before making the
  repository public.
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

`/#explore` opens the workspace directly.

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

## Deploy to Render (static site)

Nothing is deployed by this repository.

1. In the Render dashboard choose **New → Blueprint**, pick this repository and the branch to
   publish, and set the **Blueprint file path** to `render.demo.yaml`. (Alternatively, **New →
   Static Site** with root directory `frontend/elementx-frontend`, build command
   `npm ci && npm run build:demo`, publish directory `dist`.)
2. Keep **auto-deploy off** if you want manual control. No environment variables, disk or database
   are needed. Set `NODE_VERSION` to a Node release that satisfies Vite 7 (`^20.19` or `>=22.12`).
3. The blueprint also sets a Content-Security-Policy (script hash for the inline theme script,
   `connect-src 'self'`) and `nosniff`. The CSP was exercised against the built demo with no
   violations; keep the hash in step if `index.html` changes (`build:demo` checks this).
4. Add the resulting URL to the README ("Live demo").

**Cost.** Render static sites are free (bandwidth and build-minute allowances apply; check current
limits). The demo uses no free web-service instance hours, no spin-down and no keep-alive pings.

**Rollback.** Redeploy a previous commit from the static site's *Events* tab, or point the site at
the previous branch. Deleting the static site does not affect any other service.

## Attribution

Materials Project data are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The app shows the source, licence and
retrieval date next to the data.
