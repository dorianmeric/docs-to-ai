"""
Shared embedding model access.

Both the vector store and the semantic chunker need sentence embeddings.
Loading the model twice would double memory usage, so this module exposes a
single lazily-initialised SentenceTransformer instance for the whole process.
"""

from typing import Optional

from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    """Return the process-wide embedding model, loading it on first use."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model
