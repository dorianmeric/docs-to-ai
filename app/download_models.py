# app/download_models.py
from sentence_transformers import SentenceTransformer, CrossEncoder
from .errors import explain
from .logging_utils import log_error, log_info, log_success, log_warn
from .config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    EMBEDDING_QUERY_PROMPT,
    USE_RERANKER,
    RERANKER_MODEL,
    TOKENIZER_MODEL,
)
import sys


def download_tokenizer():
    """
    Pre-cache the tiktoken encoding used for chunk sizing.

    tiktoken fetches its BPE data on first use, which would otherwise need
    network access at ingest time inside the container.
    """
    log_info(f"Caching tokenizer: {TOKENIZER_MODEL}", component="Download")
    try:
        import tiktoken
        tiktoken.get_encoding(TOKENIZER_MODEL)
        log_success(f"Successfully cached {TOKENIZER_MODEL}", component="Download")
    except Exception as e:
        # Chunking falls back to an estimate, so this is not fatal
        log_warn(explain(e, context="tokenizer download"), component="Download")


def download_marker_models():
    """
    Pre-cache the Marker models used for scanned PDFs.

    Marker is optional, so this only runs when it is installed. In the Docker
    build it bakes the models into the image, which keeps the running container
    from downloading them on the first scan.
    """
    from .config import MARKER_MODE
    try:
        import marker  # noqa: F401
    except ImportError:
        log_info(
            "Marker is not installed (optional extra), so scanned PDFs cannot be read. "
            "Install it with 'uv sync --extra marker'. (optional)",
            component="Download",
        )
        return

    log_info(f"Downloading and caching the Marker models (MARKER_MODE={MARKER_MODE})", component="Download")
    try:
        from .ocr import ocr_status
        available, detail = ocr_status()
        if not available:
            log_warn(detail, component="Download")
            return
        from marker.models import create_model_dict
        local_only = MARKER_MODE in ("fast", "no_ocr")
        create_model_dict(load_indra=local_only, no_server=local_only)
        log_success(f"Successfully cached the Marker models ({detail})", component="Download")
    except Exception as e:
        log_warn(explain(e, context="marker model download"), component="Download")
        log_warn(
            "Scanned PDFs stay empty until the Marker models can be downloaded. Retry with network "
            "access, or set OCR_ENABLED=False to skip OCR entirely.",
            component="Download",
        )


def download_models():
    """
    Downloads and caches the sentence transformer and cross-encoder models.
    This script is intended to be run during the Docker build process
    to pre-warm the cache and bake the models into the image.
    """
    log_info("Downloading and caching embedding model...", component="Download")
    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
        get_dim = getattr(model, 'get_embedding_dimension', None) or model.get_sentence_embedding_dimension
        actual_dim = int(get_dim())
        log_success(f"Successfully cached {EMBEDDING_MODEL} ({actual_dim}-dim)", component="Download")
        if actual_dim != EMBEDDING_DIMENSION:
            log_warn(
                f"EMBEDDING_DIMENSION={EMBEDDING_DIMENSION} does not match "
                f"{EMBEDDING_MODEL} ({actual_dim}-dim). Set EMBEDDING_DIMENSION={actual_dim} "
                "(the model's real size is used at runtime).",
                component="Download",
            )
    except Exception as e:
        log_error(explain(e, context="embedding model download"), component="Download")
        log_error(
            "Fix: check the model name in EMBEDDING_MODEL and the network connection, then run "
            "'python -m app.download_models' again.",
            component="Download",
        )
        sys.exit(1)

    if EMBEDDING_QUERY_PROMPT:
        log_info("Using custom EMBEDDING_QUERY_PROMPT for search queries", component="Download")

    download_tokenizer()
    download_marker_models()

    if USE_RERANKER:
        log_info("Downloading and caching re-ranker model...", component="Download")
        try:
            CrossEncoder(RERANKER_MODEL)
            log_success(f"Successfully cached {RERANKER_MODEL}", component="Download")
        except Exception as e:
            log_warn(explain(e, context="re-ranker download"), component="Download")
            log_warn(
                "Re-ranking stays off until the model is available. Retry with network access, or set "
                "USE_RERANKER=False to run without re-ranking.",
                component="Download",
            )
            # Not fatal: re-ranking is optional

if __name__ == "__main__":
    download_models()
