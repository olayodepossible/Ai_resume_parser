from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import backend.api.orchestrator.resume_orchestrator as orch
from ..app.config import Settings, get_settings
from ..app.main import app
from ..app.routers import screenings as screenings_router

# Explicit values for every setting the tests depend on. Passing them as init
# kwargs (which outrank both .env and the process environment) keeps runs
# deterministic regardless of the developer's own .env.
BASE_SETTINGS: dict[str, Any] = {
    "app_name": "resume-parser-test",
    "environment": "test",
    "cors_origins": "http://localhost:3000",
    "openrouter_api_key": "test-key",
    "openrouter_base_url": "https://example.invalid/v1",
    "openai_model": "test-model",
    "auth_secret": "test-secret",
    "auth_token_ttl_hours": 12,
    # Every test that touches auth goes through `auth_client`, which points
    # this at a tmp file. The default is a deliberate dead end: if a new test
    # forgets the fixture, it fails loudly instead of writing real accounts
    # into backend/.data/.
    "auth_store_path": "/tests-must-use-the-auth_client-fixture/users.json",
    "max_resume_files": 25,
    "max_file_size_mb": 10.0,
    "max_pdf_pages": 30,
    "max_resume_chars": 20_000,
    "max_job_description_chars": 20_000,
    "screening_concurrency": 4,
    "screening_delay_seconds": 0.0,
}


def build_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**BASE_SETTINGS, **overrides})


@pytest.fixture
def make_client() -> Iterator[Callable[..., TestClient]]:
    """Build a TestClient whose settings can be overridden per test."""

    def _make(**overrides: Any) -> TestClient:
        settings = build_settings(**overrides)
        app.dependency_overrides[get_settings] = lambda: settings
        return TestClient(app)

    yield _make

    app.dependency_overrides.clear()


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()


@pytest.fixture
def auth_store_path(tmp_path: Path) -> str:
    """Where `auth_client` keeps its users: one fresh file per test."""

    return str(tmp_path / "users.json")


@pytest.fixture
def auth_client(
    make_client: Callable[..., TestClient],
    auth_store_path: str,
) -> TestClient:
    """A client whose user store is a fresh file, so accounts never leak."""

    return make_client(auth_store_path=auth_store_path)


@dataclass
class LLMStub:
    """Stands in for the model provider, and records what it was asked.

    `screen_candidate` and `rank_candidates` are patched on the orchestrator
    module, so `run_screening_pipeline` and the endpoint exercise their real
    wiring — only the network call is replaced.
    """

    screened: list[orch.Candidate] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    ranked_titles: list[str] = field(default_factory=list)

    # Behaviour switches
    fail_screening_for: set[str] = field(default_factory=set)
    fail_ranking: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    default_score: float = 88.0
    ranking_payload: dict[str, Any] | None = None

    @property
    def screened_ids(self) -> list[str]:
        return [candidate.candidateId for candidate in self.screened]

    @property
    def screened_names(self) -> list[str]:
        return [candidate.name for candidate in self.screened]

    async def screen_candidate(
        self,
        candidate: orch.Candidate,
        position_requirements: str,
        model: Any,
    ) -> orch.ScreeningResult:
        self.screened.append(candidate)
        self.requirements.append(position_requirements)

        if candidate.candidateId in self.fail_screening_for:
            raise RuntimeError(f"simulated failure for {candidate.candidateId}")

        return orch.ScreeningResult(
            candidateId=candidate.candidateId,
            score=self.scores.get(candidate.candidateId, self.default_score),
            recommendation="strong_yes",
            keySkills=["Python"],
            concerns=[],
            summary=f"summary for {candidate.name}",
        )

    async def rank_candidates(
        self,
        screening_results: list[orch.ScreeningResult],
        position_title: str,
        model: Any,
    ) -> orch.RankingOutput:
        self.ranked_titles.append(position_title)

        if self.fail_ranking:
            raise RuntimeError("simulated ranking failure")

        candidate_ids = [result.candidateId for result in screening_results]

        payload = self.ranking_payload or {
            "rankedCandidates": [
                {
                    "candidateId": result.candidateId,
                    "rank": position,
                    "finalScore": result.score,
                    "justification": f"justification for {result.candidateId}",
                }
                for position, result in enumerate(screening_results, start=1)
            ],
            "topRecommendation": "top pick",
        }

        # Deliberately routed through the real coercion, so endpoint tests see
        # the same normalisation production does.
        return orch.coerce_ranking_output(payload, candidate_ids)


@pytest.fixture
def llm(monkeypatch: pytest.MonkeyPatch) -> LLMStub:
    stub = LLMStub()

    monkeypatch.setattr(
        orch,
        "screen_candidate",
        stub.screen_candidate,
    )
    monkeypatch.setattr(
        orch,
        "rank_candidates",
        stub.rank_candidates,
    )

    # Prevent the endpoint from constructing a real LLM client.
    monkeypatch.setattr(
        screenings_router,
        "build_chat_model",
        lambda settings: object(),
    )

    return stub

def make_candidate(candidate_id: str, name: str | None = None) -> orch.Candidate:
    return orch.Candidate(
        candidateId=candidate_id,
        name=name or f"Person {candidate_id}",
        email="",
        resumeText="resume text",
        appliedPosition="Senior ML Platform Engineer",
        applicationDate="2026-09-09",
    )
