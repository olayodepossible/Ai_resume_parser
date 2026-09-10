from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Section headings that sit above or beside the name on resume templates.
_HEADING_WORDS = {
    "achievements",
    "awards",
    "certifications",
    "confidential",
    "contact",
    "curriculum",
    "curriculumvitae",
    "cv",
    "details",
    "education",
    "employment",
    "experience",
    "history",
    "information",
    "interests",
    "languages",
    "objective",
    "personal",
    "profile",
    "projects",
    "publications",
    "qualifications",
    "references",
    "resume",
    "résumé",
    "skills",
    "summary",
    "vitae",
    "work",
}

# Lowercase particles that legitimately appear inside a name.
_NAME_PARTICLES = {
    "al",
    "bin",
    "binte",
    "da",
    "de",
    "del",
    "della",
    "di",
    "du",
    "ibn",
    "la",
    "le",
    "van",
    "von",
    "y",
}

_NAME_CHARS = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ'’.\- ]+$")


def safe_filename(raw: str | None) -> str:
    """Reduce a client-supplied filename to its bare name, dropping any path."""

    if not raw:
        return "unnamed.pdf"

    # Browsers normally send a bare name, but a crafted request can send a path.
    name = PureWindowsPath(PurePosixPath(raw).name).name.strip()
    name = name.replace("\x00", "")

    return name or "unnamed.pdf"


def filename_stem(filename: str) -> str:
    stem = PurePosixPath(filename).stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or filename


def guess_email(resume_text: str) -> str:
    match = EMAIL_RE.search(resume_text)
    return match.group(0) if match else ""


def guess_name(resume_text: str, fallback: str) -> str:
    """Best-effort candidate name from the top of a resume.

    Deliberately conservative: it only accepts a line that clearly looks like a
    person's name, otherwise it falls back to the uploaded filename. The name is
    only used to address the candidate in the screening prompt, so a wrong guess
    is cosmetic rather than load-bearing.
    """

    for line in resume_text.split("\n")[:12]:
        candidate = line.strip().strip("|•·–—-").strip()

        if not 2 <= len(candidate) <= 60:
            continue
        if not _NAME_CHARS.match(candidate):
            continue
        # A trailing period marks a sentence; in a name it only follows an
        # initial, which is never the last word.
        if candidate.endswith("."):
            continue

        words = candidate.split()
        if not 1 < len(words) <= 4:
            continue
        if any(word.strip(".'’-").lower() in _HEADING_WORDS for word in words):
            continue
        # Every word must be capitalised, bar the handful of particles that are
        # genuinely lowercase. This is what separates "Alice Johnson" from a
        # short sentence like "Built pipelines in Scala".
        if not all(
            word[0].isupper() or word.lower() in _NAME_PARTICLES for word in words
        ):
            continue

        return candidate

    return fallback


def make_candidate_id(index: int) -> str:
    """Short, ordered ids.

    Deliberately human-shaped: the ranking step asks the model to echo these ids
    back, and it reproduces `cand-001` far more reliably than a random hash.
    """

    return f"cand-{index:03d}"
