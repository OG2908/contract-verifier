"""Extract structured data from Hebrew reservation agreement PDFs."""
from __future__ import annotations

import re
import logging

from pypdf import PdfReader

from .models import (
    ExtractionWarning,
    ReservationData,
    ReservationExtractionResult,
    parse_hebrew_amount,
)

logger = logging.getLogger(__name__)

# Regex patterns for reservation fields
PATTERNS = {
    "apartment_number": r'דירה\s*(?:מספר\s*)?([A-Za-z]?\d+[A-Za-z\u0590-\u05FF]?)',
    "floor": r'בקומה/מפלס\s+([^\s,]+)',
    "area_sqm": r'שטח\s+של\s+כ?-?\s*([\d,.]+)\s*\n?\s*מטר',
    "price_base": r'במחיר\s+רכישה\s+של\s+([\d,]+)\s*אירו',
    "price_total": r'ובמחיר\s+כולל\s+של\s+([\d,]+)\s*\n?\s*אירו',
    "reg_fee": r'דמי\s+רצינות\s+בסך\s+([\d,]+)\s*\n?\s*אירו',
    "project_name": r'בפרויקט\s+"?([^",(]+)',
}

# Default values used as placeholders when extraction fails
_DEFAULTS = {
    "client_name": "",
    "apartment_number": "",
    "floor": "",
    "area_gross_sqm": 0.0,
    "price_without_costs": 0.0,
    "price_with_costs": 0.0,
    "registration_fee": 0.0,
    "project_name": "",
}


def extract(pdf_path: str) -> ReservationData:
    """Extract reservation data from a Hebrew PDF.

    Raises ExtractionError on failure. Use extract_safe() for fault-tolerant
    extraction that returns partial results with warnings.
    """
    result = extract_safe(pdf_path)
    if result.has_warnings:
        failed = ", ".join(w.field_name for w in result.warnings)
        reasons = "; ".join(f"{w.field_name}: {w.reason}" for w in result.warnings)
        raise ExtractionError(
            f"Failed to extract field(s): {failed}. Details: {reasons}"
        )
    return result.data


def extract_safe(pdf_path: str) -> ReservationExtractionResult:
    """Extract reservation data, returning partial results with warnings for failures."""
    text = get_pdf_text(pdf_path)
    logger.debug("Raw PDF text (first 500 chars): %s", text[:500])

    warnings: list[ExtractionWarning] = []
    values: dict = {}

    # Extract property details from paragraph 2
    values["apartment_number"] = _try_extract_match("apartment_number", text, warnings)
    values["floor"] = _try_extract_match("floor", text, warnings)
    values["area_gross_sqm"] = _try_extract_float("area_sqm", "area_gross_sqm", text, warnings)
    values["price_without_costs"] = _try_extract_amount("price_base", "price_without_costs", text, warnings)
    values["price_with_costs"] = _try_extract_amount("price_total", "price_with_costs", text, warnings)
    values["registration_fee"] = _try_extract_amount("reg_fee", "registration_fee", text, warnings)

    project_raw = _try_extract_match("project_name", text, warnings)
    values["project_name"] = project_raw.strip() if project_raw else ""

    # Extract client details from page 2
    try:
        client_name = _extract_client_name(text)
        values["client_name"] = client_name
    except ExtractionError as e:
        values["client_name"] = ""
        warnings.append(ExtractionWarning("client_name", str(e)))

    data = ReservationData(
        client_name=values["client_name"],
        apartment_number=values["apartment_number"],
        floor=values["floor"],
        area_gross_sqm=values["area_gross_sqm"],
        price_without_costs=values["price_without_costs"],
        price_with_costs=values["price_with_costs"],
        registration_fee=values["registration_fee"],
        project_name=values["project_name"],
    )

    return ReservationExtractionResult(data=data, warnings=warnings)


# === Fault-tolerant extraction helpers ===

def _try_extract_match(
    pattern_key: str, text: str, warnings: list[ExtractionWarning],
    field_name: str | None = None,
) -> str:
    """Try to extract a regex match. On failure, append warning and return empty string."""
    fname = field_name or pattern_key
    try:
        return _extract_match(pattern_key, text)
    except ExtractionError as e:
        warnings.append(ExtractionWarning(fname, str(e)))
        return ""


def _try_extract_int(
    pattern_key: str, text: str, warnings: list[ExtractionWarning],
    field_name: str | None = None,
) -> int:
    """Try to extract an integer. On failure, append warning and return 0."""
    fname = field_name or pattern_key
    try:
        return int(_extract_match(pattern_key, text))
    except (ExtractionError, ValueError) as e:
        warnings.append(ExtractionWarning(fname, str(e)))
        return 0


