# app/download_models.py
from sentence_transformers import SentenceTransformer, CrossEncoder
from app.config import EMBEDDING_MODEL, USE_RERANKER, RERANKER_MODEL
import sys

def download_models():
    """
    Downloads and caches the sentence transformer and cross-encoder models.
    This script is intended to be run during the Docker build process
    to pre-warm the cache and bake the models into the image.
    """
    print("Downloading and caching embedding model...", file=sys.stderr)
    try:
        SentenceTransformer(EMBEDDING_MODEL)
        print(f"Successfully cached {EMBEDDING_MODEL}", file=sys.stderr)
    except Exception as e:
        print(f"Failed to download embedding model: {e}", file=sys.stderr)
        sys.exit(1)

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
