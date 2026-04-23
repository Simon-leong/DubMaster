import os
import uuid
import shutil
from pathlib import Path
from .database import get_connection

_THIS_FILE = Path(os.path.abspath(__file__))

# Use UPLOAD_DIR env var if set (production: Fly.io Volume at /data/uploads).
# Fall back to backend/uploads/ for local development.
_DEFAULT_UPLOAD_DIR = _THIS_FILE.parent.parent.parent / "uploads"
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(_DEFAULT_UPLOAD_DIR)))


class StorageService:
    def __init__(self):
        _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    def save_file(self, filename: str, file_bytes: bytes) -> str:
        ref = f"ref_{uuid.uuid4().hex}"
        ext = os.path.splitext(filename)[1] or ""
        dest = _UPLOAD_DIR / f"{ref}{ext}"
        dest.write_bytes(file_bytes)

        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO uploads (ref, filename, filepath) VALUES (?, ?, ?)",
                (ref, filename, str(dest)),
            )
            conn.commit()
        finally:
            conn.close()
        return ref

    def get_filepath(self, ref: str) -> str | None:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT filepath FROM uploads WHERE ref = ?", (ref,)
            ).fetchone()
        finally:
            conn.close()
        if row and row["filepath"]:
            return row["filepath"]
        return None


storage_service = StorageService()
