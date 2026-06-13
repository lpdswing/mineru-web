import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any

from fastapi import HTTPException, Response

from app.models.user import User


AUTH_COOKIE_NAME = "mineru_session"
AUTH_COOKIE_MAX_AGE = int(os.getenv("AUTH_COOKIE_MAX_AGE_SECONDS", "604800"))
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "mineru-web-dev-secret")
PASSWORD_ITERATIONS = 260000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or len(normalized) > 255 or not EMAIL_RE.match(normalized):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    return normalized


def validate_password(password: str) -> str:
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少需要 6 位")
    return password


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    )
    encoded = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${encoded}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, encoded_digest = stored_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    )
    expected = base64.urlsafe_b64encode(digest).decode("ascii")
    return secrets.compare_digest(expected, encoded_digest)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload: str) -> str:
    digest = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def create_session_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": int(time.time()) + AUTH_COOKIE_MAX_AGE,
    }
    encoded_payload = _b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    return f"{encoded_payload}.{_sign(encoded_payload)}"


def decode_session_token(token: str) -> dict[str, Any]:
    try:
        encoded_payload, signature = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="登录状态无效")

    if not secrets.compare_digest(_sign(encoded_payload), signature):
        raise HTTPException(status_code=401, detail="登录状态无效")

    try:
        payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="登录状态无效")

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return payload


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path="/", samesite="lax")
