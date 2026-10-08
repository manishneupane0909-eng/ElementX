import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import SECRET_KEY
from services.production_config import is_production

security = HTTPBearer()
_optional_security = HTTPBearer(auto_error=False)


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


async def require_auth_in_production(
    cred: HTTPAuthorizationCredentials | None = Depends(_optional_security),
):
    """Access control for stateless scientific endpoints.

    The Vite client always sends its JWT. In production these endpoints (which spend
    Materials Project quota or CPU) require a valid token; in local development they
    stay open so scripts and tests keep working.
    """
    if not is_production():
        return None
    if cred is None:
        raise HTTPException(401, "Not authenticated")
    return await verify_token(cred)
