from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
import bcrypt
import jwt
import numpy as np
from scipy.signal import find_peaks
from datetime import datetime, timedelta
from typing import Optional, List
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

import database
import local_store
from auth import verify_token
from routers.samples import router as samples_router
from routers.ai import router as ai_router
from routers.demo import router as demo_router
from routers.agent import router as agent_router
from services.parsers import parse_raw_file
from services.phase_detector import detect_tau_mnal
from services.llm_client import llm_available

# database.py loads backend/.env; the repo-root .env is a fallback for keys such as MP_API_KEY.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

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

app = FastAPI(title="ElementX v2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(samples_router)
app.include_router(ai_router)
app.include_router(demo_router)
app.include_router(agent_router)

_LOCAL_USERS_BY_EMAIL = local_store._LOCAL_USERS_BY_EMAIL  # noqa: SLF001


@app.on_event("startup")
async def _startup_check_db():
    global DB_AVAILABLE
    try:
        await database.client.admin.command("ping")
        database.DB_AVAILABLE = True
        print("MongoDB: connected")
    except Exception as e:
        database.DB_AVAILABLE = False
        print(f"MongoDB: NOT connected ({type(e).__name__}: {e})")


class UserIn(BaseModel):
    name: str
    institution: Optional[str] = None
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _encode_token(user_id: str, email: str) -> str:
    return jwt.encode(
        {
            "userId": user_id,
            "email": email,
            "exp": datetime.utcnow() + timedelta(days=7),
        },
        database.SECRET_KEY,
        algorithm="HS256",
    )


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


@app.post("/api/auth/register")
async def register(user: UserIn):
    try:
        if database.DB_AVAILABLE:
            if await database.db.users.find_one({"email": user.email}):
                raise HTTPException(400, "Email already registered")

            hashed = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt())
            result = await database.db.users.insert_one(
                {
                    "name": user.name,
                    "institution": user.institution,
                    "email": user.email,
                    "password": hashed,
                    "createdAt": datetime.utcnow(),
                }
            )
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

        token = _encode_token(user_id, user.email)
        return {
            "message": "Success",
            "token": token,
            "user": {"id": user_id, "email": user.email, "name": user.name},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Registration failed: {str(e)}")


@app.post("/api/auth/login")
async def login(data: LoginRequest):
    try:
        if database.DB_AVAILABLE:
            user = await database.db.users.find_one({"email": data.email})
        else:
            user = _LOCAL_USERS_BY_EMAIL.get(data.email)

        if not user or not bcrypt.checkpw(data.password.encode(), user["password"]):
            raise HTTPException(401, "Invalid credentials")

        user_id = str(user["_id"])
        token = _encode_token(user_id, user["email"])
        return {
            "message": "Login successful",
            "token": token,
            "user": {"id": user_id, "email": user["email"], "name": user["name"]},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Login failed: {str(e)}")


async def _attach_xrd_to_sample(sample_id: str, user_id: str, summary: dict):
    if database.DB_AVAILABLE:
        if not ObjectId.is_valid(sample_id):
            return
        sample = await database.db.samples.find_one(
            {"_id": ObjectId(sample_id), "userId": user_id}
        )
        if not sample:
            return
        phase_analysis = (
            detect_tau_mnal(summary["peaks"])
            if sample.get("materialFamily") == "mnal_tau"
            else None
        )
        await database.db.samples.update_one(
            {"_id": ObjectId(sample_id)},
            {
                "$set": {
                    "characterization.xrd": summary,
                    "phaseAnalysis": phase_analysis,
                    "status": "characterized",
                    "updatedAt": datetime.utcnow(),
                }
            },
        )
        return

    sample = local_store.get_raw_sample(sample_id, user_id)
    if not sample:
        return
    phase_analysis = (
        detect_tau_mnal(summary["peaks"])
        if sample.get("materialFamily") == "mnal_tau"
        else None
    )
    local_store.update_sample(
        sample_id,
        user_id,
        {
            "characterization": {
                **(sample.get("characterization") or {}),
                "xrd": summary,
            },
            "phaseAnalysis": phase_analysis,
            "status": "characterized",
        },
    )


async def _attach_magnetic_to_sample(sample_id: str, user_id: str, summary: dict):
    if database.DB_AVAILABLE:
        if not ObjectId.is_valid(sample_id):
            return
        sample = await database.db.samples.find_one(
            {"_id": ObjectId(sample_id), "userId": user_id}
        )
        if not sample:
            return
        await database.db.samples.update_one(
            {"_id": ObjectId(sample_id)},
            {
                "$set": {
                    "characterization.magnetic": summary,
                    "status": "characterized",
                    "updatedAt": datetime.utcnow(),
                }
            },
        )
        return

    sample = local_store.get_raw_sample(sample_id, user_id)
    if not sample:
        return
    local_store.update_sample(
        sample_id,
        user_id,
        {
            "characterization": {
                **(sample.get("characterization") or {}),
                "magnetic": summary,
            },
            "status": "characterized",
        },
    )


@app.post("/api/xrd/upload")
async def upload_xrd(
    file: UploadFile = File(...),
    sampleId: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user=Depends(verify_token),
):
    try:
        text = (await file.read()).decode("utf-8", errors="ignore")
        points = parse_raw_file(text)

        if len(points) < 5:
            raise HTTPException(
                400,
                "File contains no valid numeric data. Expected angle vs intensity columns.",
            )

        angles = np.array([p[0] for p in points])
        intensities = np.array([p[1] for p in points])
        peaks, _ = find_peaks(intensities, prominence=0.02 * intensities.max(), distance=10)
        peak_list = [
            {"angle": float(angles[i]), "intensity": float(intensities[i])} for i in peaks
        ]

        inserted_id = None
        if database.DB_AVAILABLE:
            result = await database.db.xrd.insert_one(
                {
                    "userId": user["userId"],
                    "sampleId": sampleId,
                    "filename": file.filename,
                    "data": [{"angle": float(p[0]), "intensity": float(p[1])} for p in points],
                    "peaks": peak_list,
                    "notes": notes,
                    "createdAt": datetime.utcnow(),
                }
            )
            inserted_id = str(result.inserted_id)

            if sampleId:
                await _attach_xrd_to_sample(
                    sampleId,
                    user["userId"],
                    {
                        "id": inserted_id,
                        "filename": file.filename,
                        "peaks": peak_list,
                        "pointCount": len(points),
                        "uploadedAt": datetime.utcnow().isoformat(),
                    },
                )
        else:
            inserted_id = local_store.insert_xrd(
                user["userId"],
                sampleId,
                {
                    "filename": file.filename,
                    "data": [{"angle": float(p[0]), "intensity": float(p[1])} for p in points],
                    "peaks": peak_list,
                    "notes": notes,
                    "createdAt": datetime.utcnow(),
                },
            )
            if sampleId:
                await _attach_xrd_to_sample(
                    sampleId,
                    user["userId"],
                    {
                        "id": inserted_id,
                        "filename": file.filename,
                        "peaks": peak_list,
                        "pointCount": len(points),
                        "uploadedAt": datetime.utcnow().isoformat(),
                    },
                )

        phase_analysis = detect_tau_mnal(peak_list)
        curve_data = [{"angle": float(p[0]), "intensity": float(p[1])} for p in points]
        return {
            "success": True,
            "points": len(points),
            "peaks": peak_list,
            "peakCount": len(peaks),
            "id": inserted_id,
            "filename": file.filename,
            "data": curve_data,
            "phaseAnalysis": phase_analysis,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"XRD upload failed: {str(e)}")


@app.post("/api/magnetic/upload")
async def upload_magnetic(
    file: UploadFile = File(...),
    measurementType: str = Form("M-H"),
    sampleId: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    user=Depends(verify_token),
):
    try:
        text = (await file.read()).decode("utf-8", errors="ignore")
        points = parse_raw_file(text)

        if len(points) < 5:
            raise HTTPException(
                400,
                "File contains no valid numeric data. Expected field/temp vs moment columns.",
            )

        x_vals = np.array([p[0] for p in points])
        y_vals = np.array([p[1] for p in points])

        props = {
            "Ms": float(np.max(np.abs(y_vals))),
            "Mr": float(np.abs(np.interp(0, x_vals, y_vals))) if np.any(np.diff(np.sign(x_vals))) else 0.0,
            "Hc": float(np.abs(np.interp(0, y_vals, x_vals))) if np.any(np.diff(np.sign(y_vals))) else 0.0,
        }

        inserted_id = None
        if database.DB_AVAILABLE:
            result = await database.db.magnetic.insert_one(
                {
                    "userId": user["userId"],
                    "sampleId": sampleId,
                    "filename": file.filename,
                    "measurementType": measurementType,
                    "data": [{"x": float(p[0]), "y": float(p[1])} for p in points],
                    "properties": props,
                    "notes": notes,
                    "createdAt": datetime.utcnow(),
                }
            )
            inserted_id = str(result.inserted_id)

            if sampleId:
                await _attach_magnetic_to_sample(
                    sampleId,
                    user["userId"],
                    {
                        "id": inserted_id,
                        "filename": file.filename,
                        "measurementType": measurementType,
                        "properties": props,
                        "uploadedAt": datetime.utcnow().isoformat(),
                    },
                )
        else:
            inserted_id = local_store.insert_magnetic(
                user["userId"],
                sampleId,
                {
                    "filename": file.filename,
                    "measurementType": measurementType,
                    "data": [{"x": float(p[0]), "y": float(p[1])} for p in points],
                    "properties": props,
                    "notes": notes,
                    "createdAt": datetime.utcnow(),
                },
            )
            if sampleId:
                await _attach_magnetic_to_sample(
                    sampleId,
                    user["userId"],
                    {
                        "id": inserted_id,
                        "filename": file.filename,
                        "measurementType": measurementType,
                        "properties": props,
                        "uploadedAt": datetime.utcnow().isoformat(),
                    },
                )

        curve_data = [{"x": float(p[0]), "y": float(p[1])} for p in points]
        return {
            "success": True,
            "points": len(points),
            "properties": props,
            "id": inserted_id,
            "filename": file.filename,
            "measurementType": measurementType,
            "data": curve_data,
        }
    except HTTPException:
        raise
    except Exception as e:
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
        "status": "ok",
        "version": "2.0.0",
        "mongodb": database.DB_AVAILABLE,
        "localMode": not database.DB_AVAILABLE,
        "aiLlm": llm_available(),
        "materials_project_configured": bool(
            os.getenv("MP_API_KEY") or os.getenv("MATERIALS_PROJECT_API_KEY")
        ),
    }


@app.get("/")
def root():
    return {
        "message": "ElementX v2 API",
        "version": "2.0.0",
        "science_endpoints": {
            "query_formula": "POST /api/query-formula",
            "parse_cif": "POST /api/parse-cif",
            "analyze_magnet": "POST /api/analyze-magnet",
            "magnetometry_analyze": "POST /api/magnetometry/analyze",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
