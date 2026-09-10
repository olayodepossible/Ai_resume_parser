from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

import orchestrator.resume_orchestrator as orch
from tests.conftest import LLMStub
from tests.pdf_factory import (
    ALICE_RESUME,
    ANONYMOUS_RESUME,
    BOB_RESUME,
    CORRUPT_PDF,
    JOB_DESCRIPTION,
    NOT_A_PDF,
    SCANNED_RESUME,
    one_page,
)

ENDPOINT = "/api/v1/screenings"


def resume(name: str, content: bytes) -> tuple[str, tuple[str, bytes, str]]:
    return ("resumes", (name, content, "application/pdf"))


def jd(name: str = "Senior ML Platform Engineer.pdf", content: bytes = JOB_DESCRIPTION):
    return ("job_description_file", (name, content, "application/pdf"))


class TestHappyPath:
    @pytest.fixture
    def response(self, client: TestClient, llm: LLMStub):
        return client.post(
            ENDPOINT,
            files=[
                jd(),
                resume("alice_johnson.pdf", ALICE_RESUME),
                resume("bob_martinez.pdf", BOB_RESUME),
            ],
        )

    def test_succeeds(self, response) -> None:
        assert response.status_code == 200, response.text

    def test_reports_the_counts(self, response) -> None:
        body = response.json()

        assert body["totalUploaded"] == 2
        assert body["totalEvaluated"] == 2
        assert body["rejectedFiles"] == []

    def test_titles_the_position_from_the_job_description_filename(
        self, response
    ) -> None:
        assert response.json()["positionTitle"] == "Senior ML Platform Engineer"

    def test_maps_each_candidate_back_to_its_file(self, response) -> None:
        candidates = response.json()["candidates"]

        assert [c["candidateId"] for c in candidates] == ["cand-001", "cand-002"]
        assert [c["sourceFilename"] for c in candidates] == [
            "alice_johnson.pdf",
            "bob_martinez.pdf",
        ]
        assert all(c["resumeChars"] > 0 for c in candidates)

    def test_extracts_names_and_emails(self, response) -> None:
        candidates = response.json()["candidates"]

        assert candidates[0]["name"] == "Alice Johnson"
        assert candidates[0]["email"] == "alice.johnson@example.com"
        # "RESUME" heading skipped in favour of the name beneath it.
        assert candidates[1]["name"] == "Bob Martinez"
        assert candidates[1]["email"] == "bob.martinez@example.com"

    def test_returns_a_screening_per_candidate(self, response) -> None:
        results = response.json()["screeningResults"]

        assert [r["candidateId"] for r in results] == ["cand-001", "cand-002"]
        assert all(r["recommendation"] == "strong_yes" for r in results)

    def test_returns_a_ranking_per_candidate(self, response) -> None:
        ranking = response.json()["rankingOutput"]

        assert [e["candidateId"] for e in ranking["rankedCandidates"]] == [
            "cand-001",
            "cand-002",
        ]
        assert [e["rank"] for e in ranking["rankedCandidates"]] == [1, 2]
        assert ranking["topRecommendation"] == "top pick"

    def test_stamps_processed_at(self, response) -> None:
        assert response.json()["processedAt"].endswith("Z")

    def test_hands_the_job_description_to_the_model(
        self, response, llm: LLMStub
    ) -> None:
        assert response.status_code == 200
        assert all("LangChain" in text for text in llm.requirements)
        assert llm.ranked_titles == ["Senior ML Platform Engineer"]

    def test_hands_the_resume_text_to_the_model(self, response, llm: LLMStub) -> None:
        assert response.status_code == 200
        assert "distributed systems" in llm.screened[0].resumeText

    def test_stamps_the_position_on_each_candidate(
        self, response, llm: LLMStub
    ) -> None:
        assert response.status_code == 200
        assert all(
            c.appliedPosition == "Senior ML Platform Engineer" for c in llm.screened
        )


class TestJobDescriptionAsText:
    def test_accepts_plain_text(self, client: TestClient, llm: LLMStub) -> None:
        response = client.post(
            ENDPOINT,
            files=[resume("alice.pdf", ALICE_RESUME)],
            data={"job_description_text": "Python and LangChain required"},
        )

        assert response.status_code == 200, response.text
        assert llm.requirements == ["Python and LangChain required"]

    def test_falls_back_to_a_placeholder_title(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[resume("alice.pdf", ALICE_RESUME)],
            data={"job_description_text": "Python required"},
        )

        assert response.json()["positionTitle"] == "Unspecified Position"

    def test_an_explicit_title_wins(self, client: TestClient, llm: LLMStub) -> None:
        response = client.post(
            ENDPOINT,
            files=[resume("alice.pdf", ALICE_RESUME)],
            data={
                "job_description_text": "Python required",
                "position_title": "ML Engineer",
            },
        )

        assert response.json()["positionTitle"] == "ML Engineer"

    def test_an_explicit_title_overrides_the_filename(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[jd(), resume("alice.pdf", ALICE_RESUME)],
            data={"position_title": "Staff Engineer"},
        )

        assert response.json()["positionTitle"] == "Staff Engineer"

    def test_a_blank_title_is_ignored(self, client: TestClient, llm: LLMStub) -> None:
        response = client.post(
            ENDPOINT,
            files=[jd(), resume("alice.pdf", ALICE_RESUME)],
            data={"position_title": "   "},
        )

        assert response.json()["positionTitle"] == "Senior ML Platform Engineer"

    def test_whitespace_only_text_is_rejected(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[resume("alice.pdf", ALICE_RESUME)],
            data={"job_description_text": "    \n  "},
        )

        assert response.status_code == 422
        assert "job description is required" in response.json()["detail"]


