"""Signup / login / profile endpoints backing the frontend's auth screens.

The implementation is a placeholder — see the module docstring in `app/auth.py`
for what it does not do (revocation, refresh, password reset, rate limiting).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
    UserStore,
    issue_token,
    public_user,
    read_token,
)
from ..config import Settings, get_settings, get_user_store
from ..schemas import (
    AuthResponse,
    LoginRequest,
    SignupRequest,
    UpdateProfileRequest,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# `auto_error=False` so a missing header raises our own 401 with a consistent
# body, rather than Starlette's bare 403.
bearer_scheme = HTTPBearer(auto_error=False)


def _store(settings: Settings) -> UserStore:
    return get_user_store(settings.auth_store_path)


def _auth_response(user: dict, settings: Settings) -> AuthResponse:
    token, expires_at = issue_token(
        user["id"],
        settings.auth_secret,
        settings.auth_token_ttl_seconds,
    )

    return AuthResponse(
        accessToken=token,
        expiresAt=expires_at,
        user=UserOut(**public_user(user)),
    )


async def current_user(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> dict:
    """Resolve `Authorization: Bearer <token>` to a user record."""

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = read_token(credentials.credentials, settings.auth_secret)
        return _store(settings).get(user_id)
    except InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


@router.post(
    "/signup",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and return a token for it",
)
async def signup(
    payload: SignupRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    try:
        user = _store(settings).create(
            email=str(payload.email),
            password=payload.password,
            full_name=payload.fullName,
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    return _auth_response(user, settings)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Exchange email and password for a token",
)
async def login(
    payload: LoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    try:
        user = _store(settings).authenticate(str(payload.email), payload.password)
    except InvalidCredentialsError as error:
        # Deliberately the same message for an unknown email and a wrong
        # password, so the endpoint is not an account-existence oracle.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return _auth_response(user, settings)


@router.get("/me", response_model=UserOut, summary="The signed-in user")
async def read_me(user: Annotated[dict, Depends(current_user)]) -> UserOut:
    return UserOut(**public_user(user))


@router.patch(
    "/me",
    response_model=UserOut,
    summary="Update the signed-in user's name or settings",
)
async def update_me(
    payload: UpdateProfileRequest,
    user: Annotated[dict, Depends(current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserOut:
    updated = _store(settings).update(
        user["id"],
        fullName=payload.fullName,
        settings=payload.settings.model_dump() if payload.settings else None,
    )

    return UserOut(**public_user(updated))
