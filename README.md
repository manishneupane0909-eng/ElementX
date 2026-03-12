# ElementX

A full-stack research platform that automates the tedious parts of materials science lab work - so researchers can focus on discovery, not data processing.

<img width="1445" height="486" alt="Screenshot 2026-03-11 at 7 49 44 PM" src="https://github.com/user-attachments/assets/903e989d-3ced-45ad-ba24-634586c8853b" />
<img width="1408" height="612" alt="Screenshot 2026-03-11 at 7 50 06 PM" src="https://github.com/user-attachments/assets/34bbb19b-ec51-44b1-990d-4647bf840063" />


## The Problem

As a materials science researcher, I found myself spending hours on repetitive tasks every week:

- Manually calculating stoichiometric masses for compound synthesis
- Hand-picking XRD peaks from noisy diffraction data
- Copy-pasting M-H loop values into spreadsheets to extract magnetic properties

ElementX automates all of it - and saves your work to your account so nothing gets lost between sessions.

## Features

| Feature | Description |
| --- | --- |
| Stoichiometry Calculator | Input a chemical formula (e.g. Fe2MoGe), a target element, and mass - get exact synthesis masses for every element |
| XRD Peak Detection | Upload raw diffraction data; SciPy automatically detects peaks using prominence thresholds |
| Magnetic Property Extractor | Upload M-H or M-T loop data and instantly get Ms, Hc, and Mr values |
| User Accounts | JWT-authenticated accounts with MongoDB persistence - all your calculations are saved |

## Tech Stack

**Backend**

- FastAPI - async Python web framework
- MongoDB + Motor - async NoSQL database driver
- NumPy / SciPy - scientific computing and peak detection
- JWT - stateless authentication

**Frontend**

- React 18 - component-based UI
- Lucide Icons - clean iconography
- Custom REST API client

**Infrastructure**

- Docker Compose - local development

## Getting Started

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone the repo
git clone https://github.com/manishneupane0909-eng/ElementX.git
cd ElementX

# 2. Create your environment file
cp .env.example .env
# Edit .env with your MongoDB URI and JWT secret

# 3. Start everything
docker-compose up -d

# 4. Open the app
open http://localhost:3000
```

### Option 2: Manual Setup

**Backend**

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload      # Runs on http://localhost:8000
```

**Frontend**

```bash
cd frontend
npm install
npm start                      # Runs on http://localhost:3000
```

## Environment Variables

Create a `.env` file in the root directory:

```env
MONGODB_URI=your_mongodb_connection_string
JWT_SECRET=your_secret_key
REACT_APP_API_URL=http://localhost:8000   # Change to your API URL in production
```

## Project Structure

```
ElementX/
├── backend/
│   ├── main.py              # FastAPI app and route definitions
│   └── requirements.txt
├── frontend/
│   ├── src/                 # React components and API client
│   └── package.json
└── docker-compose.yml       # Multi-container orchestration
```

## How It Works

### XRD Peak Detection

Raw `.txt` files with angle vs. intensity columns are parsed by the backend (handling whitespace, comma-separated, and commented formats). SciPy's `find_peaks` applies a prominence threshold based on max intensity to identify meaningful diffraction peaks - filtering out noise automatically.

### Magnetic Property Extraction

M-H loop files are parsed and fitted to extract:

- **Ms** - saturation magnetization
- **Hc** - coercive field
- **Mr** - remanent magnetization

All results are tied to the authenticated user's MongoDB document for persistent access.

## Roadmap

- Batch file processing for multiple samples
- Export results to Excel / CSV
- Enhanced data visualization (interactive charts)
- Additional XRD file format support (.xy, .dat, .xrdml)

## About

Built by Manish Neupane - physics and CS researcher at SDSU. This project grew directly out of real frustrations in the materials science lab, where manual data processing was slowing down research on MnBi-based composite magnets and Heusler alloys.

If you work in a materials science lab and find this useful, feel free to open an issue or reach out!
