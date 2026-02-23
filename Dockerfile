# One-stage build for docs-to-ai MCP server using UV

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install only runtime dependencies for Debian
RUN apt-get update && apt-get install -y --no-install-recommends libmupdf-dev libfreetype6 libharfbuzz0b libopenjp2-7 libjbig2dec0 libjpeg62-turbo zlib1g 

# Create directories
RUN mkdir -p /app /my-docs

# Copy manifests first for caching
COPY pyproject.toml uv.lock /app/

# Install dependencies (cached). --locked to ensure the dependencies in the lock file are used.
ENV UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv  uv sync --no-install-project

# Copy application code
COPY app/ /app/app/
COPY mcp_server.py /app/

# Pre-download and cache models to be included in the image
RUN uv run python -m app.download_models

# Expose HTTP port
EXPOSE 38777

# Set documents directory environment variable
ENV DOCS_DIR=/my-docs

# Entrypoint runs both stdio and HTTP transports
ENTRYPOINT ["uv", "run", "python", "mcp_server.py"]

