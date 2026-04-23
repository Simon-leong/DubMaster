import os
import sys
from pathlib import Path

# Ensure project root is in sys.path for multi-agent framework imports
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(Path(_PROJECT_ROOT) / ".env", encoding="utf-8-sig")
except Exception:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .routes import upload, generations
from .services.database import init_db

app = FastAPI(title="DubMaster API", version="2.0.0")

# Initialise SQLite tables on startup.
init_db()

# ── CORS ─────────────────────────────────────────────────────────────────────
# In production (Fly.io), the React frontend is served by this same FastAPI
# process from dist/, so CORS is not needed for same-origin requests.
# In local development, set ALLOWED_ORIGINS to "" (unset) to use localhost defaults.
# If you deploy frontend separately, set: ALLOWED_ORIGINS="https://your-frontend-url"
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
_explicit_origins: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

_dev_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_explicit_origins if _explicit_origins else _dev_origins,
    allow_origin_regex=(
        None if _explicit_origins
        else r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(upload.router)
app.include_router(generations.router)


@app.get("/health")
async def health():
    return {"status": "ok", "message": "DubMaster API is running (v2 — multi-agent pipeline)"}


# ── Static file serving (production: frontend built into dist/) ───────────────
# When the Dockerfile builds the React frontend into dist/, FastAPI serves it.
# This allows a single unified URL for both frontend and API on Fly.io.
_dist_path = Path(__file__).resolve().parent.parent.parent / "dist"
if _dist_path.exists():
    # Serve hashed JS/CSS asset bundles (long cache TTL is set by browser via
    # the immutable filenames Vite generates)
    app.mount("/assets", StaticFiles(directory=str(_dist_path / "assets")), name="assets")
    if (_dist_path / "demos").exists():
        app.mount("/demos", StaticFiles(directory=str(_dist_path / "demos")), name="demos")

    # SPA catch-all: serve index.html for any path not matched by API routes above.
    # This enables React Router to handle client-side navigation.
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        index = _dist_path / "index.html"
        return FileResponse(str(index))
else:
    # Local development mode: no dist/ — just confirm the API is alive
    @app.get("/")
    async def root():
        return {"message": "DubMaster API is running (v2 — multi-agent pipeline)"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
