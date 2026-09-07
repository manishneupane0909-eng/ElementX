from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import bcrypt
import jwt
import os
import numpy as np
from scipy.signal import find_peaks
from datetime import datetime, timedelta
from typing import Optional, List
import re
from dotenv import load_dotenv
from pathlib import Path
from uuid import uuid4

# Load repo-root .env when uvicorn is started from backend/
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()

from services.materials_client import (
    MaterialsClient,
    MaterialsAPIKeyError,
    MaterialsClientError,
    MaterialsNotFoundError,
    FormulaQueryResult,
)
from services.cif_parser import parse_cif_bytes, CifParserError, CifParseResult
from services.physics_engine import evaluate_permanent_magnet
from services.parsers.quantum_design import (
    QuantumDesignParseError,
    is_quantum_design_dat,
)
from services.magnetometry import MagnetometrySegmentationError
from services.hysteresis import HysteresisAnalysisError
from services.saturation import SaturationAnalysisError
from services.sample_provenance import SampleProvenanceError
from services.mh_analysis import MHAnalysisError
from services.magnetometry_analysis import analyze_quantum_design_magnetometry

app = FastAPI(title="ElementX Material Science Magnet Analytics API")

VITE_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=VITE_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI") or "mongodb://localhost:27017/elementx"
client = AsyncIOMotorClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
)
try:
    db = client.get_default_database()
except Exception:
    db = client["elementx"]

# MongoDB is OPTIONAL. If it's unreachable, we fall back to an in-memory store.
DB_AVAILABLE = False
_LOCAL_USERS_BY_EMAIL = {}  # email -> user dict with "_id" and "password" (bcrypt hash)

security = HTTPBearer()
SECRET_KEY = os.getenv("JWT_SECRET", "superlongrandomkey1234567890")

@app.on_event("startup")
async def _startup_check_db():
    # Best-effort connectivity check so failures are obvious.
    global DB_AVAILABLE
    try:
        await client.admin.command("ping")
        DB_AVAILABLE = True
        print("MongoDB: connected")
    except Exception as e:
        DB_AVAILABLE = False
        print(f"MongoDB: NOT connected ({type(e).__name__}: {e})")


class UserIn(BaseModel):
    name: str
    institution: Optional[str] = None
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class FormulaQueryRequest(BaseModel):
    formula: str = Field(..., min_length=1, examples=["Nd2Fe14B"])


class AnalyzeMagnetRequest(BaseModel):
    formula: str = Field(..., min_length=1, examples=["Nd2Fe14B"])
    magnetic_moment: Optional[float] = Field(
        None,
        description="Total magnetic moment in μB/f.u. Omit to fetch from Materials Project.",
    )
    volume: Optional[float] = Field(
        None,
        gt=0,
        description="Unit-cell volume in Å³. Omit to fetch from Materials Project.",
    )
    formula_units_per_cell: int = Field(
        1,
        ge=1,
        description="Number of formula units Z in the unit cell (e.g. 8 for Nd2Fe14B).",
    )
    fetch_from_materials_project: bool = Field(
        True,
        description="When true, missing magnetic_moment or volume are fetched from MP.",
    )


class CriticalityBreakdownItem(BaseModel):
    element: str
    stoichiometry: float
    mole_fraction: float
    element_criticality: float
    contribution: float


class HighRiskComponent(BaseModel):
    element: str
    mole_fraction: float
    element_criticality: float
    contribution: float


class CriticalityResult(BaseModel):
    formula: str
    total_score: float
    risk_level: str
    high_risk_components: List[HighRiskComponent]
    element_breakdown: List[CriticalityBreakdownItem]


class TheoreticalLimitsResult(BaseModel):
    magnetic_moment_mu_b_per_fu: float
    unit_cell_volume_angstrom3: float
    formula_units_per_cell: int
    magnetization_a_per_m: float
    saturation_magnetization_tesla: float
    bhmax_j_m3: float
    bhmax_kj_m3: float
    bhmax_mgoe: float
    assumptions: dict


class AnalyzeMagnetResult(BaseModel):
    formula: str
    material_id: Optional[str] = None
    magnetic_ordering: Optional[str] = None
    criticality: CriticalityResult
    theoretical_limits: Optional[TheoreticalLimitsResult] = None
    data_sources: dict


materials_client = MaterialsClient()


