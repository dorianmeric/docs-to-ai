"""
Compute-device selection for the models that can use an accelerator.

Only the neural models profit from a GPU:

* the sentence-transformer that produces dense embeddings — this also covers the
  per-sentence passes of semantic chunking, so indexing gets faster too — and
* the cross-encoder re-ranker.

BM25 scoring (:mod:`app.bm25_index`) is pure Python and ChromaDB's local HNSW
index is CPU-only, so neither is affected by this setting.

Resolution order:

1. ``USE_GPU_ACCELERATION_IF_AVAILABLE=False`` -> CPU.
2. NVIDIA CUDA -> ``cuda:<GPU_DEVICE_INDEX>`` (GPU 0 when the index is out of
   range, so a stale value never prevents startup).
3. Apple Silicon MPS -> ``mps``.
4. Otherwise -> ``cpu``.

The chosen device is probed with a tiny allocation, so a CUDA build that cannot
actually run on the installed driver/GPU falls back to CPU instead of failing
later inside an encode call.
"""

import sys
from typing import Optional

import torch

from .config import GPU_DEVICE_INDEX, USE_GPU_ACCELERATION_IF_AVAILABLE

_resolved: Optional[str] = None


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _cuda_device_index() -> Optional[int]:
    """Return the CUDA index to use, or None when CUDA is unavailable."""
    try:
        count = torch.cuda.device_count()
    except Exception as e:  # pragma: no cover - defensive
        _log(f"Could not query CUDA devices: {e}")
        return None

    if count <= 0:
        return None
    if 0 <= GPU_DEVICE_INDEX < count:
        return GPU_DEVICE_INDEX

    _log(
        f"Warning: GPU_DEVICE_INDEX={GPU_DEVICE_INDEX} is out of range "
        f"({count} CUDA device(s) visible); using GPU 0"
    )
    return 0


def _mps_available() -> bool:
    backend = getattr(torch.backends, "mps", None)
    try:
        return bool(backend and backend.is_available())
    except Exception:  # pragma: no cover - defensive
        return False


def _probe(device: str) -> bool:
    """Check that the device can actually run an operation."""
    try:
        torch.zeros(1, device=device)
        return True
    except Exception as e:
        _log(f"Warning: device '{device}' is not usable ({e}); falling back to CPU")
        return False


def describe_device(device: str) -> str:
    """Human-readable description of a torch device string."""
    if device.startswith("cuda"):
        index = int(device.split(":", 1)[1]) if ":" in device else 0
        try:
            name = torch.cuda.get_device_name(index)
            total_gb = torch.cuda.get_device_properties(index).total_memory / (1024 ** 3)
            return f"{device} ({name}, {total_gb:.0f} GB VRAM)"
        except Exception:  # pragma: no cover - defensive
            return device
    if device == "mps":
        return "mps (Apple GPU)"
    return "cpu"


def resolve_device() -> str:
    """Return the torch device string to use for all neural models (cached)."""
    global _resolved
    if _resolved is not None:
        return _resolved

    if not USE_GPU_ACCELERATION_IF_AVAILABLE:
        _resolved = "cpu"
        _log("Compute device: cpu (GPU acceleration disabled by USE_GPU_ACCELERATION_IF_AVAILABLE=False)")
        return _resolved

    cuda_index = _cuda_device_index()
    candidate = f"cuda:{cuda_index}" if cuda_index is not None else None
    if candidate and _probe(candidate):
        _resolved = candidate
        _log(f"Compute device: {describe_device(candidate)}")
        return _resolved

    if candidate is None and _mps_available() and _probe("mps"):
        _resolved = "mps"
        _log(f"Compute device: {describe_device('mps')}")
        return _resolved

    _resolved = "cpu"
    if candidate is not None or _mps_available():
        _log("Compute device: cpu (no usable GPU; continuing on CPU)")
    else:
        _log("Compute device: cpu (no GPU detected)")
    return _resolved


def reset_device_cache() -> None:
    """Forget the cached device (used by tests and when settings change)."""
    global _resolved
    _resolved = None
