import bcrypt
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import database
import local_store
from auth import verify_token
from services.demo_data import DEMO_EMAIL, DEMO_PASSWORD, DEMO_NAME
from services.demo_loader import seed_demo_lab

router = APIRouter(prefix="/api/demo", tags=["demo"])


class DemoLoadRequest(BaseModel):
    force: bool = False


@router.post("/load")
async def load_demo(payload: DemoLoadRequest = DemoLoadRequest(), user=Depends(verify_token)):
    try:
        return await seed_demo_lab(user["userId"], force=payload.force)
    except Exception as e:
        raise HTTPException(500, f"Demo load failed: {e}") from e


@router.post("/bootstrap")
async def bootstrap_demo_account():
    """Create or reset the shared demo login (no auth required). Works with or without MongoDB."""
    hashed = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt())

    if database.DB_AVAILABLE:
        existing = await database.db.users.find_one({"email": DEMO_EMAIL})
        if existing:
            user_id = str(existing["_id"])
            await database.db.users.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "name": DEMO_NAME,
                        "institution": "ElementX Demo Lab",
                        "password": hashed,
                    }
                },
            )
        else:
            result = await database.db.users.insert_one(
                {
                    "name": DEMO_NAME,
                    "institution": "ElementX Demo Lab",
                    "email": DEMO_EMAIL,
                    "password": hashed,
                    "createdAt": datetime.utcnow(),
                }
            )
            user_id = str(result.inserted_id)
    else:
        user_id = "demo-local-user"
        local_store.upsert_local_user(
            DEMO_EMAIL,
            {
                "_id": user_id,
                "name": DEMO_NAME,
                "institution": "ElementX Demo Lab",
                "email": DEMO_EMAIL,
                "password": hashed,
                "createdAt": datetime.utcnow(),
            },
        )

    demo = await seed_demo_lab(user_id, force=True)

    return {
        "success": True,
        "email": DEMO_EMAIL,
        "password": DEMO_PASSWORD,
        "userId": user_id,
        **demo,
    }
