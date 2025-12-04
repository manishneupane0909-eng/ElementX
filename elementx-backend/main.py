from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
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

# ====================== FASTAPI SETUP ======================
app = FastAPI(title="ElementX Python Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Changed from localhost only - adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====================== DATABASE ======================
client = AsyncIOMotorClient(
    os.getenv("MONGODB_URI", "mongodb+srv://elemntx:elementx123@elementx.8jn92ay.mongodb.net/elementx"))
db = client.elementx

# ====================== AUTH ======================
security = HTTPBearer()
SECRET_KEY = os.getenv("JWT_SECRET", "superlongrandomkey1234567890")


class UserIn(BaseModel):
    name: str
    institution: Optional[str] = None
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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

        token = jwt.encode({
            "userId": str(result.inserted_id),
            "email": user.email,
            "exp": datetime.utcnow() + timedelta(days=7)
        }, SECRET_KEY, algorithm="HS256")

        return {
            "message": "Success",
            "token": token,
            "user": {
                "id": str(result.inserted_id),
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
        user = await db.users.find_one({"email": data.email})
        if not user:
            raise HTTPException(401, "Invalid credentials")

        if not bcrypt.checkpw(data.password.encode(), user["password"]):
            raise HTTPException(401, "Invalid credentials")

        token = jwt.encode({
            "userId": str(user["_id"]),
            "email": user["email"],
            "exp": datetime.utcnow() + timedelta(days=7)
        }, SECRET_KEY, algorithm="HS256")

        return {
            "message": "Login successful",
            "token": token,
            "user": {
                "id": str(user["_id"]),
                "email": user["email"],
                "name": user["name"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login error: {str(e)}")
        raise HTTPException(500, f"Login failed: {str(e)}")


# ====================== SUPER ROBUST PARSER ======================
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
        # Split by any whitespace or comma
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


# ====================== XRD UPLOAD ======================
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

        result = await db.xrd.insert_one({
            "userId": user["userId"],
            "sampleId": sampleId,
            "filename": file.filename,
            "data": [{"angle": float(p[0]), "intensity": float(p[1])} for p in points],
            "peaks": peak_list,
            "notes": notes,
            "createdAt": datetime.utcnow()
        })

        return {"success": True, "points": len(points), "peaks": len(peaks), "id": str(result.inserted_id)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"XRD upload error: {str(e)}")
        raise HTTPException(500, f"XRD upload failed: {str(e)}")


# ====================== MAGNETIC UPLOAD ======================
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

        return {"success": True, "points": len(points), "properties": props, "id": str(result.inserted_id)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Magnetic upload error: {str(e)}")
        raise HTTPException(500, f"Magnetic upload failed: {str(e)}")


# ====================== HEALTH ======================
@app.get("/health")
def health():
    return {"status": "ElementX Python backend – FULLY WORKING", "backend": "Python + FastAPI + Deep Learning Ready"}


@app.get("/")
def root():
    return {"message": "ElementX API is running", "version": "1.0"}


print("ElementX Python Backend – FINAL VERSION LOADED")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)