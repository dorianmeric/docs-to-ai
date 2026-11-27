"""
OCR for scanned PDF pages, using Marker (datalab-to/marker).

A scanned PDF stores page images and no text layer, so ``page.get_text()``
returns an empty string and those pages would be indexed with nothing. The PDF
extractor hands exactly those pages to :func:`ocr_read_pages`, which runs
Marker on the document and returns the recognised text per page.

Marker is an optional dependency because it brings its own PyTorch build and
models (about 110 MB for the default ``fast`` mode, several GB for the GPU
modes)::

    uv sync --extra marker

Without it the server still runs; scanned pages stay empty and one warning
explains how to install it.

Marker modes (``MARKER_MODE``):

* ``fast`` (default) - in-process ONNX layout and OCR on CPU or GPU, no extra
  server. Reading a mixed document runs at roughly 7 pages/s.
* ``balanced`` - Marker decides per page: text layer where it is clean, Surya
  VLM OCR for scans, tables, and maths. Needs a GPU and ``vllm`` or
  ``llama.cpp`` installed.
* ``vllm`` - full-page Surya VLM OCR on every page. Highest accuracy on
  degraded scans, slowest. Needs a GPU and ``vllm``.
* ``no_ocr`` / ``auto`` - pass through to Marker unchanged.
"""

import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import MARKER_DEVICE, MARKER_MODE, MARKER_MODEL_CACHE
from .logging_utils import log_info, log_warn

# Marker is imported lazily: importing it costs seconds and pulls in torch, so
# a server without the extra installed must never pay that.
_ready: Optional[Tuple[bool, str]] = None
_reported = False
_models: Optional[Dict[str, Any]] = None
_engine_lock = threading.Lock()

MODES = ("fast", "balanced", "vllm", "no_ocr", "auto")


def _prepare_environment() -> None:
    """Point Marker at the right device and model cache before it is imported."""
    if MARKER_MODEL_CACHE:
        os.environ.setdefault("HF_HOME", MARKER_MODEL_CACHE)
    # Marker reads TORCH_DEVICE at import time. Without an override it follows
    # the same GPU switch as the embedding model, so one setting covers both.
    if MARKER_DEVICE:
        os.environ["TORCH_DEVICE"] = MARKER_DEVICE
    elif "TORCH_DEVICE" not in os.environ:
        try:
            from .device import resolve_device
            device = resolve_device()
        except Exception:
            device = "cpu"
        os.environ["TORCH_DEVICE"] = "cuda" if device.startswith("cuda") else device


def _check() -> Tuple[bool, str]:
    """Import Marker once and report what it will do."""
    _prepare_environment()
    try:
        import marker
        from marker.models import create_model_dict  # noqa: F401
    except ImportError as exc:
        return False, (
            f"Marker is not installed ({exc}). Run 'uv sync --extra marker' "
            "(or 'pip install marker-pdf'), then restart the server."
        )
    except Exception as exc:  # torch or a marker dependency is broken
        return False, f"Marker could not be imported ({type(exc).__name__}: {exc})."

    try:
        from importlib.metadata import version as _dist_version
        version = _dist_version("marker-pdf")
    except Exception:
        version = getattr(marker, "__version__", "unknown")

    mode = MARKER_MODE if MARKER_MODE in MODES else "fast"
    device = os.environ.get("TORCH_DEVICE", "auto")

    problem = _vlm_backend_problem(mode)
    if problem:
        return False, problem

    return True, f"Marker {version}, mode {mode}, device {device}"


def _vlm_backend_problem(mode: str) -> Optional[str]:
    """Explain a missing VLM backend for the modes that need one.

    'fast' runs in-process ONNX, so it needs nothing extra. 'balanced' and
    'vllm' hand scanned pages to a Surya VLM, which Marker starts through vllm
    (NVIDIA) or llama.cpp's llama-server (CPU/MPS).
    """
    if mode not in ("balanced", "vllm"):
        return None

    try:
        import vllm  # noqa: F401
        return None
    except Exception:
        pass

    from shutil import which
    if which("llama-server"):
        return None

    return (
        f"MARKER_MODE={mode} needs a VLM backend, and neither vllm nor llama.cpp was found. "
        "Install vllm on an NVIDIA machine ('pip install vllm'), or install llama.cpp so that "
        "'llama-server' is on PATH. Use MARKER_MODE=fast to run without a VLM."
    )


