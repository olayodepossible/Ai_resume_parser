from __future__ import annotations

import pytest

from app.resume_intake import (
    filename_stem,
    guess_email,
    guess_name,
    make_candidate_id,
    safe_filename,
)


class TestSafeFilename:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("resume.pdf", "resume.pdf"),
            ("  resume.pdf  ", "resume.pdf"),
            # A browser sends a bare name; a crafted request need not.
            ("/etc/passwd", "passwd"),
            ("../../../../etc/passwd", "passwd"),
            (r"C:\Users\someone\resume.pdf", "resume.pdf"),
            ("subdir/nested/resume.pdf", "resume.pdf"),
            ("resu\x00me.pdf", "resume.pdf"),
            (None, "unnamed.pdf"),
            ("", "unnamed.pdf"),
            ("   ", "unnamed.pdf"),
        ],
    )
    def test_reduces_to_a_bare_name(self, raw: str | None, expected: str) -> None:
        assert safe_filename(raw) == expected

    def test_never_returns_a_path_separator(self) -> None:
        for raw in ["a/b/c.pdf", r"a\b\c.pdf", "../x.pdf"]:
            result = safe_filename(raw)
            assert "/" not in result
            assert "\\" not in result


class TestFilenameStem:
    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("alice_johnson.pdf", "alice johnson"),
            ("bob-martinez.pdf", "bob martinez"),
            ("Senior ML Platform Engineer.pdf", "Senior ML Platform Engineer"),
            ("a__b--c.pdf", "a b c"),
            ("resume.PDF", "resume"),
        ],
    )
    def test_prettifies(self, filename: str, expected: str) -> None:
        assert filename_stem(filename) == expected


class TestGuessEmail:
    def test_finds_an_email(self) -> None:
        assert guess_email("Alice Johnson\nalice.johnson@example.com") == (
            "alice.johnson@example.com"
        )

    def test_returns_the_first_of_several(self) -> None:
        text = "first@example.com and second@example.com"
        assert guess_email(text) == "first@example.com"

    def test_handles_plus_addressing_and_hyphens(self) -> None:
        assert guess_email("a.b+tag@sub-domain.example.co.uk") == (
            "a.b+tag@sub-domain.example.co.uk"
        )

    def test_returns_empty_when_absent(self) -> None:
        assert guess_email("Alice Johnson\nno contact details here") == ""


class TestGuessName:
    def test_takes_a_name_shaped_first_line(self) -> None:
        assert guess_name("Alice Johnson\nalice@example.com", "fallback") == (
            "Alice Johnson"
        )

    def test_skips_a_leading_section_heading(self) -> None:
        text = "RESUME\nBob Martinez\nbob@example.com"
        assert guess_name(text, "fallback") == "Bob Martinez"

    @pytest.mark.parametrize(
        "heading",
        ["Curriculum Vitae", "Personal Details", "Contact Information"],
    )
    def test_skips_common_headings(self, heading: str) -> None:
        assert guess_name(f"{heading}\nCarol Danvers", "fallback") == "Carol Danvers"

    def test_skips_lines_containing_an_email(self) -> None:
        text = "alice@example.com\nAlice Johnson"
        assert guess_name(text, "fallback") == "Alice Johnson"

    def test_skips_lines_containing_digits(self) -> None:
        text = "+1 555 0100\nAlice Johnson"
        assert guess_name(text, "fallback") == "Alice Johnson"

    def test_strips_bullet_and_pipe_decoration(self) -> None:
        assert guess_name("| Alice Johnson |", "fallback") == "Alice Johnson"

    def test_accepts_accents_and_apostrophes(self) -> None:
        assert guess_name("Renée O'Brien", "fallback") == "Renée O'Brien"

    def test_rejects_a_single_word(self) -> None:
        # One word is as likely to be a heading as a name, so it is not trusted.
        assert guess_name("Engineering\n", "fallback") == "fallback"

    def test_rejects_a_long_prose_line(self) -> None:
        text = "Experienced engineer who has built many production systems"
        assert guess_name(text, "fallback") == "fallback"

    @pytest.mark.parametrize(
        "sentence",
        [
            "Built pipelines in Scala.",
            "Led a platform team",
            "Managed the deployment process",
        ],
    )
    def test_rejects_a_short_sentence(self, sentence: str) -> None:
        """A few capitalised-first-word words is a sentence, not a name; only
        a line where every word is capitalised is trusted."""

        assert guess_name(sentence, "fallback") == "fallback"

    def test_accepts_an_all_caps_name(self) -> None:
        assert guess_name("ALICE JOHNSON\nalice@example.com", "fallback") == (
            "ALICE JOHNSON"
        )

    @pytest.mark.parametrize(
        "name",
        ["Alice van Dijk", "Ludwig von Mises", "Maria de la Cruz", "Omar bin Salim"],
    )
    def test_accepts_lowercase_name_particles(self, name: str) -> None:
        assert guess_name(name, "fallback") == name

    @pytest.mark.parametrize(
        "heading", ["WORK EXPERIENCE", "Technical Skills", "Education History"]
    )
    def test_rejects_a_two_word_section_heading(self, heading: str) -> None:
        assert guess_name(heading, "fallback") == "fallback"

    def test_falls_back_when_nothing_looks_like_a_name(self) -> None:
        text = "PROFESSIONAL EXPERIENCE 2019-2024\nBuilt pipelines in Scala."
        assert guess_name(text, "alice johnson") == "alice johnson"

    def test_only_considers_the_top_of_the_document(self) -> None:
        text = "\n".join(["EXPERIENCE 1"] * 20 + ["Alice Johnson"])
        assert guess_name(text, "fallback") == "fallback"


class TestCandidateId:
    def test_is_zero_padded_and_ordered(self) -> None:
        assert make_candidate_id(1) == "cand-001"
        assert make_candidate_id(25) == "cand-025"

    def test_sorts_lexicographically_within_a_batch(self) -> None:
        ids = [make_candidate_id(i) for i in range(1, 12)]
        assert ids == sorted(ids)
