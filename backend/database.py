import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
# override=True so a stale shell export does not beat backend/.env
load_dotenv(dotenv_path=_ENV_PATH, override=True)

MONGODB_URI = os.getenv("MONGODB_URI") or "mongodb://localhost:27017/elementx"
SECRET_KEY = os.getenv("JWT_SECRET", "superlongrandomkey1234567890")

_PLACEHOLDERS = ("REPLACE_ME", "your_mongodb", "XXXXX", "<db_password>", "<password>")
if any(p in MONGODB_URI for p in _PLACEHOLDERS):
    print(f"WARNING: MONGODB_URI looks like a placeholder. Edit {_ENV_PATH}")
elif not MONGODB_URI.startswith(("mongodb://", "mongodb+srv://")):
    print("WARNING: MONGODB_URI must start with mongodb:// or mongodb+srv://")
else:
    # Safe log: host only, no credentials
    host_hint = MONGODB_URI.split("@")[-1].split("/")[0] if "@" in MONGODB_URI else MONGODB_URI
    print(f"MongoDB URI loaded (host: {host_hint})")

client = AsyncIOMotorClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
)

try:
    db = client.get_default_database()
except Exception:
    db = client["elementx"]

DB_AVAILABLE = False
