# ═══════════════════════════════════════════════════════════
#  FastAPI AI Services — Dockerfile
# ═══════════════════════════════════════════════════════════

# ── Base ────────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# System deps cho Presidio NLP models
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model cho Presidio (tiếng Anh + tiếng Việt fallback)
RUN python -m spacy download en_core_web_lg

# ── Development ─────────────────────────────────────────────
FROM base AS development
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Production ──────────────────────────────────────────────
FROM base AS production
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY . .

# Chạy với Gunicorn + Uvicorn workers trong production
CMD ["gunicorn", "app.main:app", \
     "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-"]
