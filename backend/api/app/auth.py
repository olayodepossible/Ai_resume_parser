"""Placeholder authentication: a signed-token scheme over a JSON user store.

Deliberately dependency-free — `hashlib`/`hmac` only, no database, no session
table. It exists so the frontend has a real signup/login/me contract to build
against, and is meant to be swapped for a proper identity provider before this
is exposed to anyone. See `AUTH_SECRET` in `config.py`: with the default value
tokens are portable between installs, which is fine for development and not
fine anywhere else.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

PBKDF2_ROUNDS = 240_000
SALT_BYTES = 16


class AuthError(Exception):
    """Base for the failures the auth router turns into 4xx responses."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class InvalidTokenError(AuthError):
    pass


# ---------------------
# Passwords
# ---------------------


def hash_password(password: str) -> str:
    """Return a `pbkdf2_sha256$rounds$salt$digest` string."""

    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)

    return "$".join(
        [
            "pbkdf2_sha256",
            str(PBKDF2_ROUNDS),
            _b64encode(salt),
            _b64encode(digest),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, digest = encoded.split("$")
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        _b64decode(salt),
        int(rounds),
    )

    return hmac.compare_digest(candidate, _b64decode(digest))


# ------------------------
# Tokens
# ------------------------


def issue_token(user_id: str, secret: str, ttl_seconds: int) -> tuple[str, int]:
    """Return `(token, expires_at_epoch_seconds)`.

    The token carries its own expiry, so signing out is a client-side discard.
    Nothing here supports revocation; that arrives with real sessions.
    """

    expires_at = int(time.time()) + ttl_seconds
    payload = _b64encode(
        json.dumps({"sub": user_id, "exp": expires_at}, separators=(",", ":")).encode()
    )
    signature = _b64encode(_sign(payload, secret))

    return f"{payload}.{signature}", expires_at


def read_token(token: str, secret: str) -> str:
    """Return the user id carried by `token`, or raise `InvalidTokenError`."""

    try:
        payload, signature = token.split(".")
    except ValueError as error:
        raise InvalidTokenError("Malformed token.") from error

    if not hmac.compare_digest(_b64decode(signature), _sign(payload, secret)):
        raise InvalidTokenError("Token signature does not match.")

    try:
        claims = json.loads(_b64decode(payload))
        user_id = str(claims["sub"])
        expires_at = int(claims["exp"])
    except (ValueError, KeyError, TypeError) as error:
        raise InvalidTokenError("Token payload is unreadable.") from error

    if expires_at <= time.time():
        raise InvalidTokenError("Token has expired.")

    return user_id


# ------------------------
# User store
# ------------------------


class UserStore:
    """A JSON file of users, guarded by a lock and rewritten on every change.

    A file rather than a dict so accounts survive uvicorn's reloader, and a
    whole-file rewrite rather than incremental updates because the record count
    here is measured in tens.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def create(self, email: str, password: str, full_name: str) -> dict[str, Any]:
        normalized = _normalize_email(email)

        with self._lock:
            users = self._load()

            if normalized in users:
                raise EmailAlreadyRegisteredError(
                    "An account with that email already exists."
                )

            user = {
                "id": f"user-{uuid.uuid4().hex[:12]}",
                "email": normalized,
                "fullName": full_name.strip() or normalized.split("@")[0],
                "passwordHash": hash_password(password),
                "createdAt": _now_iso(),
                "settings": dict(DEFAULT_USER_SETTINGS),
            }
            users[normalized] = user
            self._save(users)

        return user

    def authenticate(self, email: str, password: str) -> dict[str, Any]:
        with self._lock:
            user = self._load().get(_normalize_email(email))
            print(f"User: {user}")

        # Hash even when the email is unknown, so a missing account and a wrong
        # password take the same amount of time to reject.
        stored_hash = user["passwordHash"] if user else _dummy_hash()

        if not verify_password(password, stored_hash) or user is None:
            raise InvalidCredentialsError("Incorrect email or password.")

        return user

    def get(self, user_id: str) -> dict[str, Any]:
        with self._lock:
            for user in self._load().values():
                if user["id"] == user_id:
                    return user

        raise InvalidTokenError("The account on this token no longer exists.")

    def update(self, user_id: str, **changes: Any) -> dict[str, Any]:
        """Apply `fullName` and/or `settings` changes; `settings` is merged."""

        with self._lock:
            users = self._load()

            for key, user in users.items():
                if user["id"] != user_id:
                    continue

                if (full_name := changes.get("fullName")) is not None:
                    user["fullName"] = full_name.strip() or user["fullName"]

                if (settings := changes.get("settings")) is not None:
                    user["settings"] = {**user.get("settings", {}), **settings}

                users[key] = user
                self._save(users)

                return user

        raise InvalidTokenError("The account on this token no longer exists.")

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}

        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A hand-edited or truncated store should not take the API down;
            # treat it as empty and let the next write replace it.
            return {}

        return data if isinstance(data, dict) else {}

    def _save(self, users: dict[str, dict[str, Any]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Write-then-replace so a crash mid-write cannot leave a partial file.
        temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temporary.write_text(json.dumps(users, indent=2), encoding="utf-8")
        temporary.replace(self._path)


DEFAULT_USER_SETTINGS: dict[str, Any] = {
    "company": "",
    "defaultPositionTitle": "",
    "emailOnCompletion": False,
    "theme": "system",
}

@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A hash of nothing in particular, compared against unknown emails.

    Computed on first use rather than at import: `hash_password` is defined
    above but its base64 helpers are not, and 240k PBKDF2 rounds is not
    something to spend on every import of this module.
    """

    return hash_password(secrets.token_urlsafe(16))


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    """Strip the password hash before a user record leaves the process."""

    return {
        "id": user["id"],
        "email": user["email"],
        "fullName": user["fullName"],
        "createdAt": user["createdAt"],
        "settings": {**DEFAULT_USER_SETTINGS, **user.get("settings", {})},
    }


def _sign(payload: str, secret: str) -> bytes:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)

    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError):
        return b""


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")
