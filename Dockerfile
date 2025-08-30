FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt requirements-memory.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-memory.txt

# Application code
COPY backend ./backend
COPY models ./models
COPY scripts ./scripts
COPY storage ./storage

# Create necessary directories
RUN mkdir -p /app/storage/chroma \
    /app/storage/sessions \
    /app/storage/summaries \
    /app/storage/ingest \
    /app/storage/uploads \
    /app/storage/profile

# Permissions for scripts
RUN chmod +x /app/scripts/*.sh || true

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV AIR4_VERSION=0.12.0-docker

CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]