async def verify_token(cred: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(cred.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    except Exception as e:
        raise HTTPException(401, f"Authentication error: {str(e)}")


@app.post("/api/auth/register")
async def register(user: UserIn):
    try:
        if DB_AVAILABLE:
            if await db.users.find_one({"email": user.email}):
                raise HTTPException(400, "Email already registered")

            hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
            result = await db.users.insert_one({
                "name": user.name,
                "institution": user.institution,
                "email": user.email,
                "password": hashed,
                "createdAt": datetime.utcnow()
            })
            user_id = str(result.inserted_id)
        else:
            if user.email in _LOCAL_USERS_BY_EMAIL:
                raise HTTPException(400, "Email already registered")

            user_id = str(uuid4())
            hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
            _LOCAL_USERS_BY_EMAIL[user.email] = {
                "_id": user_id,
                "name": user.name,
                "institution": user.institution,
                "email": user.email,
                "password": hashed,
                "createdAt": datetime.utcnow(),
            }

        token = jwt.encode({
            "userId": user_id,
            "email": user.email,
            "exp": datetime.utcnow() + timedelta(days=7)
        }, SECRET_KEY, algorithm="HS256")

        return {
            "message": "Success",
            "token": token,
            "user": {
                "id": user_id,
                "email": user.email,
                "name": user.name
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Registration error: {str(e)}")
        raise HTTPException(500, f"Registration failed: {str(e)}")


@app.post("/api/auth/login")
async def login(data: LoginRequest):
    try:
        if DB_AVAILABLE:
            user = await db.users.find_one({"email": data.email})
        else:
            user = _LOCAL_USERS_BY_EMAIL.get(data.email)

        if not user:
            raise HTTPException(401, "Invalid credentials")

        if not bcrypt.checkpw(data.password.encode(), user["password"]):
            raise HTTPException(401, "Invalid credentials")

        user_id = str(user["_id"])
        token = jwt.encode({
            "userId": user_id,
            "email": user["email"],
            "exp": datetime.utcnow() + timedelta(days=7)
        }, SECRET_KEY, algorithm="HS256")

        return {
            "message": "Login successful",
            "token": token,
            "user": {
                "id": user_id,
                "email": user["email"],
                "name": user["name"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(500, f"Login failed: {str(e)}")


def parse_raw_file(text: str):
    lines = text.splitlines()
    data = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith(('#', ';', '*', '!', '%')):
            continue
        if any(keyword in line.lower() for keyword in
               ['theta', 'angle', 'field', 'moment', 'temp', 'intensity', 'header', 'scan']):
            continue
        values = re.split(r'[\s+,;]+', line)
        values = [v.strip() for v in values if v.strip()]
        if len(values) >= 2:
            try:
                x = float(values[0])
                y = float(values[1])
                data.append((x, y))
            except ValueError:
                continue
    return data


@app.post("/api/xrd/upload")
async def upload_xrd(
        file: UploadFile = File(...),
        sampleId: Optional[str] = Form(None),
        notes: Optional[str] = Form(None),
        user=Depends(verify_token)
):
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        points = parse_raw_file(text)

        print(f"XRD DEBUG: Parsed {len(points)} points from {file.filename}")

        if len(points) < 5:
            raise HTTPException(400,
                                "File contains no valid numeric data. Make sure it has at least two columns of numbers (angle vs intensity).")

        angles = np.array([p[0] for p in points])
        intensities = np.array([p[1] for p in points])
        peaks, _ = find_peaks(intensities, prominence=0.02 * intensities.max(), distance=10)
        peak_list = [{"angle": float(angles[i]), "intensity": float(intensities[i])} for i in peaks]

        inserted_id = None
        if DB_AVAILABLE:
            result = await db.xrd.insert_one({
                "userId": user["userId"],
                "sampleId": sampleId,
                "filename": file.filename,
                "data": [{"angle": float(p[0]), "intensity": float(p[1])} for p in points],
                "peaks": peak_list,
                "notes": notes,
                "createdAt": datetime.utcnow()
            })
            inserted_id = str(result.inserted_id)

        return {"success": True, "points": len(points), "peaks": len(peaks), "id": inserted_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"XRD upload error: {str(e)}")
        raise HTTPException(500, f"XRD upload failed: {str(e)}")


@app.post("/api/magnetic/upload")
async def upload_magnetic(
        file: UploadFile = File(...),
        measurementType: str = Form("M-H"),
        sampleId: Optional[str] = Form(None),
        notes: Optional[str] = Form(None),
        user=Depends(verify_token)
):
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        points = parse_raw_file(text)

        print(f"MAGNETIC DEBUG: Parsed {len(points)} points from {file.filename}")

        if len(points) < 5:
            raise HTTPException(400,
                                "File contains no valid numeric data. Make sure it has at least two columns (field/temp vs moment).")

        x_vals = np.array([p[0] for p in points])
        y_vals = np.array([p[1] for p in points])

        props = {
            "Ms": float(np.max(np.abs(y_vals))),
            "Mr": float(np.abs(np.interp(0, x_vals, y_vals))) if np.any(np.diff(np.sign(x_vals))) else 0.0,
            "Hc": float(np.abs(np.interp(0, y_vals, x_vals))) if np.any(np.diff(np.sign(y_vals))) else 0.0
        }

        inserted_id = None
        if DB_AVAILABLE:
            result = await db.magnetic.insert_one({
                "userId": user["userId"],
                "sampleId": sampleId,
                "filename": file.filename,
                "measurementType": measurementType,
                "data": [{"x": float(p[0]), "y": float(p[1])} for p in points],
                "properties": props,
                "notes": notes,
                "createdAt": datetime.utcnow()
            })
            inserted_id = str(result.inserted_id)

        return {"success": True, "points": len(points), "properties": props, "id": inserted_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Magnetic upload error: {str(e)}")
        raise HTTPException(500, f"Magnetic upload failed: {str(e)}")


@app.post("/api/query-formula", response_model=FormulaQueryResult)
def query_formula(body: FormulaQueryRequest):
    """Query Materials Project for structural symmetry and magnetic properties by formula."""
    try:
        return materials_client.query_formula(body.formula)
    except MaterialsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MaterialsAPIKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MaterialsClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Formula query failed: {exc}") from exc


@app.post("/api/analyze-magnet", response_model=AnalyzeMagnetResult)
def analyze_magnet(body: AnalyzeMagnetRequest):
    """
    Evaluate supply-chain criticality and theoretical magnet performance limits.

    Fetches magnetic moment and unit-cell volume from Materials Project when
    not supplied, then runs the physics engine criticality and (BH)max models.
    """
    magnetic_moment = body.magnetic_moment
    volume = body.volume
    material_id: Optional[str] = None
    magnetic_ordering: Optional[str] = None
    data_sources: dict = {"materials_project": False}

    needs_mp = body.fetch_from_materials_project and (
        magnetic_moment is None or volume is None
    )

    if needs_mp:
        try:
            mp_result = materials_client.query_formula(body.formula)
        except MaterialsNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MaterialsAPIKeyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except MaterialsClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        material_id = mp_result.material_id
        magnetic_ordering = mp_result.magnetic_ordering
        data_sources["materials_project"] = True
        data_sources["material_id"] = material_id

        if magnetic_moment is None:
            magnetic_moment = mp_result.total_magnetic_moment
            data_sources["magnetic_moment_source"] = "materials_project"
        else:
            data_sources["magnetic_moment_source"] = "request"

        if volume is None:
            volume = mp_result.unit_cell_volume
            data_sources["volume_source"] = "materials_project"
        else:
            data_sources["volume_source"] = "request"
    else:
        data_sources["magnetic_moment_source"] = "request" if magnetic_moment is not None else None
        data_sources["volume_source"] = "request" if volume is not None else None

    try:
        evaluation = evaluate_permanent_magnet(
            formula=body.formula,
            magnetic_moment=magnetic_moment,
            volume=volume,
            formula_units_per_cell=body.formula_units_per_cell,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if evaluation["theoretical_limits"] is None:
        missing = []
        if magnetic_moment is None:
            missing.append("magnetic_moment")
        if volume is None:
            missing.append("volume")
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot compute theoretical limits; missing: {', '.join(missing)}. "
                "Provide values in the request or enable Materials Project fetch with a valid MP_API_KEY."
            ),
        )

    return AnalyzeMagnetResult(
        formula=evaluation["formula"],
        material_id=material_id,
        magnetic_ordering=magnetic_ordering,
        criticality=evaluation["criticality"],
        theoretical_limits=evaluation["theoretical_limits"],
        data_sources=data_sources,
    )


@app.post("/api/parse-cif", response_model=CifParseResult)
async def parse_cif(file: UploadFile = File(...)):
    """Parse an uploaded CIF file and return lattice, symmetry, and density."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="A CIF filename is required.")

    if not file.filename.lower().endswith(".cif"):
        raise HTTPException(status_code=400, detail="Only .cif files are supported.")

    try:
        content = await file.read()
        return parse_cif_bytes(content, filename=file.filename)
    except CifParserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CIF parsing failed: {exc}") from exc


@app.post("/api/magnetometry/analyze")
async def analyze_magnetometry_dat(
    file: UploadFile = File(...),
    user_confirmed_mass_mg: Optional[float] = Form(None),
):
    """Analyze a Quantum Design / VersaLab .DAT magnetometry file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="A .dat filename is required.")

    if not file.filename.lower().endswith(".dat"):
        raise HTTPException(status_code=400, detail="Only .dat files are supported.")

    try:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")

        if not is_quantum_design_dat(text):
            raise HTTPException(
                status_code=400,
                detail="This is not a recognized Quantum Design .DAT file.",
            )

        return analyze_quantum_design_magnetometry(
            text,
            filename=file.filename,
            user_confirmed_mass_mg=user_confirmed_mass_mg,
        )
    except HTTPException:
        raise
    except QuantumDesignParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MagnetometrySegmentationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HysteresisAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SaturationAnalysisError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SampleProvenanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MHAnalysisError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Magnetometry analysis failed: {exc}",
        ) from exc


@app.get("/health")
def health():
    return {
        "status": "ElementX Material Science Magnet Analytics backend",
        "backend": "Python + FastAPI",
        "materials_project_configured": bool(
            os.getenv("MP_API_KEY") or os.getenv("MATERIALS_PROJECT_API_KEY")
        ),
    }


@app.get("/")
def root():
    return {
        "message": "ElementX API is running",
        "version": "2.0",
        "endpoints": {
            "query_formula": "POST /api/query-formula",
            "parse_cif": "POST /api/parse-cif",
            "analyze_magnet": "POST /api/analyze-magnet",
        },
    }


print("ElementX Python Backend – FINAL VERSION LOADED")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)