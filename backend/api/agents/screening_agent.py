from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
DEFAULT_MODEL = os.environ.get("SCREENING_MODEL", "gpt-4")
DEFAULT_TEMPERATURE = float(os.environ.get("SCREENING_TEMPERATURE", "0.1"))


class CandidateInput(BaseModel):
    candidate_id: str
    name: str
    email: str
    resume_text: str
    applied_position: str
    application_date: str


class ScreeningResult(BaseModel):
    candidate_id: str
    score: float = Field(ge=0, le=100)
    recommendation: str
    key_skills: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    summary: str


class ScreeningAgentConfig(BaseModel):
    model_name: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    openai_api_key: str = Field(default_factory=lambda: OPENAI_API_KEY)
    max_tokens: int = 1024


SCREENING_PROMPT_TEMPLATE = PromptTemplate(
    input_variables=[
        "position_requirements",
        "candidate_name",
        "applied_position",
        "application_date",
        "resume_text",
    ],
    template="""You are an expert technical recruiter and hiring specialist. Your task is to evaluate a candidate's resume for a specific position.

Position Requirements:
{position_requirements}

Candidate Information:
- Name: {candidate_name}
- Applied Position: {applied_position}
- Application Date: {application_date}

Resume Content:
{resume_text}

Please provide a structured evaluation of this candidate. Your response must be valid JSON with the following structure:
{{
  "score": <number between 0-100>,
  "recommendation": <"strong_yes" | "yes" | "maybe" | "no" | "strong_no">,
  "keySkills": [<list of relevant skills found>],
  "concerns": [<list of any concerns or gaps>],
  "summary": "<brief summary of the candidate>"
}}

Evaluate objectively based on the resume content and position requirements. Provide only the JSON response.""",
)

VALID_RECOMMENDATIONS = {"strong_yes", "yes", "maybe", "no", "strong_no"}


def _extract_json_from_response(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in screening agent response")
    json_str = text[start : end + 1]
    return json.loads(json_str)


def _build_screening_result(
    raw_parsed: dict[str, Any],
    candidate_id: str,
) -> ScreeningResult:
    score_raw = raw_parsed.get("score", 0)
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(100.0, score))

    recommendation = str(raw_parsed.get("recommendation", "maybe"))
    if recommendation not in VALID_RECOMMENDATIONS:
        recommendation = "maybe"

    key_skills_raw = raw_parsed.get("keySkills") or raw_parsed.get("key_skills", [])
    key_skills = [str(s) for s in key_skills_raw] if isinstance(key_skills_raw, list) else []

    concerns_raw = raw_parsed.get("concerns", [])
    concerns = [str(c) for c in concerns_raw] if isinstance(concerns_raw, list) else []

    summary = str(raw_parsed.get("summary", ""))

    return ScreeningResult(
        candidate_id=candidate_id,
        score=score,
        recommendation=recommendation,
        key_skills=key_skills,
        concerns=concerns,
        summary=summary,
    )


