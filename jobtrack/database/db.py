import logging
import sqlite3
from contextlib import closing
from pathlib import Path

from config import Config


logger = logging.getLogger(__name__)

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        company_name TEXT NOT NULL,
        job_role TEXT NOT NULL,
        job_location TEXT,
        salary TEXT,
        application_status TEXT NOT NULL DEFAULT 'Applied'
            CHECK (application_status IN (
                'Applied', 'Interview', 'Selected', 'Rejected'
            )),
        applied_date TEXT NOT NULL,
        job_description TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """,
)


def get_connection(database_path: str | Path = Config.DATABASE) -> sqlite3.Connection:
    """Open a SQLite connection with foreign-key enforcement enabled."""
    connection = sqlite3.connect(database_path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def init_db(database_path: str | Path = Config.DATABASE) -> None:
    """Create the database directory and tables if they do not already exist."""
    path = Path(database_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(get_connection(path)) as connection:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
    except (OSError, sqlite3.Error):
        logger.exception("Could not initialize the JobTrack database at %s", path)
        raise