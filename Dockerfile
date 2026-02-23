# # One-stage build for docs-to-ai MCP server using UV


FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install only runtime dependencies for Debian
RUN apt-get update && apt-get install -y --no-install-recommends libmupdf-dev libfreetype6 libharfbuzz0b libopenjp2-7 libjbig2dec0 libjpeg62-turbo zlib1g 

# Set working directory
WORKDIR /app

# Copy manifests first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies only (cached). --locked to ensure the dependencies in the lock file are used.  The path to the uv cache is on the image, and gets saved in the Windows folder: C:\Users\<You>\AppData\Local\uv\Cache
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv  uv sync --no-install-project


# Copy app code (while not copying any file mentioned in the .dockerignore)
COPY . .

# Pre-download and cache models to be included in the image
RUN uv run python app/download_models.py

# Expose HTTP port
EXPOSE 38777

# Entrypoint runs both stdio and HTTP transports
ENTRYPOINT ["uv", "run", "python", "mcp_server.py"]

