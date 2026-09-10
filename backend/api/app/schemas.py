from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class CandidateSummary(BaseModel):
    """How an uploaded PDF maps onto a candidate the pipeline evaluated."""

    candidateId: str
    name: str
    email: str = Field(
        default="",
        description="Extracted from the resume text; empty when none was found.",
    )
    sourceFilename: str
    resumeChars: int


class RejectedFile(BaseModel):
    filename: str
    reason: str


class ScreeningResultOut(BaseModel):
    candidateId: str
    score: float
    recommendation: str
    keySkills: list[str]
    concerns: list[str]
    summary: str


class RankedCandidateOut(BaseModel):
    candidateId: str
    rank: int
    finalScore: float
    justification: str


class RankingOut(BaseModel):
    rankedCandidates: list[RankedCandidateOut]
    topRecommendation: str


class ScreeningResponse(BaseModel):
    positionTitle: str
    jobDescriptionChars: int
    totalUploaded: int
    totalEvaluated: int
    candidates: list[CandidateSummary]
    rejectedFiles: list[RejectedFile] = Field(
        default_factory=list,
        description="Uploads that could not be read; the rest were still processed.",
    )
    screeningResults: list[ScreeningResultOut]
    rankingOutput: RankingOut
    processedAt: str


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    model: str
    llmConfigured: bool


# ---------------------------------------------------------------------------
# Auth (placeholder; see app/auth.py)
# ---------------------------------------------------------------------------


class UserSettings(BaseModel):
    company: str = ""
    defaultPositionTitle: str = ""
    emailOnCompletion: bool = False
    theme: Literal["light", "dark", "system"] = "system"


class UserOut(BaseModel):
    id: str
    email: str
    fullName: str
    createdAt: str
    settings: UserSettings


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    fullName: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UpdateProfileRequest(BaseModel):
    fullName: str | None = Field(default=None, max_length=120)
    settings: UserSettings | None = None


class AuthResponse(BaseModel):
    accessToken: str
    tokenType: Literal["bearer"] = "bearer"
    expiresAt: int = Field(description="Token expiry as epoch seconds (UTC).")
    user: UserOut
