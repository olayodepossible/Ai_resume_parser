from __future__ import annotations

import pytest

from app.pdf_text import (
    PdfExtractionError,
    extract_pdf_text,
    looks_like_pdf,
    normalize_text,
)
from tests.pdf_factory import (
    ALICE_RESUME,
    CORRUPT_PDF,
    JOB_DESCRIPTION,
    NOT_A_PDF,
    SCANNED_RESUME,
    make_pdf,
    one_page,
)

DEFAULTS = {"max_pages": 30, "max_chars": 20_000}


class TestExtract:
    def test_extracts_resume_text(self) -> None:
        text = extract_pdf_text(ALICE_RESUME, **DEFAULTS)

        assert "Alice Johnson" in text
        assert "alice.johnson@example.com" in text
        assert "LangChain" in text

    def test_extracts_job_description(self) -> None:
        text = extract_pdf_text(JOB_DESCRIPTION, **DEFAULTS)

        assert "Senior ML Platform Engineer" in text
        assert "AWS infrastructure" in text

    def test_reads_every_page(self) -> None:
        pdf = make_pdf([["page one text"], ["page two text"], ["page three text"]])

        text = extract_pdf_text(pdf, **DEFAULTS)

        assert "page one text" in text
        assert "page two text" in text
        assert "page three text" in text

    def test_stops_at_max_pages(self) -> None:
        pdf = make_pdf([["page one text"], ["page two text"], ["page three text"]])

        text = extract_pdf_text(pdf, max_pages=2, max_chars=20_000)

        assert "page two text" in text
        assert "page three text" not in text

    def test_truncates_at_max_chars(self) -> None:
        pdf = one_page(["A" * 500])

        text = extract_pdf_text(pdf, max_pages=30, max_chars=100)

        assert text.endswith("[truncated]")
        assert len(text) < 200


class TestRejections:
    """Every unusable input must surface as PdfExtractionError.

    The endpoint relies on this single exception type to decide what belongs in
    `rejectedFiles` rather than aborting the batch.
    """

    def test_empty_bytes(self) -> None:
        with pytest.raises(PdfExtractionError, match="empty"):
            extract_pdf_text(b"", **DEFAULTS)

    def test_not_a_pdf(self) -> None:
        with pytest.raises(PdfExtractionError, match="Not a PDF"):
            extract_pdf_text(NOT_A_PDF, **DEFAULTS)

    def test_corrupt_pdf(self) -> None:
        with pytest.raises(PdfExtractionError):
            extract_pdf_text(CORRUPT_PDF, **DEFAULTS)

    def test_scanned_pdf_without_text_layer(self) -> None:
        with pytest.raises(PdfExtractionError, match="OCR"):
            extract_pdf_text(SCANNED_RESUME, **DEFAULTS)


class TestLooksLikePdf:
    def test_accepts_leading_junk_before_header(self) -> None:
        assert looks_like_pdf(b"\n\n   " + ALICE_RESUME)

    def test_rejects_header_beyond_the_first_kilobyte(self) -> None:
        assert not looks_like_pdf(b"x" * 2000 + b"%PDF-1.4")


class TestNormalizeText:
    def test_collapses_horizontal_whitespace(self) -> None:
        assert normalize_text("a \t  b", max_chars=100) == "a b"

    def test_collapses_runs_of_blank_lines(self) -> None:
        assert normalize_text("a\n\n\n\n\nb", max_chars=100) == "a\n\nb"

    def test_strips_control_characters(self) -> None:
        assert normalize_text("a\x00\x07b", max_chars=100) == "ab"

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert normalize_text("  \n a \n  ", max_chars=100) == "a"

    def test_leaves_short_text_untouched(self) -> None:
        assert normalize_text("Python and LangChain", max_chars=100) == (
            "Python and LangChain"
        )