class TestPartialSuccess:
    """An unreadable resume is reported, not fatal — the batch still completes."""

    @pytest.fixture
    def response(self, client: TestClient, llm: LLMStub):
        return client.post(
            ENDPOINT,
            files=[
                jd(),
                resume("alice_johnson.pdf", ALICE_RESUME),
                resume("scanned_cv.pdf", SCANNED_RESUME),
                resume("bob_martinez.pdf", BOB_RESUME),
                resume("notes.txt.pdf", NOT_A_PDF),
                resume("broken.pdf", CORRUPT_PDF),
            ],
        )

    def test_still_succeeds(self, response) -> None:
        assert response.status_code == 200, response.text

    def test_counts_distinguish_uploaded_from_evaluated(self, response) -> None:
        body = response.json()

        assert body["totalUploaded"] == 5
        assert body["totalEvaluated"] == 2

    def test_names_every_rejected_file_with_a_reason(self, response) -> None:
        rejected = response.json()["rejectedFiles"]

        assert [item["filename"] for item in rejected] == [
            "scanned_cv.pdf",
            "notes.txt.pdf",
            "broken.pdf",
        ]
        assert all(item["reason"] for item in rejected)
        assert "OCR" in rejected[0]["reason"]
        assert "Not a PDF" in rejected[1]["reason"]

    def test_ids_stay_contiguous_across_the_gaps(self, response) -> None:
        """Rejected files must not leave holes in the id sequence."""

        body = response.json()

        assert [c["candidateId"] for c in body["candidates"]] == [
            "cand-001",
            "cand-002",
        ]
        assert [c["sourceFilename"] for c in body["candidates"]] == [
            "alice_johnson.pdf",
            "bob_martinez.pdf",
        ]

    def test_only_readable_resumes_reach_the_model(
        self, response, llm: LLMStub
    ) -> None:
        assert response.status_code == 200
        assert llm.screened_names == ["Alice Johnson", "Bob Martinez"]

    def test_all_unreadable_resumes_fail_the_request(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[jd(), resume("scan.pdf", SCANNED_RESUME)],
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "readable text" in detail["message"]
        assert detail["rejectedFiles"][0]["filename"] == "scan.pdf"
        assert llm.screened == []


class TestScreeningFailures:
    def test_a_failed_candidate_comes_back_with_a_zero_score(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        llm.fail_screening_for = {"cand-002"}

        response = client.post(
            ENDPOINT,
            files=[
                jd(),
                resume("alice.pdf", ALICE_RESUME),
                resume("bob.pdf", BOB_RESUME),
            ],
        )

        assert response.status_code == 200, response.text
        results = {r["candidateId"]: r for r in response.json()["screeningResults"]}

        assert results["cand-001"]["score"] == 88.0
        assert results["cand-002"]["score"] == 0.0
        assert results["cand-002"]["concerns"]

    def test_a_ranking_failure_is_a_bad_gateway(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        llm.fail_ranking = True

        response = client.post(
            ENDPOINT,
            files=[jd(), resume("alice.pdf", ALICE_RESUME)],
        )

        assert response.status_code == 502
        assert "ranking" in response.json()["detail"]


class TestRequestValidation:
    def test_a_missing_job_description_is_rejected(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(ENDPOINT, files=[resume("alice.pdf", ALICE_RESUME)])

        assert response.status_code == 422
        assert "job description is required" in response.json()["detail"]

    def test_supplying_both_job_description_forms_is_rejected(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[jd(), resume("alice.pdf", ALICE_RESUME)],
            data={"job_description_text": "also text"},
        )

        assert response.status_code == 422
        assert "not both" in response.json()["detail"]

    def test_no_resumes_at_all_is_rejected(self, client: TestClient) -> None:
        response = client.post(ENDPOINT, data={"job_description_text": "Python"})

        # FastAPI rejects the missing required field before the handler runs.
        assert response.status_code == 422

    def test_an_unreadable_job_description_is_rejected(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[
                jd("scan.pdf", SCANNED_RESUME),
                resume("alice.pdf", ALICE_RESUME),
            ],
        )

        assert response.status_code == 422
        assert "Could not read job description 'scan.pdf'" in response.json()["detail"]
        assert llm.screened == []

    def test_too_many_resumes_is_rejected(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        client = make_client(max_resume_files=2)

        response = client.post(
            ENDPOINT,
            files=[
                jd(),
                resume("a.pdf", ALICE_RESUME),
                resume("b.pdf", BOB_RESUME),
                resume("c.pdf", ALICE_RESUME),
            ],
        )

        assert response.status_code == 422
        assert "Too many resumes: 3" in response.json()["detail"]
        assert "maximum per request is 2" in response.json()["detail"]

    def test_the_limit_itself_is_allowed(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        client = make_client(max_resume_files=2)

        response = client.post(
            ENDPOINT,
            files=[jd(), resume("a.pdf", ALICE_RESUME), resume("b.pdf", BOB_RESUME)],
        )

        assert response.status_code == 200, response.text

    def test_an_oversized_resume_is_rejected(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        big = one_page(["padding " * 5000])
        limit_mb = (len(big) - 1) / (1024 * 1024)
        client = make_client(max_file_size_mb=limit_mb)

        response = client.post(ENDPOINT, files=[jd(), resume("big.pdf", big)])

        assert response.status_code == 413
        assert "exceeds the maximum upload size" in response.json()["detail"]

    def test_an_oversized_job_description_is_rejected(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        big = one_page(["padding " * 5000])
        limit_mb = (len(big) - 1) / (1024 * 1024)
        client = make_client(max_file_size_mb=limit_mb)

        response = client.post(
            ENDPOINT,
            files=[jd("big.pdf", big), resume("alice.pdf", ALICE_RESUME)],
        )

        assert response.status_code == 413
        assert "Job description 'big.pdf'" in response.json()["detail"]


class TestFilenameHandling:
    def test_a_path_in_the_filename_is_reduced_to_its_basename(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[jd(), resume("../../../../etc/passwd.pdf", ALICE_RESUME)],
        )

        assert response.status_code == 200, response.text
        assert response.json()["candidates"][0]["sourceFilename"] == "passwd.pdf"

    def test_a_rejected_files_entry_is_also_sanitised(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[
                jd(),
                resume("alice.pdf", ALICE_RESUME),
                resume(r"C:\Users\someone\scan.pdf", SCANNED_RESUME),
            ],
        )

        assert response.json()["rejectedFiles"][0]["filename"] == "scan.pdf"

    def test_the_filename_is_the_name_fallback(
        self, client: TestClient, llm: LLMStub
    ) -> None:
        response = client.post(
            ENDPOINT,
            files=[jd(), resume("carol_danvers.pdf", ANONYMOUS_RESUME)],
        )

        candidate = response.json()["candidates"][0]
        assert candidate["name"] == "carol danvers"
        assert candidate["email"] == ""


class TestTruncationLimits:
    def test_a_long_resume_is_truncated_before_reaching_the_model(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        client = make_client(max_resume_chars=200)

        response = client.post(
            ENDPOINT,
            files=[jd(), resume("long.pdf", one_page(["filler " * 2000]))],
        )

        assert response.status_code == 200, response.text
        assert llm.screened[0].resumeText.endswith("[truncated]")
        assert response.json()["candidates"][0]["resumeChars"] < 300

    def test_a_long_job_description_is_truncated(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        client = make_client(max_job_description_chars=150)

        response = client.post(
            ENDPOINT,
            files=[resume("alice.pdf", ALICE_RESUME)],
            data={"job_description_text": "requirement " * 500},
        )

        assert response.status_code == 200, response.text
        assert response.json()["jobDescriptionChars"] < 250
        assert llm.requirements[0].endswith("[truncated]")

    def test_pages_beyond_the_limit_are_ignored(
        self, make_client: Callable[..., TestClient], llm: LLMStub
    ) -> None:
        from tests.pdf_factory import make_pdf

        client = make_client(max_pdf_pages=1)
        pdf = make_pdf([["Alice Johnson"], ["second page marker"]])

        response = client.post(ENDPOINT, files=[jd(), resume("alice.pdf", pdf)])

        assert response.status_code == 200, response.text
        assert "second page marker" not in llm.screened[0].resumeText


class TestProviderConfiguration:
    def test_a_missing_api_key_is_service_unavailable(
        self, make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The real model factory runs here, so the missing key surfaces as 503
        rather than a 500 from the provider client."""

        monkeypatch.setattr(orch, "screen_candidate", None)
        client = make_client(openrouter_api_key="")

        response = client.post(
            ENDPOINT, files=[jd(), resume("alice.pdf", ALICE_RESUME)]
        )

        assert response.status_code == 503
        assert "OPENROUTER_API_KEY" in response.json()["detail"]


class TestHealth:
    def test_reports_configuration(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert set(body) == {
            "status",
            "app",
            "environment",
            "model",
            "llmConfigured",
        }


class TestOpenApiContract:
    def test_documents_the_multipart_fields(self, client: TestClient) -> None:
        spec = client.get("/openapi.json").json()

        assert ENDPOINT in spec["paths"]

        body = spec["paths"][ENDPOINT]["post"]["requestBody"]
        assert "multipart/form-data" in body["content"]

        schema_ref = body["content"]["multipart/form-data"]["schema"]["$ref"]
        schema = spec["components"]["schemas"][schema_ref.rsplit("/", 1)[-1]]

        assert set(schema["properties"]) == {
            "resumes",
            "job_description_file",
            "job_description_text",
            "position_title",
        }
        assert schema["required"] == ["resumes"]
