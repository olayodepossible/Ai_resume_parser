import asyncio
import os
from typing import Any

import httpx
from pydantic import BaseModel, EmailStr, ValidationError


# -------------------
# Configuration
# --------------------

JOB_BOARD_API_BASE = os.getenv(
    "JOB_BOARD_API_URL",
    "https://api.jobboard.example.com",
)

JOB_BOARD_API_KEY = os.getenv(
    "JOB_BOARD_API_KEY",
    "",
)

DEFAULT_TIMEOUT_MS = 15000
MAX_RETRIES = 3


# ----------------
# Data Models
# ----------------

class RawApplication(BaseModel):
    id: str
    applicant_name: str
    applicant_email: EmailStr
    resume_content: str
    position_title: str
    submitted_at: str
    status: str | None = None
    source: str | None = None


class RawPosition(BaseModel):
    id: str
    title: str
    department: str
    description: str
    requirements: str
    posted_at: str
    closing_date: str | None = None
    headcount: int | None = None


class ApplicationsResponse(BaseModel):
    applications: list[Any]
    total: int
    page: int
    page_size: int
    has_more: bool | None = None


class PositionResponse(BaseModel):
    position: RawPosition


class ApplicationsPage(BaseModel):
    applications: list[RawApplication]
    total: int
    page: int
    pageSize: int
    hasMore: bool


class JobBoardClientConfig(BaseModel):
    baseUrl: str | None = None
    apiKey: str | None = None
    timeoutMs: int | None = None
    maxRetries: int | None = None


# ---------------------------------------------------------------------------
# Custom API Error
# ---------------------------------------------------------------------------

class JobBoardApiError(Exception):

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: Any = None,
    ):
        super().__init__(message)

        self.status_code = status_code
        self.response_body = response_body


# -------------------------
# HTTP Client Builder
# -------------------------

def build_http_client(
    base_url: str,
    api_key: str,
    timeout_ms: int,
) -> httpx.AsyncClient:

    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout_ms / 1000,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )


# --------------------------
# Retry Helper
# --------------------------

async def with_retry(
    operation,
    max_retries: int,
    operation_name: str,
):
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):

        try:
            return await operation()

        except httpx.HTTPStatusError as error:

            response = error.response
            status = response.status_code

            # Do not retry normal 4xx client errors,
            # except HTTP 429 Too Many Requests.
            if 400 <= status < 500 and status != 429:

                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text

                raise JobBoardApiError(
                    (
                        f"{operation_name} failed with client error: "
                        f"{error}"
                    ),
                    status_code=status,
                    response_body=response_body,
                ) from error

            last_error = error

        except Exception as error:
            last_error = error

        if attempt < max_retries:

            # Exponential backoff:
            #
            # attempt 1 -> 0.5 seconds
            # attempt 2 -> 1.0 seconds
            # attempt 3 -> 2.0 seconds
            #
            delay_seconds = (
                (2 ** (attempt - 1)) * 0.5
            )

            await asyncio.sleep(delay_seconds)

            print(
                f"Retrying {operation_name} "
                f"(attempt {attempt + 1}/{max_retries})"
            )

    raise JobBoardApiError(
        (
            f"{operation_name} failed after "
            f"{max_retries} attempts: "
            f"{last_error}"
        )
    )


# ---------------------------------------------------------------------------
# Job Board API Client
# ---------------------------------------------------------------------------

