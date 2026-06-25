import re

from app.db.repositories import ScoreRepository
from app.models.score import JobScore
from app.services.llm_service import LLMService

KEYWORD_MIN_LENGTH = 3
NOISE_KEYWORDS = {
    "IEEE", "JFFS", "ETC", "AND", "THE", "FOR", "WITH", "INC", "LLC", "LTD", "CO", "USA",
}
NUMERIC_ONLY_PATTERN = re.compile(r"^\d+$")


class EmptyJobDescriptionError(Exception):
    pass


def get_cached_score(job_id: int) -> JobScore | None:
    return ScoreRepository().get_by_job_id(job_id)


def _clean_keywords(keywords: list) -> list[str]:
    cleaned = []
    for raw_keyword in keywords:
        keyword = str(raw_keyword).strip()
        if len(keyword) < KEYWORD_MIN_LENGTH:
            continue
        if NUMERIC_ONLY_PATTERN.match(keyword):
            continue
        if keyword.upper() in NOISE_KEYWORDS:
            continue
        cleaned.append(keyword)
    return cleaned


def score_job(job_id: int, resume_text: str, job_description: str, job_title: str) -> JobScore:
    if not job_description or not job_description.strip():
        raise EmptyJobDescriptionError("No job description available to score against")

    result = LLMService().score(resume_text, job_description, job_title)

    score = JobScore(
        job_id=job_id,
        score=int(result.get("score", 0)),
        matched_keywords=_clean_keywords(result.get("matched") or result.get("matched_keywords") or []),
        missing_keywords=_clean_keywords(result.get("missing") or result.get("missing_keywords") or []),
        reasoning=str(result.get("reason") or result.get("reasoning") or ""),
        recommendation=str(result.get("recommend") or result.get("recommendation") or ""),
    )

    ScoreRepository().save(score)
    return score
