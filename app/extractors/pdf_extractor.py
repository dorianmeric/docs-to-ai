"""
PDF Extractor - Extract text from PDF documents, with OCR for scanned pages.

Text comes from the PDF's text layer. A scanned page has no text layer: it
holds an image of the page instead, so the text layer is empty. Those pages are
rasterised and read by Tesseract (see :mod:`app.ocr`), so a scanned PDF becomes
searchable without any manual conversion.
"""

import time

import pymupdf
from pathlib import Path
from typing import Any, Dict, List

from ..config import OCR_ENABLED, OCR_MAX_PAGES, OCR_MIN_TEXT_CHARS
from ..errors import document_error
from ..log_config import log_detail
from ..logging_utils import log_info, log_warn
from ..ocr import ocr_available, ocr_page_text


def _page_may_hold_text(page) -> bool:
    """True when the page has something OCR could read (an image or a drawing).

    A blank page has neither, so OCR would only cost time. A page whose text
    was rendered as vector paths shows up as drawings, which keeps those
    readable.
    """
    try:
        return bool(page.get_images()) or bool(page.get_drawings())
    except Exception:
        return True  # Not sure: let OCR try rather than drop the page.


def _log_outcome(path: Path, total_pages: int, ocr_pages: List[Dict[str, Any]],
                 still_empty: List[int], ocr_found_nothing: List[int], over_budget: int,
                 blank: int) -> None:
    """Say what OCR did with this document, and what the user could change."""
    if ocr_pages:
        log_info(
            f"OCR read {len(ocr_pages)} of {total_pages} scanned page(s) in {path.name}",
            component="OCR",
        )
    if ocr_pages or still_empty:
        log_detail(
            "ocr_document",
            file=path.name,
            path=str(path),
            total_pages=total_pages,
            ocr_pages=ocr_pages,
            pages_still_without_text=still_empty,
            pages_ocr_found_nothing=ocr_found_nothing,
            pages_over_budget=over_budget,
            blank_pages=blank,
        )

    if over_budget:
        log_warn(
            f"{path.name}: OCR stopped after OCR_MAX_PAGES={OCR_MAX_PAGES} page(s), so "
            f"{over_budget} more scanned page(s) stay empty. Raise OCR_MAX_PAGES to read them.",
            component="OCR",
        )

    if not still_empty:
        return

    pages = f"{len(still_empty)} page(s)"
    if not OCR_ENABLED:
        log_warn(
            f"{path.name} has {pages} with no text layer (a scan), and OCR is off "
            "(OCR_ENABLED=False). Those pages stay empty. Set OCR_ENABLED=True to read them.",
            component="OCR",
        )
    elif OCR_MAX_PAGES <= 0:
        log_warn(
            f"{path.name} has {pages} with no text layer (a scan), but OCR_MAX_PAGES=0 turns OCR "
            "off. Set OCR_MAX_PAGES to a positive number, for example 9999.",
            component="OCR",
        )
    elif not ocr_available():
        log_warn(
            f"{path.name} has {pages} with no text layer (a scan), and OCR could not run, so they "
            "stay empty. The OCR warning above says what is missing.",
            component="OCR",
        )
    elif ocr_found_nothing:
        log_warn(
            f"{path.name}: OCR found no text in {len(ocr_found_nothing)} page(s). The scan may be "
            "too faint, or the page may be blank. A higher OCR_DPI can help.",
            component="OCR",
        )


def extract_text_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """Extract text from a PDF page by page, running OCR on scanned pages.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        One dict per page with 'page', 'text', 'total_pages', and 'ocr'. 'ocr' is
        True when the text came from OCR rather than the PDF's text layer.
    """
    pages_data = []

    try:
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        budget = max(0, OCR_MAX_PAGES) if OCR_ENABLED else 0
        # Asking once per document keeps the availability check out of the page loop
        ocr_ready = ocr_available() if budget else False

        ocr_pages: List[Dict[str, Any]] = []
        still_empty: List[int] = []
        ocr_found_nothing: List[int] = []
        blank_pages = 0
        over_budget = 0

        for page_num in range(total_pages):
            page = doc[page_num]
            text = page.get_text()
            used_ocr = False

            if len(text.strip()) < OCR_MIN_TEXT_CHARS:
                if not _page_may_hold_text(page):
                    blank_pages += 1
                elif budget and ocr_ready:
                    if len(ocr_pages) < budget:
                        started = time.perf_counter()
                        ocr_text = ocr_page_text(page)
                        if ocr_text.strip():
                            text = ocr_text
                            used_ocr = True
                            ocr_pages.append({
                                'page': page_num + 1,
                                'chars': len(ocr_text),
                                'ms': round((time.perf_counter() - started) * 1000, 2),
                            })
                            # A long scan shows progress instead of looking stuck
                            if len(ocr_pages) % 10 == 0:
                                log_info(
                                    f"OCR progress in {pdf_path.name}: {len(ocr_pages)} page(s) read",
                                    component="OCR",
                                )
                        else:
                            ocr_found_nothing.append(page_num + 1)
                    else:
                        over_budget += 1

                if not used_ocr:
                    still_empty.append(page_num + 1)

            pages_data.append({
                'page': page_num + 1,
                'text': text,
                'total_pages': total_pages,
                'ocr': used_ocr,
            })

        _log_outcome(pdf_path, total_pages, ocr_pages, still_empty, ocr_found_nothing,
                     over_budget, blank_pages)

        doc.close()

    except Exception as e:
        raise document_error(pdf_path, e, "PDF") from e

    return pages_data
