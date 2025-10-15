# syntax=docker/dockerfile:1

# Stage 1: Builder
FROM python:3.13-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmupdf-dev \
 && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only dependency list first for caching
COPY requirements.txt .


RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir sentence-transformers

# Install Python dependencies into a clean target directory
# RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt \
#  && find /install -type d -name "__pycache__" -exec rm -rf {} + \
#  && find /install -type f -name "*.pyc" -delete


# Stage 2: Runtime
FROM python:3.13-slim

# Copy only the installed dependencies
COPY --from=builder /install /usr/local

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy application source code
COPY --chown=appuser:appuser . .

# Make sure writable directories exist
RUN mkdir -p /app/chroma_db /app/doc_cache /app/docs && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK CMD python -c "import mcp, chromadb, sentence_transformers" || exit 1

# Default command
CMD ["python", "mcp_server.py"]
