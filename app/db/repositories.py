import json

from app.db.database import get_connection
from app.models.application import Application
from app.models.job import Job
from app.models.profile import BlacklistCompany, ProfileSettings, TargetRole
from app.models.resume import Resume
from app.models.score import JobScore
from app.utils.constants import DEFAULT_BLACKLISTED_COMPANIES


class ProfileRepository:
    def get(self) -> ProfileSettings:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM profile_settings WHERE id = 1"
            ).fetchone()
            profile = ProfileSettings()
            if row:
                profile.full_name = row["full_name"] or ""
                profile.email = row["email"] or ""
                profile.phone = row["phone"] or ""
                profile.linkedin_url = row["linkedin_url"] or ""
                profile.github_url = row["github_url"] or ""
                profile.location = row["location"] or ""
                profile.visa_status = row["visa_status"] or "H-1B Transfer — no sponsorship"
                profile.salary_min = row["salary_min"]
                profile.salary_max = row["salary_max"]
                profile.work_preference = row["work_preference"] or "Any"
                profile.default_resume_path = row["default_resume_path"] or ""

            profile.target_roles = [
                TargetRole(
                    id=r["id"],
                    role_title=r["role_title"],
                    role_description=r["role_description"] or "",
                    is_active=bool(r["is_active"]),
                )
                for r in connection.execute(
                    "SELECT * FROM target_roles ORDER BY id"
                ).fetchall()
            ]
            profile.blacklist_companies = [
                BlacklistCompany(id=r["id"], company_name=r["company_name"])
                for r in connection.execute(
                    "SELECT * FROM blacklist_companies ORDER BY company_name"
                ).fetchall()
            ]
            return profile
        finally:
            connection.close()

    def save(self, profile: ProfileSettings) -> None:
        connection = get_connection()
        try:
            connection.execute(
                """
                UPDATE profile_settings SET
                    full_name = ?, email = ?, phone = ?, linkedin_url = ?,
                    github_url = ?, location = ?, visa_status = ?,
                    salary_min = ?, salary_max = ?, work_preference = ?,
                    default_resume_path = ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (
                    profile.full_name,
                    profile.email,
                    profile.phone,
                    profile.linkedin_url,
                    profile.github_url,
                    profile.location,
                    profile.visa_status,
                    profile.salary_min,
                    profile.salary_max,
                    profile.work_preference,
                    profile.default_resume_path,
                ),
            )

            connection.execute("DELETE FROM target_roles")
            connection.executemany(
                "INSERT INTO target_roles (role_title, role_description, is_active) VALUES (?, ?, ?)",
                [
                    (role.role_title, role.role_description, int(role.is_active))
                    for role in profile.target_roles
                ],
            )

            connection.execute("DELETE FROM blacklist_companies")
            connection.executemany(
                "INSERT INTO blacklist_companies (company_name) VALUES (?)",
                [(company.company_name,) for company in profile.blacklist_companies],
            )

            connection.commit()
        finally:
            connection.close()


class BlacklistRepository:
    def seed_defaults_if_empty(self) -> None:
        connection = get_connection()
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM blacklist_companies"
            ).fetchone()[0]
            if count == 0:
                connection.executemany(
                    "INSERT OR IGNORE INTO blacklist_companies (company_name) VALUES (?)",
                    [(name,) for name in DEFAULT_BLACKLISTED_COMPANIES],
                )
                connection.commit()
        finally:
            connection.close()


class ResumeRepository:
    def add(self, resume: Resume) -> int:
        connection = get_connection()
        try:
            if resume.is_default:
                connection.execute("UPDATE resumes SET is_default = 0")
            cursor = connection.execute(
                "INSERT INTO resumes (file_name, file_path, is_default, notes) VALUES (?, ?, ?, ?)",
                (resume.file_name, resume.file_path, int(resume.is_default), resume.notes),
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    def list_all(self) -> list[Resume]:
        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT * FROM resumes ORDER BY uploaded_at DESC"
            ).fetchall()
            return [self._row_to_resume(row) for row in rows]
        finally:
            connection.close()

    def get_by_id(self, resume_id: int) -> Resume | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM resumes WHERE id = ?", (resume_id,)
            ).fetchone()
            return self._row_to_resume(row) if row else None
        finally:
            connection.close()

    def get_default(self) -> Resume | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM resumes WHERE is_default = 1"
            ).fetchone()
            return self._row_to_resume(row) if row else None
        finally:
            connection.close()

    def set_default(self, resume_id: int) -> None:
        connection = get_connection()
        try:
            connection.execute("UPDATE resumes SET is_default = 0")
            connection.execute(
                "UPDATE resumes SET is_default = 1 WHERE id = ?", (resume_id,)
            )
            connection.commit()
        finally:
            connection.close()

    def delete(self, resume_id: int) -> None:
        connection = get_connection()
        try:
            connection.execute("DELETE FROM resumes WHERE id = ?", (resume_id,))
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _row_to_resume(row) -> Resume:
        return Resume(
            id=row["id"],
            file_name=row["file_name"],
            file_path=row["file_path"],
            is_default=bool(row["is_default"]),
            notes=row["notes"] or "",
            uploaded_at=row["uploaded_at"],
        )


class JobRepository:
    def save_jobs(self, jobs: list[Job]) -> list[Job]:
        connection = get_connection()
        try:
            saved = []
            for job in jobs:
                existing = None
                if job.url:
                    existing = connection.execute(
                        "SELECT id FROM jobs WHERE url = ?", (job.url,)
                    ).fetchone()

                if existing:
                    connection.execute(
                        """
                        UPDATE jobs SET
                            title = ?, company = ?, location = ?, source = ?,
                            posted_date = ?, description = ?, employment_type = ?,
                            easy_apply = ?
                        WHERE id = ?
                        """,
                        (
                            job.title,
                            job.company,
                            job.location,
                            job.source,
                            job.posted_date,
                            job.description,
                            job.employment_type,
                            int(job.easy_apply),
                            existing["id"],
                        ),
                    )
                    job.id = existing["id"]
                else:
                    cursor = connection.execute(
                        """
                        INSERT INTO jobs (
                            title, company, location, source, url, posted_date,
                            description, employment_type, easy_apply, score, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            job.title,
                            job.company,
                            job.location,
                            job.source,
                            job.url,
                            job.posted_date,
                            job.description,
                            job.employment_type,
                            int(job.easy_apply),
                            job.score,
                            job.status,
                        ),
                    )
                    job.id = cursor.lastrowid
                saved.append(job)
            connection.commit()
            return saved
        finally:
            connection.close()

    def list_all(self) -> list[Job]:
        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_job(row) for row in rows]
        finally:
            connection.close()

    def get_by_id(self, job_id: int) -> Job | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return self._row_to_job(row) if row else None
        finally:
            connection.close()

    def update_status(self, job_id: int, status: str) -> None:
        connection = get_connection()
        try:
            connection.execute(
                "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
            )
            connection.commit()
        finally:
            connection.close()

    def update_score(self, job_id: int, score: float) -> None:
        connection = get_connection()
        try:
            connection.execute(
                "UPDATE jobs SET score = ? WHERE id = ?", (score, job_id)
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _row_to_job(row) -> Job:
        return Job(
            id=row["id"],
            title=row["title"],
            company=row["company"],
            location=row["location"] or "",
            source=row["source"] or "",
            url=row["url"] or "",
            posted_date=row["posted_date"] or "",
            description=row["description"] or "",
            employment_type=row["employment_type"] or "",
            easy_apply=bool(row["easy_apply"]),
            score=row["score"],
            status=row["status"] or "New",
            created_at=row["created_at"],
        )


class ApplicationRepository:
    def save_to_tracker(self, job_id: int, resume_id: int | None = None) -> int:
        connection = get_connection()
        try:
            existing = connection.execute(
                "SELECT id FROM applications WHERE job_id = ?", (job_id,)
            ).fetchone()
            if existing:
                return existing["id"]

            cursor = connection.execute(
                "INSERT INTO applications (job_id, resume_id, status) VALUES (?, ?, ?)",
                (job_id, resume_id, "Saved"),
            )
            connection.execute(
                "UPDATE jobs SET status = 'Saved' WHERE id = ?", (job_id,)
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    def list_all(self) -> list[Application]:
        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT * FROM applications ORDER BY created_at DESC"
            ).fetchall()
            return [
                Application(
                    id=row["id"],
                    job_id=row["job_id"],
                    resume_id=row["resume_id"],
                    date_applied=row["date_applied"] or "",
                    status=row["status"] or "Applied",
                    recruiter_name=row["recruiter_name"] or "",
                    recruiter_contact=row["recruiter_contact"] or "",
                    salary_offered=row["salary_offered"] or "",
                    notes=row["notes"] or "",
                    follow_up_date=row["follow_up_date"] or "",
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]
        finally:
            connection.close()


class ScoreRepository:
    def get_by_job_id(self, job_id: int) -> JobScore | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM job_scores WHERE job_id = ?", (job_id,)
            ).fetchone()
            return self._row_to_score(row) if row else None
        finally:
            connection.close()

    def save(self, score: JobScore) -> int:
        connection = get_connection()
        try:
            connection.execute("DELETE FROM job_scores WHERE job_id = ?", (score.job_id,))
            cursor = connection.execute(
                """
                INSERT INTO job_scores (
                    job_id, score, matched_keywords, missing_keywords, reasoning, recommendation
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    score.job_id,
                    score.score,
                    json.dumps(score.matched_keywords),
                    json.dumps(score.missing_keywords),
                    score.reasoning,
                    score.recommendation,
                ),
            )
            connection.execute(
                "UPDATE jobs SET score = ? WHERE id = ?", (score.score, score.job_id)
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    @staticmethod
    def _row_to_score(row) -> JobScore:
        return JobScore(
            id=row["id"],
            job_id=row["job_id"],
            score=row["score"],
            matched_keywords=json.loads(row["matched_keywords"] or "[]"),
            missing_keywords=json.loads(row["missing_keywords"] or "[]"),
            reasoning=row["reasoning"] or "",
            recommendation=row["recommendation"] or "",
            created_at=row["created_at"],
        )
