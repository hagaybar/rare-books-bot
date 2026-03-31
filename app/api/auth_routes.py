"""Auth API routes: login, guest, refresh, me, user CRUD."""
import os
import threading
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response, Depends, status

from app.api.auth_models import (
    LoginRequest, TokenResponse, UserInfo, CreateUserRequest,
    UpdateUserRequest, UserListItem,
)
from app.api.auth_service import (
    authenticate_user, create_access_token, create_guest_token,
    create_refresh_token, validate_refresh_token, revoke_refresh_tokens,
    create_user, audit_log, hash_password,
)
from app.api.auth_deps import require_role, get_current_user
from app.api.auth_db import get_auth_db

router = APIRouter(prefix="/auth", tags=["auth"])

# --- IP-based login rate limiting (N2) ---
_ip_attempts: dict[str, list[float]] = defaultdict(list)
_ip_lock = threading.Lock()
IP_RATE_LIMIT = 10  # max failed attempts per IP
IP_RATE_WINDOW = 900  # 15 minutes in seconds


def _check_ip_rate_limit(ip: str) -> bool:
    """Return True if the IP is allowed to attempt login, False if rate-limited."""
    now = datetime.now().timestamp()
    with _ip_lock:
        attempts = _ip_attempts[ip]
        _ip_attempts[ip] = [t for t in attempts if now - t < IP_RATE_WINDOW]
        return len(_ip_attempts[ip]) < IP_RATE_LIMIT


def _record_ip_failure(ip: str):
    """Record a failed login attempt for the given IP."""
    now = datetime.now().timestamp()
    with _ip_lock:
        _ip_attempts[ip].append(now)

