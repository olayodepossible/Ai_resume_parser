"""`coerce_ranking_output` is the guard between the model's free-form JSON and
everything downstream, which indexes straight into the result. These tests pin
the ways a model response can be wrong."""

from __future__ import annotations

import pytest

from orchestrator.resume_orchestrator import coerce_ranking_output

IDS = ["cand-001", "cand-002", "cand-003"]


def entry(candidate_id: str, rank: int, score: float = 50.0) -> dict[str, object]:
    return {
        "candidateId": candidate_id,
        "rank": rank,
        "finalScore": score,
        "justification": f"because {candidate_id}",
    }


def ids_of(output: dict) -> list[str]:
    return [item["candidateId"] for item in output["rankedCandidates"]]


def ranks_of(output: dict) -> list[int]:
    return [item["rank"] for item in output["rankedCandidates"]]


class TestHappyPath:
    def test_passes_through_a_well_formed_response(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [entry(i, r) for r, i in enumerate(IDS, start=1)],
                "topRecommendation": "cand-001 is strongest",
            },
            IDS,
        )

        assert ids_of(output) == IDS
        assert ranks_of(output) == [1, 2, 3]
        assert output["topRecommendation"] == "cand-001 is strongest"

    def test_sorts_by_rank_regardless_of_array_order(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [
                    entry("cand-003", 3),
                    entry("cand-001", 1),
                    entry("cand-002", 2),
                ],
                "topRecommendation": "",
            },
            IDS,
        )

        assert ids_of(output) == IDS


class TestKeyAliases:
    def test_accepts_snake_case(self) -> None:
        output = coerce_ranking_output(
            {
                "ranked_candidates": [
                    {
                        "candidate_id": "cand-001",
                        "rank": 1,
                        "final_score": 91,
                        "justification": "strong",
                    }
                ],
                "top_recommendation": "cand-001",
            },
            ["cand-001"],
        )

        assert output["rankedCandidates"][0]["finalScore"] == 91.0
        assert output["rankedCandidates"][0]["justification"] == "strong"
        assert output["topRecommendation"] == "cand-001"

    def test_accepts_mixed_case_and_hyphens(self) -> None:
        output = coerce_ranking_output(
            {
                "RankedCandidates": [
                    {"Candidate-Id": "cand-001", "Rank": 1, "FinalScore": 70}
                ],
                "TopRecommendation": "ok",
            },
            ["cand-001"],
        )

        assert ids_of(output) == ["cand-001"]
        assert output["topRecommendation"] == "ok"


class TestScoreCoercion:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (250, 100.0),  # clamped down
            (-40, 0.0),  # clamped up
            ("77", 77.0),  # numeric string
            ("77.5", 77.5),
            (None, 0.0),
            ("not a number", 0.0),
            (True, 0.0),  # a bool is not a score
            (88, 88.0),
        ],
    )
    def test_coerces_and_clamps(self, raw: object, expected: float) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [
                    {"candidateId": "cand-001", "rank": 1, "finalScore": raw}
                ],
                "topRecommendation": "",
            },
            ["cand-001"],
        )

        assert output["rankedCandidates"][0]["finalScore"] == expected

    def test_missing_score_defaults_to_zero(self) -> None:
        output = coerce_ranking_output(
            {"rankedCandidates": [{"candidateId": "cand-001", "rank": 1}]},
            ["cand-001"],
        )

        assert output["rankedCandidates"][0]["finalScore"] == 0.0


class TestCandidateReconciliation:
    def test_drops_a_hallucinated_id(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [entry("cand-001", 1), entry("ghost-999", 2)],
                "topRecommendation": "",
            },
            ["cand-001"],
        )

        assert ids_of(output) == ["cand-001"]

    def test_drops_a_repeated_id(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [
                    entry("cand-001", 1, 90),
                    entry("cand-001", 2, 10),
                ],
                "topRecommendation": "",
            },
            ["cand-001"],
        )

        assert ids_of(output) == ["cand-001"]
        assert output["rankedCandidates"][0]["finalScore"] == 90.0

    def test_appends_a_candidate_the_model_omitted(self) -> None:
        """An omitted candidate must never silently vanish from the shortlist."""

        output = coerce_ranking_output(
            {
                "rankedCandidates": [entry("cand-001", 1), entry("cand-002", 2)],
                "topRecommendation": "",
            },
            IDS,
        )

        assert ids_of(output) == IDS
        appended = output["rankedCandidates"][-1]
        assert appended["candidateId"] == "cand-003"
        assert appended["finalScore"] == 0.0
        assert "did not return a placement" in appended["justification"]

    def test_appends_every_candidate_when_the_list_is_empty(self) -> None:
        output = coerce_ranking_output(
            {"rankedCandidates": [], "topRecommendation": ""}, IDS
        )

        assert ids_of(output) == IDS
        assert ranks_of(output) == [1, 2, 3]

    def test_renumbers_ranks_after_reconciliation(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [
                    entry("cand-002", 7),
                    entry("ghost-999", 1),
                    entry("cand-001", 4),
                ],
                "topRecommendation": "",
            },
            IDS,
        )

        assert ids_of(output) == ["cand-001", "cand-002", "cand-003"]
        assert ranks_of(output) == [1, 2, 3]

    def test_tolerates_a_non_integer_rank(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": [
                    {"candidateId": "cand-001", "rank": "first", "finalScore": 50}
                ],
                "topRecommendation": "",
            },
            ["cand-001"],
        )

        assert ranks_of(output) == [1]


class TestMalformedResponses:
    def test_missing_ranked_candidates_raises(self) -> None:
        with pytest.raises(RuntimeError, match="rankedCandidates"):
            coerce_ranking_output({"topRecommendation": "x"}, IDS)

    def test_non_list_ranked_candidates_raises(self) -> None:
        with pytest.raises(RuntimeError, match="rankedCandidates"):
            coerce_ranking_output({"rankedCandidates": "cand-001"}, IDS)

    def test_skips_non_object_entries(self) -> None:
        output = coerce_ranking_output(
            {
                "rankedCandidates": ["cand-001", 42, None, entry("cand-001", 1)],
                "topRecommendation": "",
            },
            ["cand-001"],
        )

        assert ids_of(output) == ["cand-001"]

    def test_non_string_top_recommendation_becomes_empty(self) -> None:
        output = coerce_ranking_output(
            {"rankedCandidates": [entry("cand-001", 1)], "topRecommendation": 42},
            ["cand-001"],
        )

        assert output["topRecommendation"] == ""

    def test_missing_top_recommendation_becomes_empty(self) -> None:
        output = coerce_ranking_output(
            {"rankedCandidates": [entry("cand-001", 1)]}, ["cand-001"]
        )

        assert output["topRecommendation"] == ""
