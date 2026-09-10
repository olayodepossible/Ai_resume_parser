from __future__ import annotations

import json
import logging
import os
from typing import Any

from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
DEFAULT_MODEL = os.environ.get("RANKING_MODEL", "gpt-4.1-mini")
DEFAULT_TEMPERATURE = float(os.environ.get("RANKING_TEMPERATURE", "0.1"))


class ScreeningResult(BaseModel):
    candidate_id: str
    score: float = Field(ge=0, le=100)
    recommendation: str
    key_skills: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    summary: str


class RankedCandidate(BaseModel):
    candidate_id: str
    rank: int
    final_score: float = Field(ge=0, le=100)
    justification: str


class RankingOutput(BaseModel):
    ranked_candidates: list[RankedCandidate]
    top_recommendation: str
    position_title: str
    total_evaluated: int


class RankingAgentConfig(BaseModel):
    model_name: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    openai_api_key: str = Field(default_factory=lambda: OPENAI_API_KEY)
    max_tokens: int = 2048


RANKING_PROMPT_TEMPLATE = PromptTemplate(
    input_variables=["position_title", "candidate_count", "screening_summaries"],
    template="""You are a senior talent acquisition specialist responsible for making final hiring decisions.

You have received screening evaluations for multiple candidates applying for the position of: {position_title}

Here are the detailed screening results for all {candidate_count} candidates:

{screening_summaries}

Based on these evaluations, please rank all candidates from most to least suitable for the position.

Your response MUST be valid JSON with exactly this structure:
{{
  "ranked_candidates": [
    {{
      "candidate_id": "<id>",
      "rank": <integer starting from 1>,
      "final_score": <adjusted score 0-100>,
      "justification": "<brief justification for this ranking>"
    }}
  ],
  "top_recommendation": "<summary of why the top candidate is recommended>"
}}

Rank all {candidate_count} candidates objectively. Provide only the JSON response with no additional text.""",
)


def _format_screening_results(results: list[ScreeningResult]) -> str:
    sections: list[str] = []
    for idx, result in enumerate(results, start=1):
        skills_str = ", ".join(result.key_skills) if result.key_skills else "None listed"
        concerns_str = ", ".join(result.concerns) if result.concerns else "None identified"
        section = (
            f"Candidate {idx} (ID: {result.candidate_id}):\n"
            f"  Screening Score: {result.score}/100\n"
            f"  Initial Recommendation: {result.recommendation}\n"
            f"  Key Skills: {skills_str}\n"
            f"  Concerns: {concerns_str}\n"
            f"  Screening Summary: {result.summary}"
        )
        sections.append(section)
    return "\n\n".join(sections)


def _parse_ranking_response(raw_text: str, candidate_ids: list[str]) -> dict[str, Any]:
    text = raw_text.strip()
    json_match_start = text.find("{")
    json_match_end = text.rfind("}")
    if json_match_start == -1 or json_match_end == -1:
        raise ValueError("No JSON object found in ranking agent response")

    json_str = text[json_match_start : json_match_end + 1]
    parsed = json.loads(json_str)

    if "ranked_candidates" not in parsed:
        raise ValueError("Response missing 'ranked_candidates' field")
    if "top_recommendation" not in parsed:
        raise ValueError("Response missing 'top_recommendation' field")

    return parsed


