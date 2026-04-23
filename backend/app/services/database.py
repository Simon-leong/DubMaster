import os
import sqlite3
from pathlib import Path

_THIS_FILE = Path(os.path.abspath(__file__))

# Use DATABASE_PATH env var if set (production: Fly.io Volume at /data/dubmaster.db).
# Fall back to the local path inside backend/ for local development.
_DEFAULT_DB_PATH = _THIS_FILE.parent.parent.parent / "dubmaster.db"
_DB_PATH = Path(os.environ.get("DATABASE_PATH", str(_DEFAULT_DB_PATH)))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS generations (
                id              TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'pending',
                stage           TEXT DEFAULT 'uploading',
                stage_detail    TEXT DEFAULT '',
                art_title       TEXT,
                art_type        TEXT,
                art_duration    TEXT,
                art_heights     TEXT,
                audio_path      TEXT,
                video_path      TEXT,
                error_message   TEXT,
                prompt          TEXT,
                output_dir      TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS uploads (
                ref      TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                filepath TEXT NOT NULL DEFAULT ''
            );
        """)
        conn.commit()
    finally:
        conn.close()
