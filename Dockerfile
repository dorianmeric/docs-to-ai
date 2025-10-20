# # Multi-stage build for docs-to-ai MCP server using UV
# FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

# # Install build dependencies for Debian (needed for compiling Python packages)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     libmupdf-dev \
#     libfreetype6-dev \
#     libharfbuzz-dev \
#     libopenjp2-7-dev \
#     libjbig2dec0-dev \
#     libjpeg-dev \
#     zlib1g-dev \
#     && rm -rf /var/lib/apt/lists/*

# # Set working directory
# WORKDIR /app

# # Enable bytecode compilation for faster startup
# ENV UV_COMPILE_BYTECODE=1

# # Copy dependency files
# COPY pyproject.toml uv.lock ./

# # Install dependencies using UV (no editable install yet)
# RUN uv sync --frozen --no-install-project

# # Copy application code
# COPY *.py ./
# COPY app/ ./app/
# COPY LICENSE README.md ./
# COPY pyproject.toml uv.lock ./

# # Now install the project itself
# RUN uv sync --frozen






# Stage 2: Runtime stage
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install only runtime dependencies for Debian
RUN apt-get update && apt-get install -y --no-install-recommends libmupdf-dev libfreetype6 libharfbuzz0b libopenjp2-7 libjbig2dec0 libjpeg62-turbo zlib1g 

# Set working directory
WORKDIR /app

# Copy manifests first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (cached). --locked to ensure the dependencies in the lock file are used. 
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target="C:/Temp/uv-cache" uv sync --no-install-project

# Copy app code (while not copying any file mentioned in the .dockerignore)
COPY . .

# Expose HTTP port
EXPOSE 38777

# Entrypoint runs both stdio and HTTP transports
ENTRYPOINT ["uv", "run", "python", "mcp_server.py"]






# # Create non-root user for security (Debian syntax)
# RUN useradd -m -u 1000 appuser

# # Copy the entire application and virtual environment from builder
# # COPY --from=builder --chown=appuser:appuser /app /app
# COPY --chown=appuser:appuser *.py ./
# COPY --chown=appuser:appuser app/*.py ./app/
# COPY pyproject.toml uv.lock ./
# COPY LICENSE README.md ./

# # Create necessary directories with proper permissions
# RUN mkdir -p /app/cache/chromadb /app/cache/doc_cache /app/my-docs && \
#     chown -R appuser:appuser /app

# # Switch to non-root user
# USER appuser

# # ensures that the python output i.e. the stdout and stderr streams are sent straight to terminal (e.g. your container log) without being first buffered
# ENV PYTHONUNBUFFERED=1

# # Expose any ports if needed (not required for MCP stdio)
# # EXPOSE 8000

# # Health check (optional - checks if Python imports work)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD uv run python -c "import mcp, chromadb, sentence_transformers" || exit 1

# # Default command: run the MCP server using UV
# CMD ["uv", "run", "mcp_server.py"]
