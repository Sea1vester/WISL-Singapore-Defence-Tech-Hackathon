import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _ensure_parent_dir(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    _ensure_parent_dir(settings.database_path)
    conn = sqlite3.connect(settings.database_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_migrations() -> None:
    _ensure_parent_dir(settings.database_path)
    with db_session() as conn:
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            conn.executescript(sql_file.read_text())
