"""사용자 인증/승인. JSON 저장 + pbkdf2 해시 + hmac 서명 세션 쿠키(추가 의존성 없음)."""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime

from fastapi import HTTPException, Request

from ..config import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    USERS_FILE,
    get_session_secret,
)

COOKIE_NAME = "session"
SESSION_TTL = 60 * 60 * 24 * 14  # 14일
_PBKDF2_ITER = 200_000


# ---------- 저장소 ----------
def _load() -> list[dict]:
    if not USERS_FILE.exists():
        return []
    try:
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write(users: list[dict]) -> None:
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")


def get_user(username: str) -> dict | None:
    uname = (username or "").strip().lower()
    for u in _load():
        if u["username"].lower() == uname:
            return u
    return None


# ---------- 비밀번호 해시 ----------
def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITER)
    return dk.hex()


def _make_password(password: str) -> tuple[str, str]:
    salt = os.urandom(16)
    return salt.hex(), _hash_password(password, salt)


def _verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_hash_password(password, salt), hash_hex)


# ---------- 사용자 생성/조회 ----------
def create_user(username: str, password: str, role: str = "user", status: str = "pending") -> dict:
    username = (username or "").strip()
    salt_hex, hash_hex = _make_password(password)
    user = {
        "username": username,
        "salt": salt_hex,
        "password_hash": hash_hex,
        "role": role,
        "status": status,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    users = _load()
    users.append(user)
    _write(users)
    return user


def authenticate(username: str, password: str) -> dict | None:
    u = get_user(username)
    if not u:
        return None
    if not _verify_password(password, u.get("salt", ""), u.get("password_hash", "")):
        return None
    return u


def public_user(u: dict) -> dict:
    return {"username": u["username"], "role": u["role"], "status": u["status"]}


def count_admins() -> int:
    return sum(1 for u in _load() if u.get("role") == "admin")


def seed_admin() -> None:
    """관리자가 한 명도 없을 때만 .env 기준으로 부트스트랩 관리자 생성/승격.

    이미 관리자가 있으면 아무것도 하지 않는다 -> 권한이 데이터(users.json)에
    유지되므로 다른 사용자에게 관리자를 양도해도 재시작 후에도 유지된다.
    """
    if count_admins() > 0:
        return
    if not ADMIN_PASSWORD:
        return
    existing = get_user(ADMIN_USERNAME)
    if existing is None:
        create_user(ADMIN_USERNAME, ADMIN_PASSWORD, role="admin", status="approved")
    else:
        users = _load()
        for u in users:
            if u["username"].lower() == ADMIN_USERNAME.strip().lower():
                u["role"] = "admin"
                u["status"] = "approved"
        _write(users)


def set_role(username: str, role: str) -> tuple[bool, str]:
    """사용자 역할 변경(admin/user). 마지막 관리자는 해제 불가."""
    if role not in ("admin", "user"):
        return False, "잘못된 역할입니다."
    target = get_user(username)
    if target is None:
        return False, "사용자를 찾을 수 없습니다."
    if role == "user" and target.get("role") == "admin" and count_admins() <= 1:
        return False, "마지막 관리자는 해제할 수 없습니다."
    users = _load()
    for u in users:
        if u["username"].lower() == username.strip().lower():
            u["role"] = role
            if role == "admin":
                u["status"] = "approved"
    _write(users)
    return True, "ok"


# ---------- 관리자 작업 ----------
def list_users() -> list[dict]:
    return [
        {"username": u["username"], "role": u["role"], "status": u["status"],
         "created": u.get("created", "")}
        for u in _load()
    ]


def set_status(username: str, status: str) -> bool:
    users = _load()
    found = False
    for u in users:
        if u["username"].lower() == username.strip().lower():
            if u.get("role") == "admin":
                return False  # 관리자 상태는 변경 불가
            u["status"] = status
            found = True
    if found:
        _write(users)
    return found


def delete_user(username: str) -> bool:
    users = _load()
    target = get_user(username)
    if target is None or target.get("role") == "admin":
        return False
    new_users = [u for u in users if u["username"].lower() != username.strip().lower()]
    _write(new_users)
    return True


# ---------- 세션 쿠키(hmac 서명) ----------
def _sign(payload: str) -> str:
    sig = hmac.new(get_session_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")


def create_session_token(username: str) -> str:
    exp = int(time.time()) + SESSION_TTL
    raw = f"{username}|{exp}"
    payload = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{payload}.{_sign(payload)}"


def _b64decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def verify_session_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(payload)):
        return None
    try:
        raw = _b64decode(payload).decode("utf-8")
        username, exp_str = raw.rsplit("|", 1)
        if int(exp_str) < int(time.time()):
            return None
        return username
    except Exception:
        return None


# ---------- FastAPI 의존성 ----------
def get_current_user(request: Request) -> dict | None:
    username = verify_session_token(request.cookies.get(COOKIE_NAME))
    if not username:
        return None
    return get_user(username)


def require_user(request: Request) -> dict:
    u = get_current_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return u


def require_approved(request: Request) -> dict:
    u = require_user(request)
    if u.get("role") != "admin" and u.get("status") != "approved":
        raise HTTPException(status_code=403, detail="관리자 승인 대기 중입니다.")
    return u


def require_admin(request: Request) -> dict:
    u = require_user(request)
    if u.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return u
