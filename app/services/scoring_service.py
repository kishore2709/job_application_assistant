from app.db.repositories import ScoreRepository
from app.models.score import JobScore
from app.services.claude_service import ClaudeService


class EmptyJobDescriptionError(Exception):
    pass


def get_cached_score(job_id: int) -> JobScore | None:
    return ScoreRepository().get_by_job_id(job_id)


def score_job(job_id: int, resume_text: str, job_description: str, job_title: str) -> JobScore:
    if not job_description or not job_description.strip():
        raise EmptyJobDescriptionError("No job description available to score against")

    result = ClaudeService().score_resume_against_jd(resume_text, job_description, job_title)

    score = JobScore(
        job_id=job_id,
        score=int(result.get("score", 0)),
        matched_keywords=[str(k) for k in (result.get("matched_keywords") or [])],
        missing_keywords=[str(k) for k in (result.get("missing_keywords") or [])],
        reasoning=str(result.get("reasoning") or ""),
        recommendation=str(result.get("recommendation") or ""),
    )

    ScoreRepository().save(score)
    return score
