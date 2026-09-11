"""`run_screening_pipeline` is the shared core: v1 feeds it uploaded PDFs and
v2 feeds it job-board records, so its contract is tested independently of both."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

import backend.api.orchestrator.resume_orchestrator as orch
from .conftest import LLMStub, make_candidate

MODEL = object()


class TestEmptyBatch:
    async def test_returns_an_empty_result(self, llm: LLMStub) -> None:
        result = await orch.run_screening_pipeline([], "Title", "Requirements", MODEL)

        assert result["screeningResults"] == []
        assert result["rankingOutput"]["rankedCandidates"] == []
        assert result["rankingOutput"]["topRecommendation"] == (
            "No candidates available for evaluation"
        )

    async def test_does_not_call_the_model(self, llm: LLMStub) -> None:
        await orch.run_screening_pipeline([], "Title", "Requirements", MODEL)

        assert llm.screened == []
        assert llm.ranked_titles == []

    async def test_still_stamps_processed_at(self, llm: LLMStub) -> None:
        result = await orch.run_screening_pipeline([], "Title", "Requirements", MODEL)

        assert result["processedAt"].endswith("Z")


class TestScreening:
    async def test_screens_every_candidate(self, llm: LLMStub) -> None:
        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 4)]

        result = await orch.run_screening_pipeline(
            candidates, "Title", "Requirements", MODEL, delay_seconds=0
        )

        assert len(result["screeningResults"]) == 3
        assert llm.screened_ids == ["cand-001", "cand-002", "cand-003"]

    async def test_passes_requirements_and_title_through(self, llm: LLMStub) -> None:
        await orch.run_screening_pipeline(
            [make_candidate("cand-001")],
            "Senior ML Platform Engineer",
            "Python and LangChain required",
            MODEL,
            delay_seconds=0,
        )

        assert llm.requirements == ["Python and LangChain required"]
        assert llm.ranked_titles == ["Senior ML Platform Engineer"]

    @pytest.mark.parametrize("concurrency", [1, 3, 10])
    async def test_preserves_input_order(
        self,
        llm: LLMStub,
        monkeypatch: pytest.MonkeyPatch,
        concurrency: int,
    ) -> None:
        """Results are zipped with the uploaded files by position, so order is
        part of the contract even when calls finish out of sequence."""

        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 8)]
        expected = [candidate.candidateId for candidate in candidates]

        async def jittered(candidate: Any, requirements: str, model: Any) -> Any:
            # Later candidates return first, so an implementation that appended
            # results as they arrived would reorder them.
            index = int(candidate.candidateId.split("-")[1])
            await asyncio.sleep((10 - index) * 0.005)
            return await llm.screen_candidate(candidate, requirements, model)

        monkeypatch.setattr(orch, "screen_candidate", jittered)

        result = await orch.run_screening_pipeline(
            candidates,
            "Title",
            "Requirements",
            MODEL,
            concurrency=concurrency,
            delay_seconds=0,
        )

        assert [r.candidateId for r in result["screeningResults"]] == expected


class TestConcurrencyLimit:
    @staticmethod
    def _peak_tracker(
        llm: LLMStub,
        monkeypatch: pytest.MonkeyPatch,
        hold: float = 0.01,
    ) -> Callable[[], int]:
        """Patch screening to record the high-water mark of in-flight calls."""

        in_flight = 0
        peak = 0

        async def tracked(candidate: Any, requirements: str, model: Any) -> Any:
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            try:
                await asyncio.sleep(hold)
                return await llm.screen_candidate(candidate, requirements, model)
            finally:
                in_flight -= 1

        monkeypatch.setattr(orch, "screen_candidate", tracked)

        return lambda: peak

    async def test_never_exceeds_the_limit(
        self, llm: LLMStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        peak = self._peak_tracker(llm, monkeypatch)
        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 10)]

        await orch.run_screening_pipeline(
            candidates,
            "Title",
            "Requirements",
            MODEL,
            concurrency=3,
            delay_seconds=0,
        )

        assert peak() == 3

    async def test_a_concurrency_of_one_is_sequential(
        self, llm: LLMStub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        peak = self._peak_tracker(llm, monkeypatch, hold=0.005)
        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 5)]

        await orch.run_screening_pipeline(
            candidates, "Title", "Requirements", MODEL, concurrency=1, delay_seconds=0
        )

        assert peak() == 1

    @pytest.mark.parametrize("concurrency", [0, -5])
    async def test_a_nonsensical_limit_falls_back_to_one(
        self, llm: LLMStub, concurrency: int
    ) -> None:
        candidates = [make_candidate("cand-001"), make_candidate("cand-002")]

        result = await orch.run_screening_pipeline(
            candidates,
            "Title",
            "Requirements",
            MODEL,
            concurrency=concurrency,
            delay_seconds=0,
        )

        assert len(result["screeningResults"]) == 2


class TestErrorHandling:
    async def test_records_a_fallback_when_told_to_continue(self, llm: LLMStub) -> None:
        llm.fail_screening_for = {"cand-002"}
        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 4)]

        result = await orch.run_screening_pipeline(
            candidates,
            "Title",
            "Requirements",
            MODEL,
            delay_seconds=0,
            continue_on_error=True,
        )

        assert len(result["screeningResults"]) == 3

        failed = result["screeningResults"][1]
        assert failed.candidateId == "cand-002"
        assert failed.score == 0.0
        assert failed.recommendation == "maybe"
        assert failed.concerns == [
            "Screening evaluation failed due to a processing error"
        ]

        # The surviving candidates are unaffected.
        assert result["screeningResults"][0].score == 88.0
        assert result["screeningResults"][2].score == 88.0

    async def test_a_failed_candidate_still_reaches_the_ranking(
        self, llm: LLMStub
    ) -> None:
        llm.fail_screening_for = {"cand-002"}
        candidates = [make_candidate("cand-001"), make_candidate("cand-002")]

        result = await orch.run_screening_pipeline(
            candidates,
            "Title",
            "Requirements",
            MODEL,
            delay_seconds=0,
            continue_on_error=True,
        )

        ranked = [e["candidateId"] for e in result["rankingOutput"]["rankedCandidates"]]
        assert ranked == ["cand-001", "cand-002"]

    async def test_propagates_by_default(self, llm: LLMStub) -> None:
        """v2 keeps the original fail-fast behaviour."""

        llm.fail_screening_for = {"cand-001"}

        with pytest.raises(RuntimeError, match="simulated failure"):
            await orch.run_screening_pipeline(
                [make_candidate("cand-001")],
                "Title",
                "Requirements",
                MODEL,
                delay_seconds=0,
            )

    async def test_a_ranking_failure_always_propagates(self, llm: LLMStub) -> None:
        """continue_on_error covers screening only: without a ranking there is
        no result worth returning."""

        llm.fail_ranking = True

        with pytest.raises(RuntimeError, match="simulated ranking failure"):
            await orch.run_screening_pipeline(
                [make_candidate("cand-001")],
                "Title",
                "Requirements",
                MODEL,
                delay_seconds=0,
                continue_on_error=True,
            )


class TestRateLimitDelay:
    async def test_delay_is_applied_per_candidate(self, llm: LLMStub) -> None:
        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 4)]

        started = asyncio.get_running_loop().time()
        await orch.run_screening_pipeline(
            candidates,
            "Title",
            "Requirements",
            MODEL,
            concurrency=1,
            delay_seconds=0.02,
        )
        elapsed = asyncio.get_running_loop().time() - started

        assert elapsed >= 0.06

    async def test_zero_delay_adds_no_wait(self, llm: LLMStub) -> None:
        candidates = [make_candidate(f"cand-{i:03d}") for i in range(1, 6)]

        started = asyncio.get_running_loop().time()
        await orch.run_screening_pipeline(
            candidates, "Title", "Requirements", MODEL, delay_seconds=0
        )
        elapsed = asyncio.get_running_loop().time() - started

        assert elapsed < 0.5
