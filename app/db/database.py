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
