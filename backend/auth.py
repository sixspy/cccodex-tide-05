import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

SECRET = os.environ.get("JWT_SECRET", "tide-telegram-dev-secret")
SALT = "tide-telegram-v1"


def _digest(password: str) -> str:
    return hashlib.sha256(f"{SALT}:{password}".encode()).hexdigest()


USERS = {
    "admin": {"role": "writer", "digest": _digest("123456"), "title": "归集员"},
    "archive": {"role": "reader", "digest": _digest("arch123456"), "title": "档案员"},
}


def authenticate(username: str, password: str):
    user = USERS.get(username)
    if not user:
        return None
    digest = _digest(password)
    if not hmac.compare_digest(digest, user["digest"]):
        return None
    return {"username": username, "role": user["role"], "title": user["title"]}


def issue_token(user: dict) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    return jwt.encode(
        {"sub": user["username"], "role": user["role"], "exp": exp},
        SECRET,
        algorithm="HS256",
    )


def read_user(authorization: str | None):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:].strip()
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    username = payload.get("sub")
    user = USERS.get(username)
    if not user:
        return None
    return {"username": username, "role": payload.get("role"), "title": user["title"]}
