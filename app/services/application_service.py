from datetime import date

from app.db.repositories import ApplicationRepository, JobRepository
from app.models.application import Application


def log_application(
    job,
    resume_path: str = "",
    resume_id: int | None = None,
) -> Application:
    """Create or update an application record and mark the job as Applied."""
    repo = ApplicationRepository()
    existing = repo.get_by_job_id(job.id) if job.id else None
    today = date.today().isoformat()

    if existing is not None:
        existing.status = "Applied"
        existing.date_applied = today
        if resume_path:
            existing.resume_path = resume_path
        if resume_id is not None:
            existing.resume_id = resume_id
        repo.update(existing)
    else:
        app = Application(
            company_name=job.company,
            job_title=job.title,
            job_id=job.id,
            job_url=job.url or "",
            source=job.source or "",
            date_applied=today,
            status="Applied",
            resume_id=resume_id,
            resume_path=resume_path,
        )
        app_id = repo.create(app)
        existing = repo.get_by_id(app_id)

    if job.id:
        JobRepository().update_status(job.id, "Applied")

    return existing


def get_application_for_job(job_id: int) -> Application | None:
    return ApplicationRepository().get_by_job_id(job_id)
