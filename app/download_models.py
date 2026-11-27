# app/download_models.py
from sentence_transformers import SentenceTransformer, CrossEncoder
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
    print(f"Caching tokenizer: {TOKENIZER_MODEL}", file=sys.stderr)
    try:
        import tiktoken
        tiktoken.get_encoding(TOKENIZER_MODEL)
        print(f"Successfully cached {TOKENIZER_MODEL}", file=sys.stderr)
    except Exception as e:
        # Chunking falls back to a character estimate, so this is not fatal
        print(f"Warning: could not cache tokenizer {TOKENIZER_MODEL}: {e}", file=sys.stderr)


def download_models():
    """
    Downloads and caches the sentence transformer and cross-encoder models.
    This script is intended to be run during the Docker build process
    to pre-warm the cache and bake the models into the image.
    """
    print("Downloading and caching embedding model...", file=sys.stderr)
    try:
        model = SentenceTransformer(EMBEDDING_MODEL)
        get_dim = getattr(model, 'get_embedding_dimension', None) or model.get_sentence_embedding_dimension
        actual_dim = int(get_dim())
        print(f"Successfully cached {EMBEDDING_MODEL} ({actual_dim}-dim)", file=sys.stderr)
        if actual_dim != EMBEDDING_DIMENSION:
            print(
                f"WARNING: EMBEDDING_DIMENSION={EMBEDDING_DIMENSION} does not match "
                f"{EMBEDDING_MODEL} ({actual_dim}-dim). Set EMBEDDING_DIMENSION={actual_dim} "
                "(the model's real size is used at runtime, but the mismatch forces a re-scan).",
                file=sys.stderr
            )
    except Exception as e:
        print(f"Failed to download embedding model: {e}", file=sys.stderr)
        sys.exit(1)

    if EMBEDDING_QUERY_PROMPT:
        print("Using custom EMBEDDING_QUERY_PROMPT for search queries", file=sys.stderr)

    download_tokenizer()

    if USE_RERANKER:
        print("Downloading and caching re-ranker model...", file=sys.stderr)
        try:
            CrossEncoder(RERANKER_MODEL)
            print(f"Successfully cached {RERANKER_MODEL}", file=sys.stderr)
        except Exception as e:
            print(f"Failed to download re-ranker model: {e}", file=sys.stderr)
            # We don't exit here, as re-ranking is optional
            pass

if __name__ == "__main__":
    download_models()