def _try_extract_float(
    pattern_key: str, field_name: str, text: str, warnings: list[ExtractionWarning],
) -> float:
    """Try to extract a float. On failure, append warning and return 0.0."""
    try:
        raw = _extract_match(pattern_key, text)
        return parse_hebrew_amount(raw)
    except (ExtractionError, ValueError) as e:
        warnings.append(ExtractionWarning(field_name, str(e)))
        return 0.0


def _try_extract_amount(
    pattern_key: str, field_name: str, text: str, warnings: list[ExtractionWarning],
) -> float:
    """Try to extract a currency amount. On failure, append warning and return 0.0."""
    return _try_extract_float(pattern_key, field_name, text, warnings)


# === Core extraction (still raises on failure — used by extract()) ===

def get_pdf_text(pdf_path: str, ocr_pages: list[int] | None = None) -> str:
    """Extract text from PDF, with OCR fallback.

    Args:
        pdf_path: Path to the PDF file.
        ocr_pages: If OCR is needed, only scan these 1-based page numbers.
                   None means scan all pages.

    When *ocr_pages* is provided, those pages are **always** OCR'd (even if
    native text extraction returns content).  Native text from non-OCR pages
    is still included.  This ensures filled-in form values — which pypdf
    often misses — are captured at the correct DPI.
    """
    if ocr_pages:
        # Always OCR the specified pages; use native text for the rest
        logger.info("OCR pages configured — OCR'ing pages %s", ocr_pages)
        reader = PdfReader(pdf_path)
        ocr_set = set(ocr_pages)
        native_text = ""
        for page_idx, page in enumerate(reader.pages):
            page_num = page_idx + 1  # 1-based
            if page_num not in ocr_set:
                page_text = page.extract_text() or ""
                native_text += page_text + "\n"
        ocr_text = _ocr_extract(pdf_path, ocr_pages=ocr_pages)
        return native_text + ocr_text

    # No OCR pages configured — native first, full OCR fallback
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n"

    if len(text.strip()) < 50:
        logger.info("Text extraction yielded < 50 chars, falling back to OCR")
        return _ocr_extract(pdf_path, ocr_pages=None)

    return text


def _ocr_extract(pdf_path: str, ocr_pages: list[int] | None = None) -> str:
    """OCR fallback for scanned PDFs. Processes one page at a time at 300 DPI."""
    import pytesseract
    from pdf2image import convert_from_path

    reader = PdfReader(pdf_path)
    total = len(reader.pages)

    if ocr_pages is None:
        pages_to_scan = list(range(1, total + 1))
    else:
        pages_to_scan = [p for p in ocr_pages if 1 <= p <= total]

    text = ""
    for page_num in pages_to_scan:
        images = convert_from_path(
            pdf_path, dpi=300, first_page=page_num, last_page=page_num
        )
        for img in images:
            page_text = pytesseract.image_to_string(img, lang="heb")
            text += page_text + "\n"
    return text


def _extract_match(field: str, text: str) -> str:
    """Extract a regex match for a named field."""
    pattern = PATTERNS[field]
    cleaned = re.sub(r'[\u200f\u200e\u200b]', '', text)
    match = re.search(pattern, cleaned, re.DOTALL)
    if not match:
        raise ExtractionError(f"Cannot find '{field}' in reservation PDF. Pattern: {pattern}")
    return match.group(1).strip()


def _extract_client_name(text: str) -> str:
    """Extract client name from page 2."""
    cleaned = re.sub(r'[\u200f\u200e\u200b]', '', text)

    name_match = re.search(r'שם\s+ו?שם\s+משפחה\s*:', cleaned)

    if name_match:
        transfer_match = re.search(r'סיבת\s+העברה[^\n]*\n(.+)', cleaned, re.DOTALL)
        if transfer_match:
            remaining = transfer_match.group(1).strip()
            lines = [l.strip() for l in remaining.split('\n') if l.strip()]
            if lines:
                return lines[0]

    # Fallback: look for ID pattern and get name before it
    id_match = re.search(r'(\d{7,9})', cleaned)
    if id_match:
        pos = id_match.start()
        before = cleaned[:pos]
        lines = [l.strip() for l in before.split('\n') if l.strip()]
        if lines:
            candidate = lines[-1]
            if re.search(r'[\u0590-\u05FF]', candidate) and not re.search(r'\d', candidate):
                return candidate

    raise ExtractionError("Cannot extract client name from reservation PDF")


class ExtractionError(Exception):
    """Raised when a field cannot be extracted from a document."""
    pass
