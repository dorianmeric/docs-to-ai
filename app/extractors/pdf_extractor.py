"""
PDF Extractor - Extract text from PDF documents, with OCR for scanned pages.

Text comes from the PDF's text layer. A scanned page has no text layer: it holds
an image of the page instead, so the text layer is empty. Those pages are handed
to Marker (see :mod:`app.ocr`), so a scanned PDF becomes searchable without any
manual conversion.
"""

import time

import pymupdf
from pathlib import Path
from typing import Any, Dict, List, Set

from ..config import OCR_ENABLED, OCR_MAX_PAGES, OCR_MIN_TEXT_CHARS
from ..errors import document_error
from ..log_config import log_detail
from ..logging_utils import log_info, log_warn
from ..ocr import ocr_available, ocr_read_pages


def _page_may_hold_text(page) -> bool:
    """True when the page has something OCR could read (an image or a drawing).

    A blank page has neither, so OCR would only cost time. A page whose text was
    rendered as vector paths shows up as drawings, which keeps those readable.
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
            engine="marker",
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
            f"{path.name}: Marker found no text in {len(ocr_found_nothing)} page(s). The scan may "
            "be blank, or MARKER_MODE=fast may be too weak for it; try MARKER_MODE=balanced.",
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
    pages_data: List[Dict[str, Any]] = []

    try:
        with pymupdf.open(pdf_path) as doc:
            total_pages = len(doc)
            page_texts: List[str] = []
            needs_ocr: List[int] = []  # 0-based indexes of pages without a text layer
            blank_pages = 0

            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text()
                page_texts.append(text)
                if len(text.strip()) < OCR_MIN_TEXT_CHARS:
                    if _page_may_hold_text(page):
                        needs_ocr.append(page_num)
                    else:
                        blank_pages += 1
        # The file is closed before Marker opens it: on Windows a PDF that is
        # still open here cannot be read a second time.

        budget = max(0, OCR_MAX_PAGES) if OCR_ENABLED else 0
        requested = needs_ocr[:budget] if budget else []
        # Only a real ceiling leaves pages behind; OCR off has its own message
        over_budget = len(needs_ocr) - len(requested) if budget else 0

        ocr_text: Dict[int, str] = {}
        if requested and ocr_available():
            ocr_text = ocr_read_pages(pdf_path, requested)

        requested_set: Set[int] = set(requested)
        needs_ocr_set: Set[int] = set(needs_ocr)
        ocr_pages: List[Dict[str, Any]] = []
        ocr_found_nothing: List[int] = []
        still_empty: List[int] = []

        for page_num in range(total_pages):
            text = page_texts[page_num]
            used_ocr = False

            if page_num in requested_set:
                recognised = (ocr_text.get(page_num) or "").strip()
                if recognised:
                    text = recognised
                    used_ocr = True
                    ocr_pages.append({
                        'page': page_num + 1,
                        'chars': len(recognised),
                        'engine': 'marker',
                    })
                else:
                    ocr_found_nothing.append(page_num + 1)
                    still_empty.append(page_num + 1)
            elif page_num in needs_ocr_set:
                # OCR never saw this page: disabled, unavailable, or over budget
                still_empty.append(page_num + 1)

            pages_data.append({
                'page': page_num + 1,
                'text': text,
                'total_pages': total_pages,
                'ocr': used_ocr,
            })

        _log_outcome(pdf_path, total_pages, ocr_pages, still_empty,
                     ocr_found_nothing, over_budget, blank_pages)

    except Exception as e:
        raise document_error(pdf_path, e, "PDF") from e

    return pages_data
