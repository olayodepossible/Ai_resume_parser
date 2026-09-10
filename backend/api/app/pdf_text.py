from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"

_HORIZONTAL_WS = re.compile(r"[ \t\x0b\f\r]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")


class PdfExtractionError(ValueError):
    """A PDF could not be turned into usable text."""


def looks_like_pdf(data: bytes) -> bool:
    """True if the header appears in the first KB (some PDFs carry leading junk)."""

    return PDF_MAGIC in data[:1024]


def normalize_text(raw: str, *, max_chars: int) -> str:
    text = _CONTROL_CHARS.sub("", raw)
    text = _HORIZONTAL_WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text).strip()

    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n[truncated]"

    return text


def extract_pdf_text(data: bytes, *, max_pages: int, max_chars: int) -> str:
    """Extract plain text from a PDF's bytes.

    Raises `PdfExtractionError` for anything unusable: a non-PDF payload, a
    corrupt file, a password-protected file, or a scanned document with no text
    layer. Callers report these per-file rather than failing the whole batch.
    """

    if not data:
        raise PdfExtractionError("File is empty")

    if not looks_like_pdf(data):
        raise PdfExtractionError("Not a PDF file (missing %PDF- header)")

    try:
        reader = PdfReader(io.BytesIO(data))
    except (PdfReadError, OSError, ValueError) as exc:
        raise PdfExtractionError(f"Could not read PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            # An empty password unlocks PDFs that are encrypted but not
            # password-gated. NOT_DECRYPTED is falsy.
            unlocked = reader.decrypt("")
        except Exception as exc:
            raise PdfExtractionError(f"Could not decrypt PDF: {exc}") from exc
        if not unlocked:
            raise PdfExtractionError("PDF is password protected")

    try:
        pages = reader.pages[:max_pages]
    except (PdfReadError, ValueError) as exc:
        raise PdfExtractionError(f"Could not read PDF pages: {exc}") from exc

    chunks: list[str] = []
    for page in pages:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            # One unreadable page should not discard the rest of the document.
            continue

    text = normalize_text("\n\n".join(chunks), max_chars=max_chars)

    if not text:
        raise PdfExtractionError(
            "No extractable text — the PDF is likely a scan or image, which needs OCR"
        )

    return text
