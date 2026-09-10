"""A minimal PDF writer, so tests can exercise real extraction.

Hand-rolled rather than pulled from a library: the suite needs a handful of
small documents with known text, plus deliberately broken ones, and writing the
few hundred bytes of PDF directly avoids a dependency that only tests would use.
"""

from __future__ import annotations

from collections.abc import Sequence


def _content_stream(lines: Sequence[str]) -> bytes:
    content = "BT /F1 12 Tf 72 720 Td 14 TL\n"

    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", r"\(").replace(")", r"\)")
        content += f"({escaped}) Tj T*\n"

    content += "ET"

    return content.encode("latin-1")


def make_pdf(pages: Sequence[Sequence[str]]) -> bytes:
    """Build a valid PDF with one text block per page.

    A page with no lines produces a page with no text operators, which is how
    an image-only scan behaves: readable structure, nothing to extract.
    """

    if not pages:
        raise ValueError("A PDF needs at least one page")

    page_count = len(pages)
    font_obj = 3 + 2 * page_count

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            "<< /Type /Pages /Kids ["
            + " ".join(f"{3 + i} 0 R" for i in range(page_count))
            + f"] /Count {page_count} >>"
        ).encode(),
    ]

    for index in range(page_count):
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_obj} 0 R >> >> "
                f"/Contents {3 + page_count + index} 0 R >>"
            ).encode()
        )

    for lines in pages:
        stream = _content_stream(lines)
        objects.append(
            b"<< /Length "
            + str(len(stream)).encode()
            + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )

    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []

    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_offset = len(out)
    size = len(objects) + 1

    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {size} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode()

    return bytes(out)


def one_page(lines: Sequence[str]) -> bytes:
    return make_pdf([lines])


# --- Fixture documents -----------------------------------------------------

ALICE_RESUME = one_page(
    [
        "Alice Johnson",
        "alice.johnson@example.com | +1 555 0100",
        "",
        "SUMMARY",
        "Senior Software Engineer, 8 years in Python and distributed systems.",
        "Proficient in LangChain, AWS, Docker and Kubernetes.",
    ]
)

# Leads with a section heading, to check the name heuristic skips it.
BOB_RESUME = one_page(
    [
        "RESUME",
        "Bob Martinez",
        "bob.martinez@example.com",
        "",
        "Full-stack developer, 5 years TypeScript and Node.js.",
    ]
)

# No contact details and no name-shaped line: forces the filename fallback.
ANONYMOUS_RESUME = one_page(
    [
        "PROFESSIONAL EXPERIENCE 2019-2024",
        "Built data pipelines in Scala and Spark for a payments team.",
    ]
)

JOB_DESCRIPTION = one_page(
    [
        "Senior ML Platform Engineer",
        "We need strong Python, LangChain experience and AWS infrastructure skills.",
    ]
)

# Structurally valid, no text layer — what a scanned resume looks like.
SCANNED_RESUME = one_page([])

NOT_A_PDF = b"this is plainly not a pdf"

CORRUPT_PDF = b"%PDF-1.4\nthis header lies; there is no body or xref here"
