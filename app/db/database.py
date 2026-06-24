import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "app.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _apply_migrations(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "easy_apply" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN easy_apply INTEGER NOT NULL DEFAULT 0")
    if "preferred_resume_id" not in columns:
        connection.execute(
            "ALTER TABLE jobs ADD COLUMN preferred_resume_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL"
        )

    tailored_resume_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(tailored_resumes)")
    }
    if tailored_resume_columns and "source_resume_path" not in tailored_resume_columns:
        connection.execute("ALTER TABLE tailored_resumes ADD COLUMN source_resume_path TEXT")

    _migrate_applications_table(connection)


def _migrate_applications_table(connection: sqlite3.Connection) -> None:
    """Rebuilds `applications` to make job_id nullable (for manually-added
    applications not tied to a scraped job) and add the new denormalized
    fields. SQLite can't relax a NOT NULL constraint with ALTER TABLE, so
    this does the standard rebuild-and-swap, backfilling the new columns
    from `jobs` for any pre-existing rows.
    """
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(applications)")}
    if not columns or "company_name" in columns:
        return

    connection.execute(
        """
        CREATE TABLE applications_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
            company_name TEXT,
            job_title TEXT,
            job_url TEXT,
            source TEXT,
            date_applied TEXT,
            status TEXT DEFAULT 'Saved',
            resume_id INTEGER REFERENCES resumes(id) ON DELETE SET NULL,
            resume_path TEXT,
            salary_offered TEXT,
            recruiter_name TEXT,
            recruiter_contact TEXT,
            notes TEXT,
            follow_up_date TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    connection.execute(
        """
        INSERT INTO applications_new (
            id, job_id, company_name, job_title, job_url, source,
            date_applied, status, resume_id, resume_path, salary_offered,
            recruiter_name, recruiter_contact, notes, follow_up_date,
            created_at, updated_at
        )
        SELECT
            applications.id, applications.job_id,
            jobs.company, jobs.title, jobs.url, jobs.source,
            applications.date_applied, applications.status,
            applications.resume_id, resumes.file_path, applications.salary_offered,
            applications.recruiter_name, applications.recruiter_contact,
            applications.notes, applications.follow_up_date,
            applications.created_at, applications.updated_at
        FROM applications
        LEFT JOIN jobs ON jobs.id = applications.job_id
        LEFT JOIN resumes ON resumes.id = applications.resume_id
        """
    )
    connection.execute("DROP TABLE applications")
    connection.execute("ALTER TABLE applications_new RENAME TO applications")
    connection.commit()


def init_db() -> None:
    connection = get_connection()
    try:
        connection.executescript(SCHEMA_PATH.read_text())
        _apply_migrations(connection)
        connection.execute(
            "INSERT OR IGNORE INTO profile_settings (id, visa_status, work_preference) "
            "VALUES (1, 'H-1B Transfer — no sponsorship', 'Any')"
        )
        connection.commit()
    finally:
        connection.close()