COOKIE_KWARGS = {
    "httponly": True,
    "samesite": "lax",
    "secure": os.environ.get("HTTPS", "").lower() == "true",
    "path": "/",
}


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str | None = None):
    response.set_cookie("access_token", access_token, max_age=900, **COOKIE_KWARGS)  # 15 min
    if refresh_token:
        response.set_cookie("refresh_token", refresh_token, max_age=604800, **COOKIE_KWARGS)  # 7 days


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, response: Response):
    ip = request.client.host if request.client else "unknown"

    # IP-based rate limiting (N2): block after too many failed attempts
    if not _check_ip_rate_limit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )

    user = authenticate_user(body.username, body.password)
    if not user:
        _record_ip_failure(ip)
        audit_log("login_failed", username=body.username, ip_address=ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(user["id"], user["username"], user["role"])
    refresh_token = create_refresh_token(user["id"])
    _set_auth_cookies(response, access_token, refresh_token)

    audit_log("login", user_id=user["id"], username=user["username"], ip_address=ip)
    return TokenResponse(username=user["username"], role=user["role"])


@router.post("/guest")
async def guest_session(response: Response):
    token = create_guest_token()
    response.set_cookie("access_token", token, max_age=86400, **COOKIE_KWARGS)  # 24h
    return {"message": "Guest session created", "role": "guest"}


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")
    user = validate_refresh_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Rotate refresh token: revoke old tokens and issue a new one
    revoke_refresh_tokens(user["user_id"])
    new_refresh = create_refresh_token(user["user_id"])

    access_token = create_access_token(user["user_id"], user["username"], user["role"])
    _set_auth_cookies(response, access_token, new_refresh)
    return {"message": "Token refreshed", "role": user["role"]}


@router.post("/logout")
async def logout(request: Request, response: Response):
    user = get_current_user(request)
    if isinstance(user.get("user_id"), int):
        revoke_refresh_tokens(user["user_id"])
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserInfo)
async def get_me(user=Depends(get_current_user)):
    user_id = user.get("user_id")
    if isinstance(user_id, str) and user_id.startswith("guest"):
        return UserInfo(user_id=0, username="guest", role="guest")

    conn = get_auth_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "User not found")
        # Get token usage for this month
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        usage = conn.execute(
            "SELECT tokens_used, input_tokens, output_tokens, cost_usd, model "
            "FROM token_usage WHERE user_id = ? AND month = ?",
            (user_id, month),
        ).fetchone()
        return UserInfo(
            user_id=row["id"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            token_limit=row["token_limit"],
            tokens_used_this_month=usage["tokens_used"] if usage else 0,
            input_tokens_this_month=usage["input_tokens"] if usage else 0,
            output_tokens_this_month=usage["output_tokens"] if usage else 0,
            cost_usd_this_month=usage["cost_usd"] if usage else 0.0,
            model=usage["model"] if usage else "",
        )
    finally:
        conn.close()


# --- Admin user management ---

@router.get("/users", response_model=list[UserListItem])
async def list_users(admin=Depends(require_role("admin"))):
    conn = get_auth_db()
    try:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        rows = conn.execute(
            """SELECT u.*,
                      COALESCE(tu.tokens_used, 0) as tokens_used_this_month,
                      COALESCE(tu.input_tokens, 0) as input_tokens_this_month,
                      COALESCE(tu.output_tokens, 0) as output_tokens_this_month,
                      COALESCE(tu.cost_usd, 0.0) as cost_usd_this_month
               FROM users u
               LEFT JOIN token_usage tu ON tu.user_id = u.id AND tu.month = ?
               ORDER BY u.id""",
            (month,),
        ).fetchall()
        return [UserListItem(
            id=r["id"], username=r["username"], role=r["role"],
            is_active=bool(r["is_active"]), last_login=r["last_login"],
            tokens_used_this_month=r["tokens_used_this_month"],
            input_tokens_this_month=r["input_tokens_this_month"],
            output_tokens_this_month=r["output_tokens_this_month"],
            cost_usd_this_month=r["cost_usd_this_month"],
            token_limit=r["token_limit"],
        ) for r in rows]
    finally:
        conn.close()


@router.post("/users", status_code=201)
async def create_user_endpoint(body: CreateUserRequest, admin=Depends(require_role("admin"))):
    try:
        user_id = create_user(body.username, body.password, body.role, body.token_limit, admin["user_id"])
        audit_log("user_created", user_id=admin["user_id"], username=admin["username"],
                  details=f"Created user '{body.username}' with role '{body.role}'")
        return {"id": user_id, "username": body.username, "role": body.role}
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            raise HTTPException(400, f"Username '{body.username}' already exists")
        raise


@router.get("/settings/chat-status")
async def get_chat_status(admin=Depends(require_role("admin"))):
    from app.api.security import is_chat_enabled
    return {"chat_enabled": is_chat_enabled()}


@router.post("/settings/chat-toggle")
async def toggle_chat(admin=Depends(require_role("admin"))):
    from app.api.security import is_chat_enabled, set_chat_enabled
    current = is_chat_enabled()
    set_chat_enabled(not current)
    audit_log("chat_toggled", user_id=admin["user_id"], username=admin["username"],
              details=f"Chat {'disabled' if current else 'enabled'}")
    return {"chat_enabled": not current}


@router.put("/users/{user_id}")
async def update_user(user_id: int, body: UpdateUserRequest, admin=Depends(require_role("admin"))):
    conn = get_auth_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")

        updates = []
        params = []
        if body.role is not None:
            updates.append("role = ?")
            params.append(body.role)
        if body.is_active is not None:
            updates.append("is_active = ?")
            params.append(int(body.is_active))
        if body.token_limit is not None:
            updates.append("token_limit = ?")
            params.append(body.token_limit)
        if body.new_password:
            updates.append("password_hash = ?")
            params.append(hash_password(body.new_password))

        if updates:
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        audit_details = body.model_dump(exclude_none=True, exclude={"new_password"})
        if body.new_password:
            audit_details["password_changed"] = True
        audit_log("user_updated", user_id=admin["user_id"], username=admin["username"],
                  details=f"Updated user {user_id}: {audit_details}")
        return {"message": "User updated"}
    finally:
        conn.close()
