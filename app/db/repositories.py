import json

from app.db.database import get_connection
from app.models.application import Application
from app.models.job import Job
from app.models.profile import BlacklistCompany, ProfileSettings, TargetRole
from app.models.resume import Resume
from app.models.score import JobScore
from app.models.search_preferences import SearchPreferences
from app.models.tailored_resume import TailoredResume
from app.utils import crypto
from app.utils.constants import ADDITIONAL_BLACKLISTED_COMPANIES, DEFAULT_BLACKLISTED_COMPANIES


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
                profile.scoring_provider = row["scoring_provider"] or "anthropic"
                profile.scoring_model = row["scoring_model"] or "claude-haiku-4-5-20251001"
                profile.tailoring_provider = row["tailoring_provider"] or "anthropic"
                profile.tailoring_model = row["tailoring_model"] or "claude-sonnet-4-6"
                profile.anthropic_api_key = crypto.decrypt(row["anthropic_api_key"] or "")
                profile.openai_api_key = crypto.decrypt(row["openai_api_key"] or "")
                profile.google_api_key = crypto.decrypt(row["google_api_key"] or "")
                profile.ollama_base_url = row["ollama_base_url"] or "http://localhost:11434"

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

    def save_llm_settings(self, profile: ProfileSettings) -> None:
        """Writes only the 8 AI-provider columns, independent of the main
        Save button's save() — so testing/saving provider settings never
        touches profile fields, target roles, or the blacklist.
        """
        connection = get_connection()
        try:
            connection.execute(
                """
                UPDATE profile_settings SET
                    scoring_provider = ?, scoring_model = ?,
                    tailoring_provider = ?, tailoring_model = ?,
                    anthropic_api_key = ?, openai_api_key = ?, google_api_key = ?,
                    ollama_base_url = ?, updated_at = datetime('now')
                WHERE id = 1
                """,
                (
                    profile.scoring_provider,
                    profile.scoring_model,
                    profile.tailoring_provider,
                    profile.tailoring_model,
                    crypto.encrypt(profile.anthropic_api_key),
                    crypto.encrypt(profile.openai_api_key),
                    crypto.encrypt(profile.google_api_key),
                    profile.ollama_base_url,
                ),
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

    def seed_additional_defaults(self) -> None:
        connection = get_connection()
        try:
            connection.executemany(
                "INSERT OR IGNORE INTO blacklist_companies (company_name) VALUES (?)",
                [(name,) for name in ADDITIONAL_BLACKLISTED_COMPANIES],
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

    def set_preferred_resume(self, job_id: int, resume_id: int) -> None:
        connection = get_connection()
        try:
            connection.execute(
                "UPDATE jobs SET preferred_resume_id = ? WHERE id = ?", (resume_id, job_id)
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
            preferred_resume_id=row["preferred_resume_id"],
            created_at=row["created_at"],
        )


class ApplicationRepository:
    def save_to_tracker(self, job, resume_id: int | None = None, resume_path: str = "") -> int:
        connection = get_connection()
        try:
            existing = connection.execute(
                "SELECT id FROM applications WHERE job_id = ?", (job.id,)
            ).fetchone()
            if existing:
                return existing["id"]

            cursor = connection.execute(
                """
                INSERT INTO applications (
                    job_id, company_name, job_title, job_url, source,
                    status, resume_id, resume_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.company,
                    job.title,
                    job.url,
                    job.source,
                    "Saved",
                    resume_id,
                    resume_path,
                ),
            )
            connection.execute("UPDATE jobs SET status = 'Saved' WHERE id = ?", (job.id,))
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    def get_by_job_id(self, job_id: int) -> Application | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM applications WHERE job_id = ?", (job_id,)
            ).fetchone()
            return self._row_to_application(row) if row else None
        finally:
            connection.close()

    def get_by_id(self, application_id: int) -> Application | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            return self._row_to_application(row) if row else None
        finally:
            connection.close()

    def create(self, application: Application) -> int:
        connection = get_connection()
        try:
            cursor = connection.execute(
                """
                INSERT INTO applications (
                    job_id, company_name, job_title, job_url, source,
                    date_applied, status, resume_id, resume_path,
                    salary_offered, recruiter_name, recruiter_contact,
                    notes, follow_up_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application.job_id,
                    application.company_name,
                    application.job_title,
                    application.job_url,
                    application.source,
                    application.date_applied,
                    application.status,
                    application.resume_id,
                    application.resume_path,
                    application.salary_offered,
                    application.recruiter_name,
                    application.recruiter_contact,
                    application.notes,
                    application.follow_up_date,
                ),
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    def update(self, application: Application) -> None:
        connection = get_connection()
        try:
            connection.execute(
                """
                UPDATE applications SET
                    company_name = ?, job_title = ?, job_url = ?, source = ?,
                    date_applied = ?, status = ?, resume_id = ?, resume_path = ?,
                    salary_offered = ?, recruiter_name = ?, recruiter_contact = ?,
                    notes = ?, follow_up_date = ?, updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    application.company_name,
                    application.job_title,
                    application.job_url,
                    application.source,
                    application.date_applied,
                    application.status,
                    application.resume_id,
                    application.resume_path,
                    application.salary_offered,
                    application.recruiter_name,
                    application.recruiter_contact,
                    application.notes,
                    application.follow_up_date,
                    application.id,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def mark_applied(self, application_id: int, date_applied: str) -> None:
        connection = get_connection()
        try:
            connection.execute(
                """
                UPDATE applications SET status = 'Applied', date_applied = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (date_applied, application_id),
            )
            connection.commit()
        finally:
            connection.close()

    def list_all(self) -> list[Application]:
        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT * FROM applications ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_application(row) for row in rows]
        finally:
            connection.close()

    @staticmethod
    def _row_to_application(row) -> Application:
        return Application(
            id=row["id"],
            job_id=row["job_id"],
            company_name=row["company_name"] or "",
            job_title=row["job_title"] or "",
            job_url=row["job_url"] or "",
            source=row["source"] or "",
            date_applied=row["date_applied"] or "",
            status=row["status"] or "Saved",
            resume_id=row["resume_id"],
            resume_path=row["resume_path"] or "",
            salary_offered=row["salary_offered"] or "",
            recruiter_name=row["recruiter_name"] or "",
            recruiter_contact=row["recruiter_contact"] or "",
            notes=row["notes"] or "",
            follow_up_date=row["follow_up_date"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


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


class TailoredResumeRepository:
    def save(self, tailored: TailoredResume) -> int:
        connection = get_connection()
        try:
            cursor = connection.execute(
                """
                INSERT INTO tailored_resumes (
                    job_id, resume_id, company, job_title, score,
                    file_name, file_path, tailored_text, source_resume_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tailored.job_id,
                    tailored.resume_id,
                    tailored.company,
                    tailored.job_title,
                    tailored.score,
                    tailored.file_name,
                    tailored.file_path,
                    tailored.tailored_text,
                    tailored.source_resume_path,
                ),
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()

    def list_all(self) -> list[TailoredResume]:
        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT * FROM tailored_resumes ORDER BY created_at DESC"
            ).fetchall()
            return [self._row_to_tailored_resume(row) for row in rows]
        finally:
            connection.close()

    def get_by_id(self, tailored_resume_id: int) -> TailoredResume | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM tailored_resumes WHERE id = ?", (tailored_resume_id,)
            ).fetchone()
            return self._row_to_tailored_resume(row) if row else None
        finally:
            connection.close()

    def get_by_job_id(self, job_id: int) -> TailoredResume | None:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM tailored_resumes WHERE job_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            return self._row_to_tailored_resume(row) if row else None
        finally:
            connection.close()

    def update_text_and_file(self, tailored_resume_id: int, text: str, file_path: str) -> None:
        connection = get_connection()
        try:
            connection.execute(
                "UPDATE tailored_resumes SET tailored_text = ?, file_path = ? WHERE id = ?",
                (text, file_path, tailored_resume_id),
            )
            connection.commit()
        finally:
            connection.close()

    def delete(self, tailored_resume_id: int) -> None:
        connection = get_connection()
        try:
            connection.execute(
                "DELETE FROM tailored_resumes WHERE id = ?", (tailored_resume_id,)
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _row_to_tailored_resume(row) -> TailoredResume:
        return TailoredResume(
            id=row["id"],
            job_id=row["job_id"],
            resume_id=row["resume_id"],
            company=row["company"] or "",
            job_title=row["job_title"] or "",
            score=row["score"],
            file_name=row["file_name"],
            file_path=row["file_path"],
            tailored_text=row["tailored_text"] or "",
            source_resume_path=row["source_resume_path"] or "",
            created_at=row["created_at"],
        )


class TargetRoleRepository:
    def list_active(self) -> list[TargetRole]:
        connection = get_connection()
        try:
            rows = connection.execute(
                "SELECT * FROM target_roles WHERE is_active = 1 ORDER BY id"
            ).fetchall()
            return [
                TargetRole(
                    id=row["id"],
                    role_title=row["role_title"],
                    role_description=row["role_description"] or "",
                    is_active=bool(row["is_active"]),
                )
                for row in rows
            ]
        finally:
            connection.close()

    def add(self, role_title: str, role_description: str = "") -> int:
        connection = get_connection()
        try:
            existing = connection.execute(
                "SELECT id FROM target_roles WHERE role_title = ? COLLATE NOCASE",
                (role_title,),
            ).fetchone()
            if existing:
                return existing["id"]

            cursor = connection.execute(
                "INSERT INTO target_roles (role_title, role_description, is_active) VALUES (?, ?, 1)",
                (role_title, role_description),
            )
            connection.commit()
            return cursor.lastrowid
        finally:
            connection.close()


class SearchPreferencesRepository:
    def get(self) -> SearchPreferences:
        connection = get_connection()
        try:
            row = connection.execute(
                "SELECT * FROM search_preferences WHERE id = 1"
            ).fetchone()
            if row is None:
                return SearchPreferences()
            return SearchPreferences(
                location_scope=row["location_scope"] or "all",
                selected_states=json.loads(row["selected_states"] or "[]"),
                selected_titles=json.loads(row["selected_titles"] or "[]"),
                date_posted_filter=row["date_posted_filter"] or "7days",
                remote_only=bool(row["remote_only"]),
                fulltime_only=bool(row["fulltime_only"]),
                easy_apply_only=bool(row["easy_apply_only"]),
                hide_sponsorship_restricted=bool(row["hide_sponsorship_restricted"]),
                source=row["source"] or "Both",
                theme=row["theme"] or "dark",
                updated_at=row["updated_at"],
            )
        finally:
            connection.close()

    def save(self, preferences: SearchPreferences) -> None:
        connection = get_connection()
        try:
            connection.execute(
                """
                INSERT INTO search_preferences (
                    id, location_scope, selected_states, selected_titles,
                    date_posted_filter, remote_only, fulltime_only,
                    easy_apply_only, hide_sponsorship_restricted, source, theme, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    location_scope = excluded.location_scope,
                    selected_states = excluded.selected_states,
                    selected_titles = excluded.selected_titles,
                    date_posted_filter = excluded.date_posted_filter,
                    remote_only = excluded.remote_only,
                    fulltime_only = excluded.fulltime_only,
                    easy_apply_only = excluded.easy_apply_only,
                    hide_sponsorship_restricted = excluded.hide_sponsorship_restricted,
                    source = excluded.source,
                    theme = excluded.theme,
                    updated_at = datetime('now')
                """,
                (
                    preferences.location_scope,
                    json.dumps(preferences.selected_states),
                    json.dumps(preferences.selected_titles),
                    preferences.date_posted_filter,
                    int(preferences.remote_only),
                    int(preferences.fulltime_only),
                    int(preferences.easy_apply_only),
                    int(preferences.hide_sponsorship_restricted),
                    preferences.source,
                    preferences.theme,
                ),
            )
            connection.commit()
        finally:
            connection.close()
