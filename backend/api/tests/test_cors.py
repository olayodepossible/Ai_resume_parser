"""Which browser origins the API accepts.

Worth its own file because the failure mode is invisible from curl: a
disallowed origin still gets a normal response, just without the
`access-control-allow-origin` header, and only the browser turns that into an
error. `http://localhost:3000` and `http://127.0.0.1:3000` are different
origins, which is the trap this guards.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from ..app.config import LOOPBACK_ORIGIN_REGEX, Settings
from ..app.main import settings as app_settings
from .conftest import build_settings

PREFLIGHT_HEADERS = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type",
}


class TestConfiguredOrigins:
    """The `Settings` properties, independent of the middleware."""

    def test_both_loopback_spellings_are_allowed_by_default(self) -> None:
        # Read the field default rather than a constructed Settings: conftest
        # pins `cors_origins`, which would hide a regression in the default.
        default = Settings.model_fields["cors_origins"].default
        origins = build_settings(cors_origins=default).cors_origin_list

        assert "http://localhost:3000" in origins
        assert "http://127.0.0.1:3000" in origins

    def test_the_list_is_split_and_stripped(self) -> None:
        settings = build_settings(
            cors_origins=" http://a.test , http://b.test ,, ",
        )

        assert settings.cors_origin_list == ["http://a.test", "http://b.test"]

    def test_development_accepts_any_loopback_port(self) -> None:
        settings = build_settings(environment="development")

        assert settings.cors_origin_regex_or_none == LOOPBACK_ORIGIN_REGEX

    def test_other_environments_get_no_regex(self) -> None:
        # Production is limited to the enumerated CORS_ORIGINS.
        assert build_settings(environment="production").cors_origin_regex_or_none is None

    def test_an_explicit_regex_wins_everywhere(self) -> None:
        pattern = r"https://.*\.preview\.example\.com"

        for environment in ("development", "production"):
            settings = build_settings(
                environment=environment,
                cors_origin_regex=pattern,
            )

            assert settings.cors_origin_regex_or_none == pattern


class TestLoopbackRegex:
    """Starlette applies this with `re.fullmatch`; these assume the same."""

    def test_matches_every_loopback_spelling_on_any_port(self) -> None:
        for origin in (
            "http://localhost:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3000",
            "http://[::1]:8080",
        ):
            assert re.fullmatch(LOOPBACK_ORIGIN_REGEX, origin), origin

    def test_does_not_match_a_lookalike_host(self) -> None:
        # The reason the pattern must be anchored: a prefix match would let
        # any attacker-controlled domain through.
        for origin in (
            "http://localhost:3000.evil.example.com",
            "http://notlocalhost:3000",
            "http://localhost.evil.example.com:3000",
            "https://localhost:3000",
        ):
            assert not re.fullmatch(LOOPBACK_ORIGIN_REGEX, origin), origin


class TestMiddlewareIsWired:
    """End-to-end through the real app.

    `CORSMiddleware` is configured at import from the module-level settings,
    so `dependency_overrides` cannot vary it. These use the app's own
    configured list rather than hardcoding an origin, which keeps them
    independent of the developer's .env.
    """

    def test_a_configured_origin_survives_preflight(self, client: TestClient) -> None:
        origin = app_settings.cors_origin_list[0]

        response = client.options(
            "/api/v1/auth/login",
            headers={"Origin": origin, **PREFLIGHT_HEADERS},
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin

    def test_every_configured_origin_is_accepted(self, client: TestClient) -> None:
        for origin in app_settings.cors_origin_list:
            response = client.options(
                "/api/v1/auth/login",
                headers={"Origin": origin, **PREFLIGHT_HEADERS},
            )

            assert response.headers.get("access-control-allow-origin") == origin, origin

    def test_a_foreign_origin_is_refused_at_preflight(
        self,
        client: TestClient,
    ) -> None:
        response = client.options(
            "/api/v1/auth/login",
            headers={"Origin": "https://evil.example.com", **PREFLIGHT_HEADERS},
        )

        assert response.status_code == 400
        assert "access-control-allow-origin" not in response.headers

    def test_a_foreign_origin_gets_no_header_on_a_simple_request(
        self,
        client: TestClient,
    ) -> None:
        response = client.get(
            "/health",
            headers={"Origin": "https://evil.example.com"},
        )

        # The request still runs — it is the missing header that makes the
        # browser discard the response.
        assert response.status_code == 200
        assert "access-control-allow-origin" not in response.headers

    def test_the_authorization_header_is_allowed(self, client: TestClient) -> None:
        origin = app_settings.cors_origin_list[0]

        response = client.options(
            "/api/v1/screenings",
            headers={"Origin": origin, **PREFLIGHT_HEADERS},
        )

        allowed = response.headers.get("access-control-allow-headers", "").lower()

        assert "authorization" in allowed
