"""
OCR for scanned PDF pages.

A scanned PDF stores page images and no text layer, so ``page.get_text()``
returns an empty string and the page would be indexed with no text. The PDF
extractor calls :func:`ocr_page_text` for such a page: the page is rasterised
with PyMuPDF and read by Tesseract through ``pytesseract``.

The engine is optional. A missing Python package, a missing Tesseract program,
or a missing language pack makes :func:`ocr_status` report the reason, and the
PDF extractor then keeps the empty text and logs one warning. Nothing else
breaks when OCR cannot run.

Install:
    python: ``uv sync`` (pytesseract and pillow are project dependencies)
    program: Debian/Ubuntu ``apt-get install tesseract-ocr tesseract-ocr-eng``,
             Windows ``winget install UB-Mannheim.TesseractOCR``,
             macOS ``brew install tesseract``
    extra languages: install the matching pack, e.g. ``tesseract-ocr-deu``, and
             set ``OCR_LANG=deu`` (combine with ``+``: ``OCR_LANG=deu+eng``)
"""

import io
from typing import Optional, Tuple

from .config import OCR_DPI, OCR_LANG
from .logging_utils import log_info, log_warn

# Tesseract's own render window. Below 150 dpi small print turns to mush, and
# above 600 dpi the extra pixels cost time without adding accuracy.
MIN_DPI = 150
MAX_DPI = 600

_status: Optional[Tuple[bool, str]] = None
_reported = False


def _wanted_languages() -> list:
    return [part.strip() for part in str(OCR_LANG).split('+') if part.strip()]


def _check() -> Tuple[bool, str]:
    """Test the Python packages, the Tesseract program, and the language packs."""
    try:
        import pytesseract
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        return False, f"The Python packages are missing ({exc}). Run 'uv sync'."

    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:  # pytesseract raises when the program is absent
        return False, (
            f"The Tesseract program was not found ({type(exc).__name__}). Install Tesseract and its "
            "packages: Debian 'apt-get install tesseract-ocr tesseract-ocr-eng', "
            "Windows 'winget install UB-Mannheim.TesseractOCR', macOS 'brew install tesseract'."
        )

    wanted = _wanted_languages()
    try:
        installed = sorted(pytesseract.get_languages(config=''))
    except Exception:
        installed = []
    missing = [lang for lang in wanted if installed and lang not in installed]
    if missing:
        return False, (
            f"Tesseract {version} has no language pack for {', '.join(missing)} "
            f"(OCR_LANG={OCR_LANG}). Installed: {', '.join(installed)}. Install the pack, for example "
            f"'apt-get install tesseract-ocr-{missing[0]}', or set OCR_LANG to an installed language."
        )

    return True, f"Tesseract {version}, OCR_LANG={OCR_LANG}"


def ocr_status() -> Tuple[bool, str]:
    """Return ``(can OCR run, one-line reason)``; checked once per process.

    The result is logged once. Later calls are silent, so a scan of many
    scanned documents does not repeat the same warning.
    """
    global _status, _reported
    if _status is None:
        _status = _check()
    available, detail = _status

    if not _reported:
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
    """True when OCR can run on this machine."""
    return ocr_status()[0]


def ocr_dpi() -> int:
    """OCR_DPI held inside the range Tesseract handles well."""
    return max(MIN_DPI, min(MAX_DPI, int(OCR_DPI)))


def ocr_page_text(page) -> str:
    """Run OCR on one PyMuPDF page and return the recognised text.

    Args:
        page: A ``pymupdf``/``fitz`` page object.

    Returns:
        The recognised text, or an empty string when OCR is unavailable, the
        page cannot be rendered, or Tesseract finds no text.
    """
    if not ocr_available():
        return ""

    page_number = getattr(page, 'number', 0) + 1
    try:
        import pytesseract
        from PIL import Image

        pixmap = page.get_pixmap(dpi=ocr_dpi())
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=OCR_LANG) or ""
    except Exception as exc:
        # A page that fails must not stop the document; the text stays empty.
        log_warn(f"OCR failed on page {page_number} ({type(exc).__name__}: {exc})", component="OCR")
        return ""
