import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, TypedDict

import httpx
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

JOB_BOARD_API_BASE = os.getenv(
    "JOB_BOARD_API_URL",
    "https://api.jobboard.example.com",
)

JOB_BOARD_API_KEY = os.getenv("JOB_BOARD_API_KEY", "")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Candidate(BaseModel):
    candidateId: str
    name: str
    email: str
    resumeText: str
    appliedPosition: str
    applicationDate: str


class ScreeningResult(BaseModel):
    candidateId: str
    score: float
    recommendation: str
    keySkills: list[str]
    concerns: list[str]
    summary: str


class RankedCandidate(TypedDict):
    candidateId: str
    rank: int
    finalScore: float
    justification: str


class RankingOutput(TypedDict):
    rankedCandidates: list[RankedCandidate]
    topRecommendation: str


class PipelineResult(TypedDict):
    screeningResults: list[ScreeningResult]
    rankingOutput: RankingOutput
    processedAt: str


class ApplicationInput(TypedDict):
    positionId: str
    positionTitle: str
    requirements: str


class BatchResult(TypedDict):
    positionId: str
    result: PipelineResult | None
    error: str | None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def utc_iso_now() -> str:
    """
    Return a UTC timestamp similar to JavaScript:
        new Date().toISOString()
    """

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def extract_json_object(raw_text: str) -> dict[str, Any]:
    """
    Extract a JSON object from an LLM response.

    Equivalent to the TypeScript logic using:
        rawText.match(...)
    """

    match = re.search(r"\{[\s\S]*\}", raw_text.strip())

    if not match:
        raise ValueError("No JSON found in model response")

    parsed = json.loads(match.group(0))

    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON is not an object")

    return parsed


def message_text(message: Any) -> str:
    """
    Convert the LangChain AIMessage response into plain text.

    Normally ChatOpenAI returns text content, but this also handles
    list/block-based content.
    """

    content = getattr(message, "content", "")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)

            elif isinstance(block, dict):
                text = block.get("text")

                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts)

    return str(content)


# ---------------------------------------------------------------------------
# Ranking output normalisation
# ---------------------------------------------------------------------------

_RANKING_KEYS = {
    "rankedcandidates": "rankedCandidates",
    "toprecommendation": "topRecommendation",
}

_RANKED_CANDIDATE_KEYS = {
    "candidateid": "candidateId",
    "rank": "rank",
    "finalscore": "finalScore",
    "justification": "justification",
}


def _canonical_key(
    key: str,
    aliases: dict[str, str],
) -> str:
    """Map `final_score` / `finalscore` / `FinalScore` onto `finalScore`."""

    return aliases.get(
        key.replace("_", "").replace("-", "").lower(),
        key,
    )


def _coerce_score(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0

    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(100.0, score))


