# ElementX

A full-stack materials characterization platform for researchers. Helps with stoichiometry calculations, XRD peak detection, and magnetic property analysis from lab data.

## What it does

- Stoichiometry Calculator: Calculate exact masses needed for compound synthesis
- XRD Analysis: Upload XRD data files and automatically detect peaks using SciPy
- Magnetic Properties: Extract Ms, Hc, Mr from M-H loops
- User Accounts: JWT auth with MongoDB for saving calculations

## Tech Stack

Backend:
- FastAPI (Python)
- MongoDB with Motor (async driver)
- NumPy/SciPy for data processing
- JWT for authentication

Frontend:
- React
- Lucide icons
- Custom API client

## Setup

### Backend

```bash
cd elementx-backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Backend runs on `http://localhost:8000`

### Frontend

```bash
cd ElementX-frontend
npm install
npm start
```

Frontend runs on `http://localhost:3000`

## Environment Variables

Create a `.env` file in `elementx-backend/`:

```
MONGODB_URI=your_mongodb_connection_string
JWT_SECRET=your_secret_key
```

## Features

### Stoichiometry Calculator
Input a chemical formula (like Fe2MoGe), target element and mass, and it calculates all the masses needed.

### XRD Peak Detection
Upload a text file with angle vs intensity data. The backend uses SciPy's `find_peaks` to detect peaks automatically.

### Magnetic Analysis
Upload M-H or M-T data and it extracts:
- Saturation magnetization (Ms)
- Coercivity (Hc)
- Remanence (Mr)

## Notes

- The file parser handles various formats (whitespace, commas, comments)
- Peak detection uses prominence threshold based on max intensity
- All calculations are saved to MongoDB per user

## Future improvements

- Add more file format support
- Better visualization for XRD/Magnetic data
- Export to Excel/CSV
- Batch processing for multiple files

