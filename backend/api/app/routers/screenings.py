from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.config import (
    LLMNotConfiguredError,
    Settings,
    build_chat_model,
    get_settings,
)
from app.pdf_text import PdfExtractionError, extract_pdf_text, normalize_text
from app.resume_intake import (
    filename_stem,
    guess_email,
    guess_name,
    make_candidate_id,
    safe_filename,
)
from app.schemas import (
    CandidateSummary,
    RejectedFile,
    ScreeningResponse,
)
from orchestrator.resume_orchestrator import Candidate, run_screening_pipeline

router = APIRouter(prefix="/api/v1", tags=["screenings"])

READ_CHUNK_SIZE = 64 * 1024

# Spelled out as integers because Starlette renamed the 413/422 constants
# (REQUEST_ENTITY_TOO_LARGE -> CONTENT_TOO_LARGE, UNPROCESSABLE_ENTITY ->
# UNPROCESSABLE_CONTENT); either name warns or is missing depending on version.
HTTP_413_TOO_LARGE = 413
HTTP_422_UNPROCESSABLE = 422


async def _read_limited(upload: UploadFile, limit: int, label: str) -> bytes:
    """Read an upload, refusing anything over `limit` bytes.

    Read in chunks rather than trusting `UploadFile.size`, which is only as
    reliable as the client's multipart headers.
    """

    chunks: list[bytes] = []
    total = 0

    while chunk := await upload.read(READ_CHUNK_SIZE):
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=HTTP_413_TOO_LARGE,
                detail=(
                    f"{label} exceeds the maximum upload size of "
                    f"{limit // (1024 * 1024)} MB"
                ),
            )
        chunks.append(chunk)

    return b"".join(chunks)


def _is_present(upload: UploadFile | None) -> bool:
    """Browsers can submit an empty file part; treat that as 'not provided'."""

    return upload is not None and bool(upload.filename)


@router.post(
    "/screenings",
    response_model=ScreeningResponse,
    status_code=status.HTTP_200_OK,
    summary="Screen and rank a batch of resume PDFs against a job description",
)
async def create_screening(
    resumes: Annotated[
        list[UploadFile],
        File(description="One or more candidate resumes, as PDF files."),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    job_description_file: Annotated[
        UploadFile | None,
        File(description="The job description as a PDF file."),
    ] = None,
    job_description_text: Annotated[
        str | None,
        Form(description="The job description as plain text, instead of a PDF."),
    ] = None,
    position_title: Annotated[
        str | None,
        Form(description="Defaults to the job description filename."),
    ] = None,
) -> ScreeningResponse:
    """Replaces the version 2 job-board fetch with a direct upload.

    Extracts text from the uploaded PDFs, turns each resume into a `Candidate`,
    and hands the batch to the existing screen-then-rank pipeline.
    """

    # -----------------------------------------------------------------------
    # Validate the request shape
    # -----------------------------------------------------------------------

    present_resumes = [upload for upload in resumes if _is_present(upload)]

    if not present_resumes:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail="At least one resume PDF is required.",
        )

    if len(present_resumes) > settings.max_resume_files:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail=(
                f"Too many resumes: {len(present_resumes)}. "
                f"The maximum per request is {settings.max_resume_files}."
            ),
        )

    has_jd_file = _is_present(job_description_file)
    has_jd_text = bool(job_description_text and job_description_text.strip())

    if has_jd_file and has_jd_text:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail=(
                "Provide either 'job_description_file' or 'job_description_text', "
                "not both."
            ),
        )

    if not has_jd_file and not has_jd_text:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail=(
                "A job description is required: send 'job_description_file' "
                "(PDF) or 'job_description_text'."
            ),
        )

    # -----------------------------------------------------------------------
    # 1. Job description -> requirements text
    # -----------------------------------------------------------------------

    if has_jd_file:
        assert job_description_file is not None  # narrowed by has_jd_file
        jd_filename = safe_filename(job_description_file.filename)
        jd_bytes = await _read_limited(
            job_description_file,
            settings.max_file_size_bytes,
            f"Job description '{jd_filename}'",
        )

        try:
            position_requirements = extract_pdf_text(
                jd_bytes,
                max_pages=settings.max_pdf_pages,
                max_chars=settings.max_job_description_chars,
            )
        except PdfExtractionError as error:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE,
                detail=f"Could not read job description '{jd_filename}': {error}",
            ) from error

        default_title = filename_stem(jd_filename)
    else:
        assert job_description_text is not None  # narrowed by has_jd_text
        position_requirements = normalize_text(
            job_description_text,
            max_chars=settings.max_job_description_chars,
        )
        default_title = "Unspecified Position"

        if not position_requirements:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE,
                detail="'job_description_text' is empty.",
            )

    resolved_title = (position_title or "").strip() or default_title

    # -----------------------------------------------------------------------
    # 2. Resume PDFs -> Candidate records
    # -----------------------------------------------------------------------

    application_date = datetime.now(timezone.utc).date().isoformat()

    candidates: list[Candidate] = []
    summaries: list[CandidateSummary] = []
    rejected: list[RejectedFile] = []

    for upload in present_resumes:
        filename = safe_filename(upload.filename)

        resume_bytes = await _read_limited(
            upload,
            settings.max_file_size_bytes,
            f"Resume '{filename}'",
        )

        try:
            resume_text = extract_pdf_text(
                resume_bytes,
                max_pages=settings.max_pdf_pages,
                max_chars=settings.max_resume_chars,
            )
        except PdfExtractionError as error:
            # One unreadable resume should not fail the whole batch; it is
            # reported back so the client can re-upload or follow up manually.
            rejected.append(RejectedFile(filename=filename, reason=str(error)))
            continue

        candidate_id = make_candidate_id(len(candidates) + 1)
        name = guess_name(resume_text, fallback=filename_stem(filename))
        email = guess_email(resume_text)

        candidates.append(
            Candidate(
                candidateId=candidate_id,
                name=name,
                email=email,
                resumeText=resume_text,
                appliedPosition=resolved_title,
                applicationDate=application_date,
            )
        )
        summaries.append(
            CandidateSummary(
                candidateId=candidate_id,
                name=name,
                email=email,
                sourceFilename=filename,
                resumeChars=len(resume_text),
            )
        )

    if not candidates:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail={
                "message": "None of the uploaded resumes contained readable text.",
                "rejectedFiles": [item.model_dump() for item in rejected],
            },
        )

    # -----------------------------------------------------------------------
    # 3. Hand off to the existing screen-then-rank pipeline
    # -----------------------------------------------------------------------

    try:
        model = build_chat_model(settings)
    except LLMNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    try:
        pipeline_result = await run_screening_pipeline(
            candidates,
            resolved_title,
            position_requirements,
            model,
            concurrency=settings.screening_concurrency,
            delay_seconds=settings.screening_delay_seconds,
            continue_on_error=True,
        )
    except Exception as error:
        # Screening failures are absorbed per candidate, so reaching here means
        # the ranking call itself failed or the provider was unreachable.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"The model provider failed to complete the ranking: {error}",
        ) from error

    return ScreeningResponse(
        positionTitle=resolved_title,
        jobDescriptionChars=len(position_requirements),
        totalUploaded=len(present_resumes),
        totalEvaluated=len(candidates),
        candidates=summaries,
        rejectedFiles=rejected,
        screeningResults=[
            result.model_dump() for result in pipeline_result["screeningResults"]
        ],
        rankingOutput=pipeline_result["rankingOutput"],
        processedAt=pipeline_result["processedAt"],
    )
