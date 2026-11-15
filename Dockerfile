# Multi-Agent Automated Code Review Board
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and configurations
COPY config/ config/
COPY core/ core/
COPY agents/ agents/
COPY plugins/ plugins/
COPY reporting/ reporting/
COPY cli/ cli/
COPY knowledge_base/ knowledge_base/
COPY samples/ samples/
COPY pyproject.toml .

# Create non-root user and prepare runtime directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/output && \
    chown -R appuser:appuser /app

USER appuser

# Entrypoint default to CLI
ENTRYPOINT ["python", "-m", "cli.main"]
CMD ["--help"]
