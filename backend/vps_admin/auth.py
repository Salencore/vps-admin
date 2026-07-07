from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import get_settings
from .db import connect, utcnow

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_user(username: str, password: str, role: str = "admin") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, utcnow()),
        )


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def create_token(user: dict[str, Any]) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.token_ttl_minutes)
    payload = {"sub": user["username"], "role": user["role"], "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
    except JWTError:
        return None
