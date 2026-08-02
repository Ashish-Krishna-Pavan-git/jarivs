"""Security helpers: password hashing, JWT, CSRF, encryption, and URL safety."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import time
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken


JWT_SECRET = os.getenv("JWT_SECRET") or os.getenv("FLASK_SECRET_KEY") or "jarvis-dev-secret-change-me"
TOKEN_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", "43200"))
JWT_ISSUER = "jarvis-agent"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, rounds, salt, expected = encoded.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _unb64(salt), int(rounds))
        return hmac.compare_digest(_b64(actual), expected)
    except Exception:
        return False


def _fernet_key() -> bytes:
    raw = os.getenv("JARVIS_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            return raw.encode("ascii") if len(raw) == 44 else base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        except Exception:
            pass
    return base64.urlsafe_b64encode(hashlib.sha256(JWT_SECRET.encode()).digest())


def encrypt_text(value: str) -> str:
    if not value:
        return ""
    return "fernet:" + Fernet(_fernet_key()).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("fernet:"):
        return value
    try:
        return Fernet(_fernet_key()).decrypt(value.split(":", 1)[1].encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def encrypt_json(data: dict) -> str:
    return encrypt_text(json.dumps(data or {}, separators=(",", ":")))


def decrypt_json(value: str) -> dict:
    try:
        return json.loads(decrypt_text(value) or "{}")
    except Exception:
        return {}


def issue_jwt(username: str, role: str, user_id: int, must_change_password: bool = False, csrf: str | None = None) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": JWT_ISSUER,
        "sub": username,
        "role": role,
        "user_id": user_id,
        "must_change_password": bool(must_change_password),
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(12),
    }
    if csrf:
        payload["csrf"] = csrf
    body = f"{_b64(json.dumps(header,separators=(',',':')).encode())}.{_b64(json.dumps(payload,separators=(',',':')).encode())}"
    sig = hmac.new(JWT_SECRET.encode(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def verify_jwt(token: str) -> dict | None:
    try:
        head, payload, sig = token.split(".", 2)
        body = f"{head}.{payload}"
        expected = hmac.new(JWT_SECRET.encode(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64(expected), sig):
            return None
        data = json.loads(_unb64(payload))
        if data.get("iss") != JWT_ISSUER or int(data.get("exp", 0)) < int(time.time()):
            return None
        return data
    except Exception:
        return None


def make_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def apply_security_headers(response, request):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' https://huggingface.co https://*.huggingface.co https://*.hf.space;"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, X-CSRF-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    allowed = [x.strip() for x in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if x.strip()]
    origin = request.headers.get("Origin")
    if origin and (origin in allowed or not allowed or "hf.space" in origin or "huggingface.co" in origin):
        response.headers["Access-Control-Allow-Origin"] = origin
    return response


def is_safe_external_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False, "Only http and https URLs are allowed"
        if not parsed.hostname:
            return False, "URL must include a hostname"
        host = parsed.hostname.strip().lower()
        if host in {"localhost", "127.0.0.1", "::1"} and not allow_private:
            return False, "Loopback hosts are blocked"
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if not allow_private and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast):
                return False, f"Private or reserved address blocked: {ip}"
        return True, ""
    except Exception as exc:
        return False, f"URL validation failed: {exc}"
