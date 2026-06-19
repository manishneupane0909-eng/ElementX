from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId
import bcrypt
import jwt
import numpy as np
from scipy.signal import find_peaks
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

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
        return {
            "success": True,
            "points": len(points),
            "peaks": peak_list,
            "peakCount": len(peaks),
            "id": inserted_id,
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

        return {"success": True, "points": len(points), "properties": props, "id": inserted_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Magnetic upload failed: {str(e)}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "mongodb": database.DB_AVAILABLE,
        "localMode": not database.DB_AVAILABLE,
        "aiLlm": llm_available(),
    }


@app.get("/")
def root():
    return {"message": "ElementX v2 API", "version": "2.0.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
