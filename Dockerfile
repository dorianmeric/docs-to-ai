# # One-stage build for docs-to-ai MCP server using UV


FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Install only runtime dependencies for Debian. tesseract-ocr reads scanned
# PDFs, tesseract-ocr-eng is the English language pack; add more packs (e.g.
# tesseract-ocr-deu) and point OCR_LANG at them to read other languages.
RUN apt-get update && apt-get install -y --no-install-recommends libmupdf-dev libfreetype6 libharfbuzz0b libopenjp2-7 libjbig2dec0 libjpeg62-turbo zlib1g tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy manifests first for caching
COPY pyproject.toml uv.lock /app/

# Install dependencies (cached). --locked to ensure the dependencies in the lock file are used.
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv  uv sync --no-install-project

# ---------------------------------------------------------------------------
# Build-time configuration (override with: docker build --build-arg KEY=VALUE)
# These defaults match app/config.py. They are baked into the image as ENV so
# the pre-downloaded models and the runtime behaviour stay consistent.
# ---------------------------------------------------------------------------
ARG EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
ARG EMBEDDING_DIMENSION=1024
ARG EMBEDDING_BATCH_SIZE=32
ARG USE_GPU_ACCELERATION_IF_AVAILABLE=True
ARG GPU_DEVICE_INDEX=0
ARG USE_RERANKER=True
ARG RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ARG CHUNKING_STRATEGY=semantic
ARG CHUNK_SIZE=1024
ARG CHUNK_OVERLAP=200
ARG CHUNK_BY_TOKEN=True
ARG TOKENIZER_MODEL=cl100k_base
ARG PRESERVE_HEADINGS=True
ARG MAX_HEADING_CHUNK_SIZE=1024
ARG MIN_CHUNK_SIZE=50
ARG SEMANTIC_CHUNK_PERCENTILE=95
ARG SEMANTIC_CHUNK_MIN_SIZE=64
ARG SEMANTIC_CHUNK_MAX_SIZE=1024
ARG SEMANTIC_CHUNK_BUFFER_SIZE=1
ARG DEFAULT_SEARCH_RESULTS=10
ARG MAX_SEARCH_RESULTS=20
ARG RERANKER_TOP_N=50
ARG USE_BM25=True
ARG BM25_WEIGHT=0.3
ARG BM25_K1=1.5
ARG BM25_B=0.75
ARG RRF_K=60
ARG CHROMA_SPACE=cosine
ARG HNSW_EF_SEARCH=200
ARG HNSW_EF_CONSTRUCTION=200
ARG USE_FOLDER_AS_TOPIC=True
ARG DEFAULT_TOPIC=uncategorized
ARG CHROMA_COLLECTION_NAME=my-documents
ARG FULL_SCAN_ON_BOOT=False
ARG FOLDER_WATCHER_ACTIVE_ON_BOOT=True
ARG DEBOUNCE_SECONDS=10
ARG FULL_SCAN_INTERVAL_DAYS=7
ARG OCR_ENABLED=True
ARG OCR_MIN_TEXT_CHARS=20
ARG OCR_DPI=300
ARG OCR_LANG=eng
ARG OCR_MAX_PAGES=9999

ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
    EMBEDDING_DIMENSION=${EMBEDDING_DIMENSION} \
    EMBEDDING_BATCH_SIZE=${EMBEDDING_BATCH_SIZE} \
    USE_GPU_ACCELERATION_IF_AVAILABLE=${USE_GPU_ACCELERATION_IF_AVAILABLE} \
    GPU_DEVICE_INDEX=${GPU_DEVICE_INDEX} \
    USE_RERANKER=${USE_RERANKER} \
    RERANKER_MODEL=${RERANKER_MODEL} \
    CHUNKING_STRATEGY=${CHUNKING_STRATEGY} \
    CHUNK_SIZE=${CHUNK_SIZE} \
    CHUNK_OVERLAP=${CHUNK_OVERLAP} \
    CHUNK_BY_TOKEN=${CHUNK_BY_TOKEN} \
    TOKENIZER_MODEL=${TOKENIZER_MODEL} \
    PRESERVE_HEADINGS=${PRESERVE_HEADINGS} \
    MAX_HEADING_CHUNK_SIZE=${MAX_HEADING_CHUNK_SIZE} \
    MIN_CHUNK_SIZE=${MIN_CHUNK_SIZE} \
    SEMANTIC_CHUNK_PERCENTILE=${SEMANTIC_CHUNK_PERCENTILE} \
    SEMANTIC_CHUNK_MIN_SIZE=${SEMANTIC_CHUNK_MIN_SIZE} \
    SEMANTIC_CHUNK_MAX_SIZE=${SEMANTIC_CHUNK_MAX_SIZE} \
    SEMANTIC_CHUNK_BUFFER_SIZE=${SEMANTIC_CHUNK_BUFFER_SIZE} \
    DEFAULT_SEARCH_RESULTS=${DEFAULT_SEARCH_RESULTS} \
    MAX_SEARCH_RESULTS=${MAX_SEARCH_RESULTS} \
    RERANKER_TOP_N=${RERANKER_TOP_N} \
    USE_BM25=${USE_BM25} \
    BM25_WEIGHT=${BM25_WEIGHT} \
    BM25_K1=${BM25_K1} \
    BM25_B=${BM25_B} \
    RRF_K=${RRF_K} \
    CHROMA_SPACE=${CHROMA_SPACE} \
    HNSW_EF_SEARCH=${HNSW_EF_SEARCH} \
    HNSW_EF_CONSTRUCTION=${HNSW_EF_CONSTRUCTION} \
    USE_FOLDER_AS_TOPIC=${USE_FOLDER_AS_TOPIC} \
    DEFAULT_TOPIC=${DEFAULT_TOPIC} \
    CHROMA_COLLECTION_NAME=${CHROMA_COLLECTION_NAME} \
    FULL_SCAN_ON_BOOT=${FULL_SCAN_ON_BOOT} \
    FOLDER_WATCHER_ACTIVE_ON_BOOT=${FOLDER_WATCHER_ACTIVE_ON_BOOT} \
    DEBOUNCE_SECONDS=${DEBOUNCE_SECONDS} \
    FULL_SCAN_INTERVAL_DAYS=${FULL_SCAN_INTERVAL_DAYS} \
    OCR_ENABLED=${OCR_ENABLED} \
    OCR_MIN_TEXT_CHARS=${OCR_MIN_TEXT_CHARS} \
    OCR_DPI=${OCR_DPI} \
    OCR_LANG=${OCR_LANG} \
    OCR_MAX_PAGES=${OCR_MAX_PAGES}

# Network access is not guaranteed at runtime: bake the embedding/reranker
# models and the tiktoken BPE data into the image. Only the files the download
# needs are copied first, so editing the app code does not invalidate this
# (large) layer and force a re-download on every rebuild.
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache
COPY app/config.py app/errors.py app/logging_utils.py app/log_config.py app/download_models.py /app/app/
RUN uv run python -m app.download_models

# Copy the rest of the application code
COPY app/ /app/app/
COPY mcp_server.py /app/

# Expose HTTP port
EXPOSE 38777

# Entrypoint runs both stdio and HTTP transports
ENTRYPOINT ["uv", "run", "python", "mcp_server.py"]

