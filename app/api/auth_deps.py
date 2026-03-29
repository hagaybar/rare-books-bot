"""FastAPI dependencies for authentication and authorization."""
from fastapi import Request, HTTPException, status

from app.api.auth_service import validate_access_token

ROLE_HIERARCHY = {"admin": 4, "full": 3, "limited": 2, "guest": 1}


def get_current_user(request: Request) -> dict:
    """Extract and validate JWT from cookie. Returns user payload."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = validate_access_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return payload


def require_role(minimum_role: str):
    """Factory that returns a dependency requiring a minimum role level."""
    min_level = ROLE_HIERARCHY.get(minimum_role, 0)

    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        user_level = ROLE_HIERARCHY.get(user.get("role", ""), 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role} role or higher",
            )
        return user

    return dependency