def _build_ranking_output(
    raw_parsed: dict[str, Any],
    position_title: str,
    total_evaluated: int,
) -> RankingOutput:
    ranked_candidates: list[RankedCandidate] = []
    for item in raw_parsed.get("ranked_candidates", []):
        try:
            ranked_candidates.append(
                RankedCandidate(
                    candidate_id=str(item.get("candidate_id", "")),
                    rank=int(item.get("rank", 0)),
                    final_score=float(item.get("final_score", 0)),
                    justification=str(item.get("justification", "")),
                )
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Skipping malformed ranked candidate entry: %s", exc)

    ranked_candidates.sort(key=lambda c: c.rank)

    return RankingOutput(
        ranked_candidates=ranked_candidates,
        top_recommendation=str(raw_parsed.get("top_recommendation", "")),
        position_title=position_title,
        total_evaluated=total_evaluated,
    )


class CandidateRankingAgent:
    def __init__(self, config: RankingAgentConfig | None = None) -> None:
        self.config = config or RankingAgentConfig()
        self._llm = ChatOpenAI(
            model=self.config.model_name,
            temperature=self.config.temperature,
            api_key=OPENAI_API_KEY,
            base_url=self.config.openrouter_base_url,
            max_tokens=self.config.max_tokens,
        )
        self._chain = LLMChain(llm=self._llm, prompt=RANKING_PROMPT_TEMPLATE)

    def rank_candidates(
        self,
        screening_results: list[ScreeningResult],
        position_title: str,
    ) -> RankingOutput:
        if not screening_results:
            logger.info("No screening results provided; returning empty ranking.")
            return RankingOutput(
                ranked_candidates=[],
                top_recommendation="No candidates were available for evaluation.",
                position_title=position_title,
                total_evaluated=0,
            )

        candidate_ids = [r.candidate_id for r in screening_results]
        screening_summaries = _format_screening_results(screening_results)

        logger.info(
            "Ranking %d candidates for position '%s'",
            len(screening_results),
            position_title,
        )

        chain_result = self._chain.invoke(
            {
                "position_title": position_title,
                "candidate_count": str(len(screening_results)),
                "screening_summaries": screening_summaries,
            }
        )

        raw_text: str = chain_result.get("text", "") if isinstance(chain_result, dict) else str(chain_result)

        raw_parsed = _parse_ranking_response(raw_text, candidate_ids)
        ranking_output = _build_ranking_output(raw_parsed, position_title, len(screening_results))

        logger.info(
            "Ranking complete. Top candidate ID: %s",
            ranking_output.ranked_candidates[0].candidate_id
            if ranking_output.ranked_candidates
            else "N/A",
        )

        return ranking_output

    def rank_candidates_from_dicts(
        self,
        screening_dicts: list[dict[str, Any]],
        position_title: str,
    ) -> RankingOutput:
        screening_results: list[ScreeningResult] = []
        for raw in screening_dicts:
            try:
                normalized = {
                    "candidate_id": raw.get("candidateId") or raw.get("candidate_id", ""),
                    "score": raw.get("score", 0),
                    "recommendation": raw.get("recommendation", "maybe"),
                    "key_skills": raw.get("keySkills") or raw.get("key_skills", []),
                    "concerns": raw.get("concerns", []),
                    "summary": raw.get("summary", ""),
                }
                screening_results.append(ScreeningResult(**normalized))
            except (ValidationError, TypeError) as exc:
                logger.warning("Skipping malformed screening result: %s", exc)

        return self.rank_candidates(screening_results, position_title)


def create_ranking_agent(
    model_name: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> CandidateRankingAgent:
    config = RankingAgentConfig(
        model_name=model_name,
        temperature=temperature,
        openai_api_key=OPENAI_API_KEY,
    )
    return CandidateRankingAgent(config=config)


def rank_pipeline_results(
    screening_results: list[dict[str, Any]],
    position_title: str,
    model_name: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    agent = create_ranking_agent(model_name=model_name)
    output = agent.rank_candidates_from_dicts(screening_results, position_title)
    return output.model_dump()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    sample_results: list[dict[str, Any]] = [
        {
            "candidateId": "cand-001",
            "score": 85,
            "recommendation": "strong_yes",
            "keySkills": ["Python", "LangChain", "AWS", "REST APIs"],
            "concerns": [],
            "summary": "Strong backend engineer with relevant ML pipeline experience.",
        },
        {
            "candidateId": "cand-002",
            "score": 70,
            "recommendation": "yes",
            "keySkills": ["TypeScript", "Node.js", "Docker"],
            "concerns": ["Limited ML experience"],
            "summary": "Solid full-stack developer with some gaps in required ML tooling.",
        },
        {
            "candidateId": "cand-003",
            "score": 55,
            "recommendation": "maybe",
            "keySkills": ["Java", "Spring Boot"],
            "concerns": ["No Python experience", "No cloud exposure"],
            "summary": "Experienced Java developer but lacks required stack proficiency.",
        },
    ]

    result = rank_pipeline_results(
        screening_results=sample_results,
        position_title="Senior ML Platform Engineer",
    )

    print(json.dumps(result, indent=2))