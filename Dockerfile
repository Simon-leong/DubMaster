# =============================================================================
# DubMaster — Multi-stage Dockerfile
# Stage 1: Build React frontend (Node 20)
# Stage 2: Install Python dependencies
# Stage 3: Runtime image (Python 3.11-slim + ffmpeg)
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: Build React frontend
# ─────────────────────────────────────────────────────────────────────────────
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# Install Node dependencies first (cache layer)
COPY package.json package-lock.json ./
RUN npm ci

# Copy frontend source files
COPY vite.config.ts tsconfig.json index.html ./
COPY src/ ./src/
COPY public/ ./public/

# VITE_API_BASE_URL="" means the frontend uses relative paths (same origin).
# e.g., fetch("/upload/video") instead of fetch("http://localhost:8000/upload/video")
# This works because FastAPI serves both the static files AND the API routes
# on the same port (8080) in production.
# The trailing .replace(/\/$/, '') in api.ts handles the empty string correctly.
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build
# Output: /frontend/dist/


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: Install Python dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS py-builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy and merge both requirements files
COPY requirements.txt ./root-requirements.txt
COPY backend/requirements.txt ./backend-requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        -r root-requirements.txt \
        -r backend-requirements.txt


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3: Final runtime image
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# ffmpeg is required by moviepy and pydub at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from py-builder
COPY --from=py-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=py-builder /usr/local/bin /usr/local/bin

# Copy the built React frontend from frontend-builder
COPY --from=frontend-builder /frontend/dist ./dist

# Copy application source — all Python modules needed by the backend and
# the multi-agent pipeline
COPY config.yaml ./
COPY backend/ ./backend/

# Root-level Python modules (the multi-agent pipeline)
COPY __init__.py agents.py critiquers.py experts.py llm.py mixer.py \
     plan.py router.py run.py tools.py tools_v2.py tot.py tree_memory.py ./

# Supporting packages
COPY utils/ ./utils/
COPY tool/ ./tool/
COPY template/ ./template/

# Create persistent data directories.
# In production these are overridden by the Fly.io Volume mount at /data.
RUN mkdir -p /data/uploads /data/outputs

# Environment defaults — all overridden by Fly.io secrets / env vars
ENV DATABASE_PATH=/data/dubmaster.db \
    UPLOAD_DIR=/data/uploads \
    OUTPUT_DIR=/data/outputs \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Fly.io uses port 8080 by default
EXPOSE 8080

# Single worker to avoid SQLite write conflicts from concurrent threads.
# The multi-agent pipeline runs in background threads (not processes), so
# --workers 1 is safe and correct for this architecture.
# --timeout-keep-alive 600: keeps status-polling connections alive for 10 min,
# which is sufficient for long-running generation jobs.
CMD ["uvicorn", "backend.app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--timeout-keep-alive", "600"]
