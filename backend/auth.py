import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import SECRET_KEY

security = HTTPBearer()


async def verify_token(cred: HTTPAuthorizationCredentials = Depends(security)):
    try:
        return jwt.decode(cred.credentials, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


async def current_owner_id(claims: dict = Depends(verify_token)) -> str:
    """Server-side identity for ownership: the verified JWT ``userId`` claim only."""
    user_id = claims.get("userId")
    if not isinstance(user_id, str) or not user_id.strip():
        raise HTTPException(401, "Invalid token")
    return user_id
