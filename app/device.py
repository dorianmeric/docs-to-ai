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

from pathlib import Path
from typing import Optional

import torch

from .logging_utils import log_error, log_info, log_success, log_warn
from .config import GPU_DEVICE_INDEX, USE_GPU_ACCELERATION_IF_AVAILABLE

_resolved: Optional[str] = None


def _in_container() -> bool:
    """True when the process runs inside a container."""
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _nvidia_device_nodes_present() -> bool:
    """True when the container was given NVIDIA device nodes."""
    return any(
        Path(node).exists()
        for node in ("/dev/nvidiactl", "/dev/nvidia0", "/dev/nvidia-uvm")
    )


def _log_gpu_unavailable_hint() -> None:
    """Explain why no GPU was found, and exactly what to change."""
    if _in_container():
        if _nvidia_device_nodes_present():
            _log(
                "PyTorch cannot use the GPU even though the container has NVIDIA devices: this image "
                "carries a CPU-only PyTorch build.\n"
                "Rebuild the image so the CUDA-enabled PyTorch wheel is installed: "
                "docker compose build --no-cache",
                level="warn",
            )
            return
        _log(
            "No GPU is visible inside this container, so embedding and re-ranking run on the CPU.\n"
            "If the host has an NVIDIA GPU, pass it to the container with:\n"
            "  docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d\n"
            "To keep plain 'docker compose up -d', put COMPOSE_FILE in .env. Use ';' as separator on "
            "Windows and ':' on Linux/macOS:\n"
            "  COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml\n"
            "A plain 'docker run' needs '--gpus all'. Linux hosts also need the NVIDIA Container "
            "Toolkit. Docker Desktop needs the WSL2 backend and the NVIDIA driver on the host.\n"
            "Verify with 'docker compose exec docs-to-ai nvidia-smi', or for a plain 'docker run' add "
            "'--entrypoint nvidia-smi' (the image entrypoint is the MCP server itself).", 
            level="warn",
        )
        return
    _log(
        "No GPU detected, so embedding and re-ranking run on the CPU.\n"
        "To use an NVIDIA GPU, install a CUDA-enabled PyTorch build: "
        "uv pip install --index-url https://download.pytorch.org/whl/cu128 torch"
    )


def _log(message: str, level: str = "info") -> None:
    if level == "success":
        log_success(message, component="Device")
    elif level == "warn":
        log_warn(message, component="Device")
    elif level == "error":
        log_error(message, component="Device")
    else:
        log_info(message, component="Device")


def _cuda_device_index() -> Optional[int]:
    """Return the CUDA index to use, or None when CUDA is unavailable."""
    try:
        count = torch.cuda.device_count()
    except Exception as e:  # pragma: no cover - defensive
        _log(f"Could not query CUDA devices: {e}", level="warn")
        return None

    if count <= 0:
        return None
    if 0 <= GPU_DEVICE_INDEX < count:
        return GPU_DEVICE_INDEX

    _log(
        f"GPU_DEVICE_INDEX={GPU_DEVICE_INDEX} is out of range "
        f"({count} CUDA device(s) visible); using GPU 0",
        level="warn",
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
        _log(f"Device '{device}' is not usable ({e}); falling back to CPU", level="warn")
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
        _log(f"Compute device: {describe_device(candidate)}", level="success")
        return _resolved

    if candidate is None and _mps_available() and _probe("mps"):
        _resolved = "mps"
        _log(f"Compute device: {describe_device('mps')}", level="success")
        return _resolved

    _resolved = "cpu"
    if candidate is not None or _mps_available():
        _log("Compute device: cpu (no usable GPU; continuing on CPU)", level="warn")
    else:
        _log_gpu_unavailable_hint()
    return _resolved


def reset_device_cache() -> None:
    """Forget the cached device (used by tests and when settings change)."""
    global _resolved
    _resolved = None