class JobBoardClient:

    def __init__(
        self,
        config: JobBoardClientConfig | None = None,
    ):
        config = config or JobBoardClientConfig()

        self.base_url = (
            config.baseUrl
            or JOB_BOARD_API_BASE
        )

        self.api_key = (
            config.apiKey
            if config.apiKey is not None
            else JOB_BOARD_API_KEY
        )

        self.timeout_ms = (
            config.timeoutMs
            if config.timeoutMs is not None
            else DEFAULT_TIMEOUT_MS
        )

        self.max_retries = (
            config.maxRetries
            if config.maxRetries is not None
            else MAX_RETRIES
        )

        self.http_client = build_http_client(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout_ms=self.timeout_ms,
        )

    # -----------------------------------------------------------------------
    # Fetch one applications page
    # -----------------------------------------------------------------------

    async def fetch_applications_page(
        self,
        position_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> ApplicationsPage:

        async def operation():
            response = await self.http_client.get(
                f"/positions/{position_id}/applications",
                params={
                    "page": page,
                    "page_size": page_size,
                },
            )

            response.raise_for_status()

            return response

        response = await with_retry(
            operation,
            self.max_retries,
            (
                "fetchApplicationsPage"
                f"(positionId={position_id}, "
                f"page={page})"
            ),
        )

        # ---------------------------------------------------------------
        # Validate overall API response
        # ---------------------------------------------------------------

        try:
            parsed = ApplicationsResponse.model_validate(
                response.json()
            )

        except ValidationError as error:

            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            raise JobBoardApiError(
                (
                    "Unexpected response shape from "
                    "applications endpoint: "
                    f"{error}"
                ),
                status_code=response.status_code,
                response_body=response_body,
            ) from error

        # ---------------------------------------------------------------
        # Validate individual applications
        # ---------------------------------------------------------------

        valid_applications: list[
            RawApplication
        ] = []

        for raw in parsed.applications:

            try:
                application = (
                    RawApplication.model_validate(raw)
                )

                valid_applications.append(
                    application
                )

            except ValidationError as error:

                print(
                    "Skipping malformed application "
                    f"record: {error}"
                )

        has_more = (
            parsed.has_more
            if parsed.has_more is not None
            else len(valid_applications) == page_size
        )

        return ApplicationsPage(
            applications=valid_applications,
            total=parsed.total,
            page=parsed.page,
            pageSize=parsed.page_size,
            hasMore=has_more,
        )

    # -----------------------------------------------------------------------
    # Fetch all applications using pagination
    # -----------------------------------------------------------------------

    async def fetch_all_applications(
        self,
        position_id: str,
    ) -> list[RawApplication]:

        all_applications: list[
            RawApplication
        ] = []

        current_page = 1
        has_more = True

        while has_more:

            page = await self.fetch_applications_page(
                position_id=position_id,
                page=current_page,
                page_size=50,
            )

            all_applications.extend(
                page.applications
            )

            has_more = (
                page.hasMore
                and len(page.applications) > 0
            )

            current_page += 1

            if has_more:
                await asyncio.sleep(0.2)

        return all_applications

    # -----------------------------------------------------------------------
    # Fetch one position
    # -----------------------------------------------------------------------

    async def fetch_position(
        self,
        position_id: str,
    ) -> RawPosition:

        async def operation():
            response = await self.http_client.get(
                f"/positions/{position_id}"
            )

            response.raise_for_status()

            return response

        response = await with_retry(
            operation,
            self.max_retries,
            (
                "fetchPosition"
                f"(positionId={position_id})"
            ),
        )

        try:
            parsed = (
                PositionResponse.model_validate(
                    response.json()
                )
            )

        except ValidationError as error:

            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            raise JobBoardApiError(
                (
                    "Unexpected response shape from "
                    "position endpoint: "
                    f"{error}"
                ),
                status_code=response.status_code,
                response_body=response_body,
            ) from error

        return parsed.position

    # -----------------------------------------------------------------------
    # Fetch an application by ID
    # -----------------------------------------------------------------------

    async def fetch_application_by_id(
        self,
        position_id: str,
        application_id: str,
    ) -> RawApplication | None:

        try:

            async def operation():
                response = await self.http_client.get(
                    (
                        f"/positions/{position_id}"
                        f"/applications/{application_id}"
                    )
                )

                response.raise_for_status()

                return response

            response = await with_retry(
                operation,
                self.max_retries,
                (
                    "fetchApplicationById"
                    f"(applicationId={application_id})"
                ),
            )

            try:
                return RawApplication.model_validate(
                    response.json()
                )

            except ValidationError as error:

                try:
                    response_body = response.json()
                except Exception:
                    response_body = response.text

                raise JobBoardApiError(
                    (
                        "Unexpected application "
                        "record shape: "
                        f"{error}"
                    ),
                    status_code=response.status_code,
                    response_body=response_body,
                ) from error

        except JobBoardApiError as error:

            if error.status_code == 404:
                return None

            raise

    # -----------------------------------------------------------------------
    # List all currently open positions
    # -----------------------------------------------------------------------

    async def list_open_positions(
        self,
    ) -> list[RawPosition]:

        async def operation():
            response = await self.http_client.get(
                "/positions",
                params={
                    "status": "open",
                },
            )

            response.raise_for_status()

            return response

        response = await with_retry(
            operation,
            self.max_retries,
            "listOpenPositions",
        )

        try:
            response_data = response.json()
        except Exception as error:
            raise JobBoardApiError(
                (
                    "Unexpected response shape from "
                    "positions list endpoint"
                ),
                status_code=response.status_code,
                response_body=response.text,
            ) from error

        raw_positions = response_data.get(
            "positions"
        )

        if not isinstance(raw_positions, list):

            raise JobBoardApiError(
                (
                    "Unexpected response shape from "
                    "positions list endpoint"
                ),
                status_code=response.status_code,
                response_body=response_data,
            )

        positions: list[RawPosition] = []

        for raw in raw_positions:

            try:
                position = (
                    RawPosition.model_validate(raw)
                )

                positions.append(position)

            except ValidationError as error:

                print(
                    "Skipping malformed position "
                    f"record: {error}"
                )

        return positions

    # -----------------------------------------------------------------------
    # Close HTTP client
    # -----------------------------------------------------------------------

    async def close(self) -> None:
        await self.http_client.aclose()

    # -----------------------------------------------------------------------
    # Async context manager support
    # -----------------------------------------------------------------------

    async def __aenter__(
        self,
    ) -> "JobBoardClient":

        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:

        await self.close()


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def extract_resume_text(
    application: RawApplication,
) -> str:

    return application.resume_content


def format_application_metadata(
    application: RawApplication,
) -> dict[str, str]:

    return {
        "id": application.id,
        "name": application.applicant_name,
        "email": str(
            application.applicant_email
        ),
        "position": application.position_title,
        "submittedAt": application.submitted_at,
        "status": (
            application.status
            or "pending"
        ),
        "source": (
            application.source
            or "direct"
        ),
    }


def create_default_job_board_client(
) -> JobBoardClient:

    return JobBoardClient(
        JobBoardClientConfig(
            baseUrl=JOB_BOARD_API_BASE,
            apiKey=JOB_BOARD_API_KEY,
            timeoutMs=DEFAULT_TIMEOUT_MS,
            maxRetries=MAX_RETRIES,
        )
    )