"""
Shared embedding model access.

Both the vector store and the semantic chunker need sentence embeddings.
Loading the model twice would double memory usage, so this module exposes a
single lazily-initialised SentenceTransformer instance for the whole process.

Two entry points are exposed:

* :func:`encode_passages` — embeds document chunks (no instruction prefix).
* :func:`encode_queries` — embeds search queries, applying the model's query
  instruction prompt when it ships one (Qwen3-Embedding recommends an
  instruction for queries; it measurably improves retrieval).

Both normalise the output vectors, which is what the ChromaDB collection is
created with (``space="cosine"``).
"""

import sys
from typing import List, Optional, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from .config import EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE, EMBEDDING_QUERY_PROMPT

_model: Optional[SentenceTransformer] = None
_query_prompt: Optional[str] = None
_prompt_resolved = False


def get_embedding_model() -> SentenceTransformer:
    """Return the process-wide embedding model, loading it on first use."""
    global _model
    if _model is None:
        print(f"Loading embedding model: {EMBEDDING_MODEL}", file=sys.stderr)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_query_prompt() -> Optional[str]:
    """Resolve the query instruction prefix.

    Priority: explicit ``EMBEDDING_QUERY_PROMPT`` > the model's built-in
    ``query`` prompt (Qwen3-Embedding ships one) > no prompt at all.
    """
    global _query_prompt, _prompt_resolved
    if _prompt_resolved:
        return _query_prompt

    _prompt_resolved = True
    if EMBEDDING_QUERY_PROMPT:
        _query_prompt = EMBEDDING_QUERY_PROMPT
    else:
        try:
            prompts = get_embedding_model().prompts or {}
        except Exception:
            prompts = {}
        _query_prompt = prompts.get("query") or None

    if _query_prompt:
        print(f"Using query instruction prompt for {EMBEDDING_MODEL}", file=sys.stderr)
    return _query_prompt


def _encode(texts: Sequence[str], prompt: Optional[str] = None,
            show_progress_bar: bool = False) -> np.ndarray:
    model = get_embedding_model()
    kwargs = {
        'batch_size': EMBEDDING_BATCH_SIZE,
        'normalize_embeddings': True,
        'convert_to_numpy': True,
        'show_progress_bar': show_progress_bar,
    }
    if prompt:
        kwargs['prompt'] = prompt
    return np.asarray(model.encode(list(texts), **kwargs))


def encode_passages(texts: Sequence[str], show_progress_bar: bool = False) -> np.ndarray:
    """Embed document chunks (no instruction prefix)."""
    return _encode(texts, show_progress_bar=show_progress_bar)


def encode_queries(queries: Sequence[str], show_progress_bar: bool = False) -> np.ndarray:
    """Embed search queries, with the model's query instruction if available."""
    return _encode(queries, prompt=_get_query_prompt(), show_progress_bar=show_progress_bar)


def encode_one_query(query: str) -> List[float]:
    """Embed a single query and return it as a plain list of floats."""
    return encode_queries([query])[0].tolist()


def get_embedding_dimension() -> Optional[int]:
    """Return the embedding size reported by the model, or None if unknown.

    Used to validate ``EMBEDDING_DIMENSION``: a stale value there would make the
    collection metadata lie about its own vectors.
    """
    model = get_embedding_model()
    getter = getattr(model, 'get_embedding_dimension', None) \
        or getattr(model, 'get_sentence_embedding_dimension', None)
    if getter is None:
        return None
    try:
        return int(getter())
    except Exception as e:
        print(f"Could not determine embedding dimension: {e}", file=sys.stderr)
        return None
