"""The signup / login / profile contract the frontend is built against."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth import (
    InvalidTokenError,
    issue_token,
    read_token,
    verify_password,
)
from app.config import BACKEND_ROOT, get_user_store
from tests.conftest import build_settings

CREDENTIALS = {
    "email": "Ada@Example.com",
    "password": "correct horse battery",
    "fullName": "Ada Lovelace",
}


def register(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/signup",
        json={**CREDENTIALS, **overrides},
    )

    assert response.status_code == 201, response.text

    return response.json()


class TestSignup:
    def test_returns_a_token_and_the_new_user(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        assert body["tokenType"] == "bearer"
        assert body["accessToken"]
        assert body["user"]["fullName"] == "Ada Lovelace"
        assert body["user"]["id"].startswith("user-")

    def test_normalises_the_email(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        # Stored lowercased so "Ada@" and "ada@" are the same account.
        assert body["user"]["email"] == "ada@example.com"

    def test_seeds_default_settings(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        assert body["user"]["settings"] == {
            "company": "",
            "defaultPositionTitle": "",
            "emailOnCompletion": False,
            "theme": "system",
        }

    def test_falls_back_to_the_email_local_part_for_a_blank_name(
        self,
        auth_client: TestClient,
    ) -> None:
        body = register(auth_client, fullName="   ")

        assert body["user"]["fullName"] == "ada"

    def test_never_returns_the_password_hash(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        assert "passwordHash" not in body["user"]

    def test_a_duplicate_email_is_a_conflict(self, auth_client: TestClient) -> None:
        register(auth_client)

        response = auth_client.post("/api/v1/auth/signup", json=CREDENTIALS)

        assert response.status_code == 409

    def test_a_duplicate_email_in_another_case_is_also_a_conflict(
        self,
        auth_client: TestClient,
    ) -> None:
        register(auth_client)

        response = auth_client.post(
            "/api/v1/auth/signup",
            json={**CREDENTIALS, "email": "ADA@EXAMPLE.COM"},
        )

        assert response.status_code == 409

    @pytest.mark.parametrize(
        "overrides",
        [
            {"password": "short"},
            {"email": "not-an-email"},
            {"email": ""},
        ],
        ids=["password-too-short", "malformed-email", "empty-email"],
    )
    def test_rejects_bad_input(
        self,
        auth_client: TestClient,
        overrides: dict[str, Any],
    ) -> None:
        response = auth_client.post(
            "/api/v1/auth/signup",
            json={**CREDENTIALS, **overrides},
        )

        assert response.status_code == 422

    def test_the_stored_password_is_hashed(
        self,
        auth_client: TestClient,
        auth_store_path: str,
    ) -> None:
        body = register(auth_client)
        stored = get_user_store(auth_store_path).get(body["user"]["id"])

        assert CREDENTIALS["password"] not in stored["passwordHash"]
        assert stored["passwordHash"].startswith("pbkdf2_sha256$")
        assert verify_password(CREDENTIALS["password"], stored["passwordHash"])


class TestLogin:
    def test_accepts_the_right_password(self, auth_client: TestClient) -> None:
        register(auth_client)

        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": CREDENTIALS["email"], "password": CREDENTIALS["password"]},
        )

        assert response.status_code == 200
        assert response.json()["accessToken"]

    def test_is_case_insensitive_on_the_email(self, auth_client: TestClient) -> None:
        register(auth_client)

        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "ADA@EXAMPLE.COM", "password": CREDENTIALS["password"]},
        )

        assert response.status_code == 200

    def test_a_wrong_password_is_unauthorised(self, auth_client: TestClient) -> None:
        register(auth_client)

        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": CREDENTIALS["email"], "password": "wrong password"},
        )

        assert response.status_code == 401

    def test_an_unknown_email_is_indistinguishable_from_a_wrong_password(
        self,
        auth_client: TestClient,
    ) -> None:
        register(auth_client)

        wrong_password = auth_client.post(
            "/api/v1/auth/login",
            json={"email": CREDENTIALS["email"], "password": "wrong password"},
        )
        unknown_email = auth_client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "wrong password"},
        )

        # Same status and same message: the endpoint must not reveal which
        # emails have accounts.
        assert unknown_email.status_code == wrong_password.status_code == 401
        assert unknown_email.json()["detail"] == wrong_password.json()["detail"]


class TestReadMe:
    def test_returns_the_token_holder(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        response = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['accessToken']}"},
        )

        assert response.status_code == 200
        assert response.json() == body["user"]

    def test_a_missing_header_is_unauthorised(self, auth_client: TestClient) -> None:
        assert auth_client.get("/api/v1/auth/me").status_code == 401

    @pytest.mark.parametrize(
        "token",
        ["", "garbage", "a.b.c", "not-base64.signature"],
        ids=["empty", "no-separator", "too-many-parts", "bad-signature"],
    )
    def test_a_malformed_token_is_unauthorised(
        self,
        auth_client: TestClient,
        token: str,
    ) -> None:
        response = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 401

    def test_a_token_signed_with_another_secret_is_rejected(
        self,
        auth_client: TestClient,
    ) -> None:
        body = register(auth_client)
        forged, _ = issue_token(body["user"]["id"], "a-different-secret", 3600)

        response = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {forged}"},
        )

        assert response.status_code == 401

    def test_an_expired_token_is_rejected(self, auth_client: TestClient) -> None:
        body = register(auth_client)
        expired, _ = issue_token(
            body["user"]["id"],
            build_settings().auth_secret,
            ttl_seconds=-1,
        )

        response = auth_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )

        assert response.status_code == 401


class TestUpdateMe:
    def test_changes_the_name(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        response = auth_client.patch(
            "/api/v1/auth/me",
            json={"fullName": "Ada B. Lovelace"},
            headers={"Authorization": f"Bearer {body['accessToken']}"},
        )

        assert response.status_code == 200
        assert response.json()["fullName"] == "Ada B. Lovelace"

    def test_changes_settings(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        response = auth_client.patch(
            "/api/v1/auth/me",
            json={
                "settings": {
                    "company": "Analytical Engines Ltd",
                    "defaultPositionTitle": "Senior ML Engineer",
                    "emailOnCompletion": True,
                    "theme": "dark",
                }
            },
            headers={"Authorization": f"Bearer {body['accessToken']}"},
        )

        assert response.status_code == 200
        assert response.json()["settings"]["theme"] == "dark"
        assert response.json()["settings"]["company"] == "Analytical Engines Ltd"

    def test_changes_persist_to_the_next_read(self, auth_client: TestClient) -> None:
        body = register(auth_client)
        headers = {"Authorization": f"Bearer {body['accessToken']}"}

        auth_client.patch(
            "/api/v1/auth/me",
            json={"fullName": "Ada B. Lovelace"},
            headers=headers,
        )

        assert (
            auth_client.get("/api/v1/auth/me", headers=headers).json()["fullName"]
            == "Ada B. Lovelace"
        )

    def test_an_omitted_field_is_left_alone(self, auth_client: TestClient) -> None:
        body = register(auth_client)
        headers = {"Authorization": f"Bearer {body['accessToken']}"}

        auth_client.patch(
            "/api/v1/auth/me",
            json={"settings": {"theme": "dark"}},
            headers=headers,
        )
        response = auth_client.patch("/api/v1/auth/me", json={}, headers=headers)

        assert response.json()["fullName"] == "Ada Lovelace"
        assert response.json()["settings"]["theme"] == "dark"

    def test_an_unknown_theme_is_rejected(self, auth_client: TestClient) -> None:
        body = register(auth_client)

        response = auth_client.patch(
            "/api/v1/auth/me",
            json={"settings": {"theme": "solarized"}},
            headers={"Authorization": f"Bearer {body['accessToken']}"},
        )

        assert response.status_code == 422

    def test_requires_a_token(self, auth_client: TestClient) -> None:
        response = auth_client.patch("/api/v1/auth/me", json={"fullName": "Nobody"})

        assert response.status_code == 401


class TestTokens:
    def test_a_round_trip_returns_the_subject(self) -> None:
        token, _ = issue_token("user-abc", "secret", 3600)

        assert read_token(token, "secret") == "user-abc"

    def test_expiry_is_reported_in_epoch_seconds(self) -> None:
        _, expires_at = issue_token("user-abc", "secret", 3600)

        assert 3590 <= expires_at - int(time.time()) <= 3600

    def test_a_tampered_payload_is_rejected(self) -> None:
        token, _ = issue_token("user-abc", "secret", 3600)
        _, signature = token.split(".")

        # {"sub":"user-evil","exp":9999999999} carrying the original signature.
        forged = "eyJzdWIiOiJ1c2VyLWV2aWwiLCJleHAiOjk5OTk5OTk5OTl9"

        with pytest.raises(InvalidTokenError):
            read_token(f"{forged}.{signature}", "secret")


class TestStoreLocation:
    def test_a_relative_path_is_anchored_to_the_backend_directory(self) -> None:
        store = get_user_store(".data/users.json")

        # Not the working directory: `uv run main.py` from backend/ and
        # `uvicorn app.main:app` from the repo root must agree.
        assert store.path == BACKEND_ROOT / ".data" / "users.json"

    def test_an_absolute_path_is_left_alone(self, auth_store_path: str) -> None:
        assert get_user_store(auth_store_path).path == Path(auth_store_path)


class TestOpenApiShape:
    def test_the_auth_routes_are_documented(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]

        assert "/api/v1/auth/signup" in paths
        assert "/api/v1/auth/login" in paths
        assert set(paths["/api/v1/auth/me"]) == {"get", "patch"}
