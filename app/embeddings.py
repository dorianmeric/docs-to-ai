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

from typing import List, Optional, Sequence

import numpy as np
from sentence_transformers import SentenceTransformer

from .logging_utils import log_info, log_warn
from .config import EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE, EMBEDDING_QUERY_PROMPT
from .device import describe_device, resolve_device
from .errors import DocsToAIError, explain

_model: Optional[SentenceTransformer] = None
_query_prompt: Optional[str] = None
_prompt_resolved = False


def get_embedding_model() -> SentenceTransformer:
    """Return the process-wide embedding model, loading it on first use."""
    global _model
    if _model is None:
        device = resolve_device()
        log_info(f"Loading embedding model: {EMBEDDING_MODEL} on {describe_device(device)}", component="Embeddings")
        try:
            _model = SentenceTransformer(EMBEDDING_MODEL, device=device)
        except Exception as exc:
            raise DocsToAIError(
                problem=f"The embedding model '{EMBEDDING_MODEL}' could not be loaded.",
                cause="The model name is wrong, the model files are not downloaded yet, or the machine cannot "
                      "run the model on the selected device.",
                fix="Check EMBEDDING_MODEL (default: Qwen/Qwen3-Embedding-0.6B). Run "
                    "'python -m app.download_models' once with network access. If a GPU is involved, run "
                    "'python -c \"import torch; print(torch.cuda.is_available())\"' to check the driver.",
                details=f"{type(exc).__name__}: {exc}",
            ) from exc
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
        log_info(f"Using query instruction prompt for {EMBEDDING_MODEL}", component="Embeddings")
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
    try:
        return np.asarray(model.encode(list(texts), **kwargs))
    except Exception as exc:
        # Out-of-memory is the usual failure here: say so instead of dumping a traceback
        raise DocsToAIError(
            problem=f"The embedding model failed while encoding {len(texts)} text(s).",
            cause="The batch is larger than the available memory, or the GPU rejected the computation.",
            fix="Lower EMBEDDING_BATCH_SIZE (try 8 or 16) and retry. On a multi-GPU machine set "
                "GPU_DEVICE_INDEX to a card with more VRAM. Set USE_GPU_ACCELERATION_IF_AVAILABLE=False to "
                "run this step on the CPU.",
            details=explain(exc).splitlines()[-1],
        ) from exc


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
        log_warn(f"Could not determine embedding dimension: {e}", component="Embeddings")
        return None