def coerce_ranking_output(
    parsed: dict[str, Any],
    candidate_ids: list[str],
) -> RankingOutput:
    """Turn the ranking model's free-form JSON into a trustworthy RankingOutput.

    The prompt asks for camelCase keys and exactly one entry per candidate, but
    nothing binds the model to that. It can emit snake_case, invent candidate
    ids, rank the same candidate twice, skip candidates entirely, or return a
    score outside 0-100. Callers index straight into this structure, so it is
    normalised here instead of trusted:

    - keys are canonicalised,
    - unknown and duplicate candidate ids are dropped,
    - scores are coerced and clamped,
    - candidates the model omitted are appended rather than lost,
    - ranks are renumbered 1..N after sorting.
    """

    normalized: dict[str, Any] = {
        _canonical_key(key, _RANKING_KEYS): value
        for key, value in parsed.items()
    }

    raw_entries = normalized.get("rankedCandidates")

    if not isinstance(raw_entries, list):
        raise RuntimeError(
            "Ranking output is missing a 'rankedCandidates' list"
        )

    known_ids = set(candidate_ids)
    seen_ids: set[str] = set()
    entries: list[RankedCandidate] = []

    for raw in raw_entries:

        if not isinstance(raw, dict):
            continue

        entry = {
            _canonical_key(key, _RANKED_CANDIDATE_KEYS): value
            for key, value in raw.items()
        }

        candidate_id = str(
            entry.get("candidateId", "")
        ).strip()

        # Keeps the shortlist aligned with the candidates actually submitted.
        if candidate_id not in known_ids or candidate_id in seen_ids:
            continue

        seen_ids.add(candidate_id)

        try:
            rank = int(entry.get("rank", len(entries) + 1))
        except (TypeError, ValueError):
            rank = len(entries) + 1

        entries.append(
            {
                "candidateId": candidate_id,
                "rank": rank,
                "finalScore": _coerce_score(
                    entry.get("finalScore")
                ),
                "justification": str(
                    entry.get("justification", "")
                ),
            }
        )

    entries.sort(key=lambda entry: entry["rank"])

    for candidate_id in candidate_ids:

        if candidate_id in seen_ids:
            continue

        entries.append(
            {
                "candidateId": candidate_id,
                "rank": len(entries) + 1,
                "finalScore": 0.0,
                "justification": (
                    "The ranking model did not return a placement "
                    "for this candidate."
                ),
            }
        )

    for position, entry in enumerate(entries, start=1):
        entry["rank"] = position

    top_recommendation = normalized.get(
        "topRecommendation"
    )

    return {
        "rankedCandidates": entries,
        "topRecommendation": (
            top_recommendation
            if isinstance(top_recommendation, str)
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# Fetch candidates from job board
# ---------------------------------------------------------------------------

async def fetch_candidates_from_job_board(
    position_id: str,
) -> list[Candidate]:

    headers = {
        "Authorization": f"Bearer {JOB_BOARD_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{JOB_BOARD_API_BASE}/positions/"
            f"{position_id}/applications",
            headers=headers,
        )

        response.raise_for_status()

        response_data = response.json()

    candidates: list[Candidate] = []

    for item in response_data["applications"]:

        try:
            candidate = Candidate(
                candidateId=item["id"],
                name=item["applicant_name"],
                email=item["applicant_email"],
                resumeText=item["resume_content"],
                appliedPosition=item["position_title"],
                applicationDate=item["submitted_at"],
            )

        except (ValidationError, KeyError, TypeError):
            # Equivalent to:
            #
            # CandidateSchema.safeParse(...)
            #
            # Invalid candidate records are ignored.

            continue

        candidates.append(candidate)

    return candidates


# ---------------------------------------------------------------------------
# Screen a single candidate
# ---------------------------------------------------------------------------

async def screen_candidate(
    candidate: Candidate,
    position_requirements: str,
    model: ChatOpenAI,
) -> ScreeningResult:

    screening_prompt_template = PromptTemplate.from_template(
        """
You are an expert technical recruiter and hiring specialist.
Your task is to evaluate a candidate's resume for a specific position.

Position Requirements:

{positionRequirements}

Candidate Information:

- Name: {candidateName}

- Applied Position: {appliedPosition}

- Application Date: {applicationDate}

Resume Content:

{resumeText}

Please provide a structured evaluation of this candidate.

Your response must be valid JSON with the following structure:

{{
  "score": <number between 0-100>,
  "recommendation": <"strong_yes" | "yes" | "maybe" | "no" | "strong_no">,
  "keySkills": [<list of relevant skills found>],
  "concerns": [<list of any concerns or gaps>],
  "summary": "<brief summary of the candidate>"
}}

Evaluate objectively based on the resume content and position requirements.

Provide only the JSON response.
""".strip()
    )

    # Current LangChain runnable equivalent of LLMChain.
    chain = screening_prompt_template | model

    result = await chain.ainvoke(
        {
            "positionRequirements": position_requirements,
            "candidateName": candidate.name,
            "appliedPosition": candidate.appliedPosition,
            "applicationDate": candidate.applicationDate,
            "resumeText": candidate.resumeText,
        }
    )

    try:
        raw_text = message_text(result).strip()

        parsed_result = extract_json_object(raw_text)

    except (ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Failed to parse screening result for candidate "
            f"{candidate.candidateId}: {error}"
        ) from error

    # -----------------------------------------------------------------------
    # Equivalent to the TypeScript fallback logic
    # -----------------------------------------------------------------------

    score_value = parsed_result.get("score")

    score = (
        float(score_value)
        if isinstance(score_value, (int, float))
        and not isinstance(score_value, bool)
        else 0.0
    )

    recommendation_value = parsed_result.get(
        "recommendation"
    )

    recommendation = (
        recommendation_value
        if isinstance(recommendation_value, str)
        else "maybe"
    )

    key_skills_value = parsed_result.get(
        "keySkills"
    )

    key_skills = (
        key_skills_value
        if isinstance(key_skills_value, list)
        else []
    )

    concerns_value = parsed_result.get(
        "concerns"
    )

    concerns = (
        concerns_value
        if isinstance(concerns_value, list)
        else []
    )

    summary_value = parsed_result.get(
        "summary"
    )

    summary = (
        summary_value
        if isinstance(summary_value, str)
        else ""
    )

    # -----------------------------------------------------------------------
    # Validate final result
    # -----------------------------------------------------------------------

    try:
        screening_result = ScreeningResult(
            candidateId=candidate.candidateId,
            score=score,
            recommendation=recommendation,
            keySkills=key_skills,
            concerns=concerns,
            summary=summary,
        )

    except ValidationError as error:
        raise RuntimeError(
            "Invalid screening result for candidate "
            f"{candidate.candidateId}: {error}"
        ) from error

    return screening_result


# ---------------------------------------------------------------------------
# Rank candidates
# ---------------------------------------------------------------------------

async def rank_candidates(
    screening_results: list[ScreeningResult],
    position_title: str,
    model: ChatOpenAI,
) -> RankingOutput:

    ranking_prompt_template = PromptTemplate.from_template(
        """
You are a senior talent acquisition specialist responsible for making
final hiring decisions.

You have received screening evaluations for multiple candidates applying
for the position of:

{positionTitle}

Here are the screening results for all candidates:

{screeningResults}

Based on these evaluations, please rank the candidates from most to least
suitable.

Your response must be valid JSON with this structure:

{{
  "rankedCandidates": [
    {{
      "candidateId": "<id>",
      "rank": <rank number starting from 1>,
      "finalScore": <adjusted score 0-100>,
      "justification": "<brief justification for this ranking>"
    }}
  ],
  "topRecommendation": "<summary of why the top candidate is recommended>"
}}

Rank all {candidateCount} candidates and provide only the JSON response.
""".strip()
    )

    chain = ranking_prompt_template | model

    formatted_results = "\n\n".join(
        (
            f"Candidate {index + 1} "
            f"(ID: {screening_result.candidateId}):\n"
            f"  - Score: "
            f"{screening_result.score}/100\n"
            f"  - Recommendation: "
            f"{screening_result.recommendation}\n"
            f"  - Key Skills: "
            f"{', '.join(screening_result.keySkills)}\n"
            f"  - Concerns: "
            f"{', '.join(screening_result.concerns) or 'None'}\n"
            f"  - Summary: "
            f"{screening_result.summary}"
        )
        for index, screening_result
        in enumerate(screening_results)
    )

    result = await chain.ainvoke(
        {
            "positionTitle": position_title,
            "screeningResults": formatted_results,
            "candidateCount": str(
                len(screening_results)
            ),
        }
    )

    try:
        raw_text = message_text(result).strip()

        parsed_output = extract_json_object(
            raw_text
        )

    except (ValueError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Failed to parse ranking output: {error}"
        ) from error

    return coerce_ranking_output(
        parsed_output,
        [
            screening_result.candidateId
            for screening_result in screening_results
        ],
    )


# ---------------------------------------------------------------------------
# Screen + rank core
#
# This is the part of the pipeline that does not care where candidates came
# from. Version 1 feeds it resumes uploaded as PDFs; version 2 feeds it
# candidates fetched from the job board API.
# ---------------------------------------------------------------------------

def _failed_screening_result(
    candidate: Candidate,
) -> ScreeningResult:

    return ScreeningResult(
        candidateId=candidate.candidateId,
        score=0.0,
        recommendation="maybe",
        keySkills=[],
        concerns=[
            "Screening evaluation failed due to a processing error"
        ],
        summary=(
            "Could not complete automated screening "
            "for this candidate."
        ),
    )


async def run_screening_pipeline(
    candidates: list[Candidate],
    position_title: str,
    position_requirements: str,
    model: ChatOpenAI,
    *,
    concurrency: int = 1,
    delay_seconds: float = 0.5,
    continue_on_error: bool = False,
) -> PipelineResult:
    """Screen every candidate, then rank them as a set.

    `concurrency` caps how many screening calls are in flight at once, and
    `delay_seconds` spaces them out for provider rate limits. The defaults
    (one at a time, 500ms apart) reproduce the original sequential behaviour.

    With `continue_on_error`, a candidate whose screening call fails is recorded
    with a zero score and an explanatory concern instead of aborting the batch —
    one malformed model response should not discard an entire upload.
    """

    if not candidates:
        return {
            "screeningResults": [],
            "rankingOutput": {
                "rankedCandidates": [],
                "topRecommendation": (
                    "No candidates available for evaluation"
                ),
            },
            "processedAt": utc_iso_now(),
        }

    semaphore = asyncio.Semaphore(
        max(1, concurrency)
    )

    async def screen_one(
        candidate: Candidate,
    ) -> ScreeningResult:

        async with semaphore:

            print(
                f"Screening candidate: "
                f"{candidate.name} "
                f"({candidate.candidateId})"
            )

            try:
                result = await screen_candidate(
                    candidate,
                    position_requirements,
                    model,
                )

            except Exception as error:

                if not continue_on_error:
                    raise

                print(
                    f"Failed to screen candidate "
                    f"{candidate.candidateId}: {error}"
                )

                result = _failed_screening_result(
                    candidate
                )

            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

            return result

    # gather preserves input order, so results line up with `candidates`.
    screening_results = list(
        await asyncio.gather(
            *(
                screen_one(candidate)
                for candidate in candidates
            )
        )
    )

    print(
        f"Completed screening for "
        f"{len(screening_results)} candidates"
    )

    ranking_output = await rank_candidates(
        screening_results,
        position_title,
        model,
    )

    print(
        "Ranking complete. "
        "Top recommendation generated."
    )

    return {
        "screeningResults": screening_results,
        "rankingOutput": ranking_output,
        "processedAt": utc_iso_now(),
    }


# ---------------------------------------------------------------------------
# Main recruitment pipeline (version 2: candidates come from the job board)
# ---------------------------------------------------------------------------

async def orchestrate_recruitment_pipeline(
    position_id: str,
    position_title: str,
    position_requirements: str,
) -> PipelineResult:

    # ChatOpenAI automatically reads OPENAI_API_KEY
    # from the environment.
    model = ChatOpenAI(
        model="gpt-4",
        temperature=0.1,
    )

    print(
        f"Starting recruitment pipeline for position: "
        f"{position_title} "
        f"(ID: {position_id})"
    )

    candidates = await fetch_candidates_from_job_board(
        position_id
    )

    print(
        f"Fetched {len(candidates)} "
        f"candidates from job board"
    )

    return await run_screening_pipeline(
        candidates,
        position_title,
        position_requirements,
        model,
    )


# ---------------------------------------------------------------------------
# Process multiple positions
# ---------------------------------------------------------------------------

async def process_application_batch(
    applications: list[ApplicationInput],
) -> list[BatchResult]:

    results: list[BatchResult] = []

    for application in applications:

        try:
            result = (
                await orchestrate_recruitment_pipeline(
                    application["positionId"],
                    application["positionTitle"],
                    application["requirements"],
                )
            )

            results.append(
                {
                    "positionId": application[
                        "positionId"
                    ],
                    "result": result,
                    "error": None,
                }
            )

        except Exception as error:

            print(
                f"Error processing position "
                f"{application['positionId']}: "
                f"{error}"
            )

            results.append(
                {
                    "positionId": application[
                        "positionId"
                    ],
                    "result": None,
                    "error": (
                        str(error)
                        or "Unknown error occurred"
                    ),
                }
            )

    return results