# ElementX

Web app I built to keep track of rare-earth-free magnet samples — mostly MnAl and MnBi work. Upload XRD and VSM files, run stoichiometry, flag τ-MnAl from diffraction peaks, and keep notes on what to try next.

FastAPI + React. MongoDB if you have it; otherwise it runs fine in local memory mode.

## Try the demo

1. Start backend and frontend (see below)
2. Open http://localhost:3000
3. Click **Try live demo** — three example MnAl samples with synthetic curves
4. Login: `demo@elementx.dev` / `demo2026`

No database required for the demo. Add `MONGODB_URI` to `backend/.env` when you want data to stick around.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# backend/.env
# MONGODB_URI=...          # optional
# JWT_SECRET=...
# GEMINI_API_KEY=...       # optional — for chat + brief text generation

uvicorn main:app --reload
```

```bash
cd frontend
npm install
npm start
```

API docs: http://localhost:8000/docs

## Features

- Sample database (create, edit, link XRD/VSM uploads)
- τ-MnAl phase check from peak positions
- Stoichiometry calculator
- Bragg lattice estimate, Scherrer grain size, BHmax from hysteresis
- Dopant ranker — rules-based, uses outcome labels you set on samples
- Lab chat tab — ask questions about your data, upload files inline
- Synthesis note parser (structured JSON from notebook text)
- Experiment brief export (markdown)

## API (samples)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/samples` | Create sample |
| GET | `/api/samples` | List your samples |
| GET | `/api/samples/{id}` | Sample + linked XRD/VSM |
| PATCH | `/api/samples/{id}` | Update synthesis, status, outcome |
| DELETE | `/api/samples/{id}` | Delete sample |
| POST | `/api/samples/{id}/recommend` | Rank next alloy / dopant to try |
| POST | `/api/samples/{id}/experiment-brief` | Markdown brief for one sample |

## API (analysis helpers)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ai/status` | Text generation available or not |
| POST | `/api/ai/parse-synthesis` | Notebook text → JSON |
| POST | `/api/ai/copilot` | Q&A over your sample list |
| POST | `/api/agent/chat` | Chat with calculators + ranker wired in |

Set `outcomeLabel` to `success`, `partial`, or `fail` on a sample (PATCH) so the ranker has something to learn from.

## Project layout

```
backend/
  main.py              FastAPI app
  routers/             samples, demo, analysis routes
  services/            parsers, phase check, ranker, calculators
frontend/
  src/App.js           main UI
  src/components/Plots.js   XRD + M-H charts
```

## Still on my list

- [ ] Import real MnAl C-doping history from the lab
- [ ] NOVAMAG reference lookup
- [ ] Better phase ID than peak matching

## Author

Manish Neupane — SDSU (CS + Physics)