def ocr_status() -> Tuple[bool, str]:
    """Return ``(can OCR run, one-line reason)``; checked once per process.

    The result is logged once. Later calls are silent, so scanning many
    documents does not repeat the same message.
    """
    global _ready, _reported
    if _ready is None:
        _ready = _check()
    available, detail = _ready

    if not _reported and MARKER_MODE != "no_ocr":
        _reported = True
        if available:
            log_info(f"OCR is available: {detail}", component="OCR")
        else:
            log_warn(
                f"OCR is enabled but unavailable: {detail} Scanned PDF pages stay empty until this is fixed.",
                component="OCR",
            )
    return available, detail


def ocr_available() -> bool:
    """True when Marker can read a scanned page."""
    return ocr_status()[0]


def _load_models() -> Dict[str, Any]:
    """Create Marker's model dict once and reuse it for every document."""
    global _models
    if _models is not None:
        return _models

    _prepare_environment()
    from marker.models import create_model_dict

    mode = MARKER_MODE if MARKER_MODE in MODES else "fast"
    # 'fast'/'no_ocr' run in-process (ONNX) and must not spawn a VLM server;
    # 'balanced'/'vllm' talk to vllm or llama.cpp over the inference manager.
    local_only = mode in ("fast", "no_ocr")
    started = time.perf_counter()
    _models = create_model_dict(load_indra=local_only, no_server=local_only)
    log_info(
        f"Marker models loaded in {time.perf_counter() - started:.1f}s",
        component="OCR",
    )
    return _models


def _html_to_text(html: str) -> str:
    """Marker block HTML to plain text, keeping table rows readable."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")

    for table in soup.find_all("table"):
        rows = []
        for row in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(" | ".join(cells))
        table.replace_with("\n" + "\n".join(rows) + "\n" if rows else "")

    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block_tag in soup.find_all(
        ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "div", "tr"]
    ):
        block_tag.append("\n")

    lines = [line.strip() for line in soup.get_text().splitlines()]
    compact: List[str] = []
    for line in lines:
        if line or (compact and compact[-1]):
            compact.append(line)
    return "\n".join(compact).strip()


def _page_index(page_block_id: str, position: int) -> int:
    """Marker page id '/page/7/Page/0' to the 0-based page index."""
    parts = str(page_block_id).split("/")
    if len(parts) > 2 and parts[2].isdigit():
        return int(parts[2])
    return position


def ocr_read_pages(pdf_path: Path, page_indexes: List[int]) -> Dict[int, str]:
    """Read the given 0-based pages of a PDF with Marker.

    Args:
        pdf_path: Path to the PDF.
        page_indexes: 0-based page numbers to read, in document order.

    Returns:
        ``{page_index: text}`` for the pages Marker returned. An empty dict
        means OCR could not run or returned nothing; the reason is logged.
    """
    if not page_indexes or not ocr_available():
        return {}

    started = time.perf_counter()
    try:
        with _engine_lock:  # Marker's models are not safe for parallel calls
            from marker.converters.pdf import PdfConverter
            from marker.output import json_to_html

            converter = PdfConverter(
                artifact_dict=_load_models(),
                renderer="marker.renderers.json.JSONRenderer",
                config={
                    "mode": MARKER_MODE if MARKER_MODE in MODES else "fast",
                    "page_range": list(page_indexes),
                    # These pages were chosen because they have no text layer, so
                    # OCR always runs instead of trusting an empty text layer
                    "force_ocr": True,
                    "disable_tqdm": True,
                },
            )
            rendered = converter(str(pdf_path))

        texts: Dict[int, str] = {}
        for position, page_block in enumerate(getattr(rendered, "children", None) or []):
            index = _page_index(getattr(page_block, "id", ""), position)
            parts = [_html_to_text(json_to_html(block)) for block in (page_block.children or [])]
            text = "\n\n".join(part for part in parts if part)
            texts[index] = text
    except Exception as exc:
        log_warn(
            f"Marker could not read {pdf_path.name} ({type(exc).__name__}: {exc}). "
            "The scanned pages stay empty.",
            component="OCR",
        )
        return {}

    elapsed = time.perf_counter() - started
    log_info(
        f"Marker read {len(texts)} page(s) of {pdf_path.name} in {elapsed:.1f}s "
        f"({elapsed / max(1, len(texts)):.1f}s per page)",
        component="OCR",
    )
    return texts