class CandidateScreeningAgent:
    def __init__(self, config: ScreeningAgentConfig | None = None) -> None:
        self.config = config or ScreeningAgentConfig()
        self._llm = ChatOpenAI(
            model=self.config.model_name,
            temperature=self.config.temperature,
            openai_api_key=self.config.openai_api_key,
            max_tokens=self.config.max_tokens,
        )
        self._chain = LLMChain(llm=self._llm, prompt=SCREENING_PROMPT_TEMPLATE)

    def screen_candidate(
        self,
        candidate: CandidateInput,
        position_requirements: str,
    ) -> ScreeningResult:
        logger.info(
            "Screening candidate '%s' (ID: %s) for position '%s'",
            candidate.name,
            candidate.candidate_id,
            candidate.applied_position,
        )

        chain_result = self._chain.invoke(
            {
                "position_requirements": position_requirements,
                "candidate_name": candidate.name,
                "applied_position": candidate.applied_position,
                "application_date": candidate.application_date,
                "resume_text": candidate.resume_text,
            }
        )

        raw_text: str = (
            chain_result.get("text", "")
            if isinstance(chain_result, dict)
            else str(chain_result)
        )

        raw_parsed = _extract_json_from_response(raw_text)
        result = _build_screening_result(raw_parsed, candidate.candidate_id)

        logger.info(
            "Screening complete for candidate %s: score=%.1f, recommendation=%s",
            candidate.candidate_id,
            result.score,
            result.recommendation,
        )

        return result

    def screen_candidates_batch(
        self,
        candidates: list[CandidateInput],
        position_requirements: str,
    ) -> list[ScreeningResult]:
        results: list[ScreeningResult] = []
        for candidate in candidates:
            try:
                result = self.screen_candidate(candidate, position_requirements)
                results.append(result)
            except Exception as exc:
                logger.error(
                    "Failed to screen candidate %s: %s",
                    candidate.candidate_id,
                    exc,
                )
                results.append(
                    ScreeningResult(
                        candidate_id=candidate.candidate_id,
                        score=0.0,
                        recommendation="maybe",
                        key_skills=[],
                        concerns=["Screening evaluation failed due to processing error"],
                        summary="Could not complete automated screening for this candidate.",
                    )
                )
        return results

    def screen_candidate_from_dict(
        self,
        candidate_data: dict[str, Any],
        position_requirements: str,
    ) -> ScreeningResult:
        try:
            normalized = {
                "candidate_id": (
                    candidate_data.get("candidateId")
                    or candidate_data.get("candidate_id", "")
                ),
                "name": candidate_data.get("name", ""),
                "email": candidate_data.get("email", ""),
                "resume_text": (
                    candidate_data.get("resumeText")
                    or candidate_data.get("resume_text", "")
                ),
                "applied_position": (
                    candidate_data.get("appliedPosition")
                    or candidate_data.get("applied_position", "")
                ),
                "application_date": (
                    candidate_data.get("applicationDate")
                    or candidate_data.get("application_date", "")
                ),
            }
            candidate = CandidateInput(**normalized)
        except (ValidationError, TypeError) as exc:
            raise ValueError(f"Invalid candidate data: {exc}") from exc

        return self.screen_candidate(candidate, position_requirements)


def create_screening_agent(
    model_name: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> CandidateScreeningAgent:
    config = ScreeningAgentConfig(
        model_name=model_name,
        temperature=temperature,
        openai_api_key=OPENAI_API_KEY,
    )
    return CandidateScreeningAgent(config=config)


def screen_pipeline_candidates(
    candidates: list[dict[str, Any]],
    position_requirements: str,
    model_name: str = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    agent = create_screening_agent(model_name=model_name)
    results: list[dict[str, Any]] = []
    for candidate_data in candidates:
        try:
            result = agent.screen_candidate_from_dict(candidate_data, position_requirements)
            results.append(result.model_dump())
        except Exception as exc:
            logger.error(
                "Pipeline screening failed for candidate data %s: %s",
                candidate_data.get("candidateId") or candidate_data.get("candidate_id", "unknown"),
                exc,
            )
            candidate_id = (
                candidate_data.get("candidateId")
                or candidate_data.get("candidate_id", "unknown")
            )
            results.append(
                ScreeningResult(
                    candidate_id=candidate_id,
                    score=0.0,
                    recommendation="maybe",
                    key_skills=[],
                    concerns=["Automated screening could not be completed"],
                    summary="Processing error prevented evaluation of this candidate.",
                ).model_dump()
            )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    sample_candidates: list[dict[str, Any]] = [
        {
            "candidateId": "cand-001",
            "name": "Alice Johnson",
            "email": "alice.johnson@example.com",
            "resumeText": (
                "Senior Software Engineer with 8 years of experience in Python and distributed systems. "
                "Proficient in LangChain, AWS, Docker, and Kubernetes. Led ML pipeline development at "
                "previous employer, reducing model deployment time by 40%. M.S. Computer Science, Stanford."
            ),
            "appliedPosition": "Senior ML Platform Engineer",
            "applicationDate": "2024-01-15",
        },
        {
            "candidateId": "cand-002",
            "name": "Bob Martinez",
            "email": "bob.martinez@example.com",
            "resumeText": (
                "Full-stack developer with 5 years of experience in TypeScript and Node.js. "
                "Familiar with React, PostgreSQL, and Docker. Some exposure to Python scripting. "
                "B.S. Computer Science, University of Texas."
            ),
            "appliedPosition": "Senior ML Platform Engineer",
            "applicationDate": "2024-01-16",
        },
    ]

    sample_requirements = (
        "We are looking for a Senior ML Platform Engineer with strong Python skills, "
        "experience with LangChain or similar LLM frameworks, cloud infrastructure (AWS preferred), "
        "and a track record of building and maintaining ML pipelines in production."
    )

    results = screen_pipeline_candidates(
        candidates=sample_candidates,
        position_requirements=sample_requirements,
    )

    print(json.dumps(results, indent=2))