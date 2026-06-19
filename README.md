# ElementX v2

Open-source discovery loop for **rare-earth-free permanent magnet** research — with **AI dopant ranking, lab copilot, and one-click demo**.

## Show it to someone in 30 seconds

1. Start backend + frontend (see Quick start below)
2. Open **http://localhost:3000**
3. Click **▶ Try live demo (1 click)**
4. You land on **AI Discovery** with 3 MnAl samples, τ-phase flags, and ranked dopant suggestions

Demo login (auto-created): `demo@elementx.dev` / `demo2026`

**Pitch flow:** Sample Database → open **DEMO MnAl-C 5%** → AI Discovery → ask copilot *"Which samples have τ-phase?"* → **Generate experiment brief**

Works **without MongoDB** (local in-memory mode). Connect Atlas in `backend/.env` for persistent storage.

## Location

This project lives separately from the undergraduate research workspace:

```
/Users/nish/Desktop/ElementX-v2
```

## v2 focus (Phase 1)

- MongoDB-backed **Sample** records (MnAl, MnBi, Fe-soft families)
- Link XRD + magnetometry uploads to a sample
- τ-MnAl phase flag from detected XRD peaks
- **AI Discovery**: dopant ranker, lab copilot, synthesis parser, experiment briefs
- **Physics Copilot** (chat agent): one prompt → analyze XRD/VSM, compute lattice (Bragg), crystallite size (Scherrer), (BH)max, rank next experiments, write briefs — powered by free Gemini
- REST API ready for discovery dashboard + NOVAMAG integration

## Quick start

```bash
cd /Users/nish/Desktop/ElementX-v2

# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export MONGODB_URI="your_atlas_uri"   # optional — runs in local mode without it
export JWT_SECRET="your_secret"
export GEMINI_API_KEY="..."           # FREE key: https://aistudio.google.com/apikey
export GEMINI_MODEL="gemini-2.0-flash"
# export OPENAI_API_KEY="sk-..."      # optional alternative LLM
uvicorn main:app --reload

# Frontend (new terminal)
cd frontend
npm install
npm start
```

API docs: http://localhost:8000/docs

## Project structure (v2)

```
ElementX-v2/
├── backend/
│   ├── main.py
│   ├── database.py
│   ├── auth.py
│   ├── models/
│   │   └── sample.py
│   ├── routers/
│   │   ├── samples.py
│   │   └── ai.py
│   └── services/
│       ├── parsers.py
│       ├── phase_detector.py
│       ├── dopant_ranker.py
│       ├── llm_client.py
│       ├── sample_context.py
│       ├── synthesis_parser.py
│       └── experiment_brief.py
└── frontend/
```

## Sample API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/samples` | Create sample |
| GET | `/api/samples` | List your samples |
| GET | `/api/samples/{id}` | Sample + linked XRD/VSM |
| PATCH | `/api/samples/{id}` | Update synthesis/status/outcome |
| DELETE | `/api/samples/{id}` | Delete sample |
| POST | `/api/samples/{id}/recommend` | AI dopant / next-experiment ranker |
| POST | `/api/samples/{id}/experiment-brief` | Generate markdown experiment brief |

## AI API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/ai/status` | LLM availability + feature list |
| POST | `/api/ai/parse-synthesis` | Lab notes → structured synthesis JSON |
| POST | `/api/ai/copilot` | RAG Q&A over your sample database |

Set `outcomeLabel` (`success` / `partial` / `fail`) on samples via PATCH to improve future rankings.

## Roadmap

- [x] Sample CRUD + phase detector stub
- [x] Frontend: sample picker on XRD/VSM tabs
- [x] Sample detail page + AI Discovery tab
- [x] Dopant prioritizer v0 (heuristic ranker + learning loop)
- [ ] Import lab history (MnAl C-doping)
- [ ] NOVAMAG reference panel
- [ ] ML phase classifier + Bayesian dopant optimizer

## Author

Manish Neupane — SDSU (CS + Physics), rare-earth-free magnet research.
