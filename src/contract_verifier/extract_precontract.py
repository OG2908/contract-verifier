"""Extract structured data from a signed Hebrew private agreement contract PDF."""
from __future__ import annotations

import re
import logging

from .extract_reservation import get_pdf_text, ExtractionError
from .models import (
    ExtractionWarning,
    PreContractData,
    PreContractExtractionResult,
    PreContractPaymentLine,
    parse_hebrew_amount,
)

logger = logging.getLogger(__name__)


def _clean(text: str) -> str:
    """Strip RTL markers and zero-width chars."""
    return re.sub(r'[\u200f\u200e\u200b]', '', text)


# ---------------------------------------------------------------------------
# Amount parsing — handles OCR artefact where € is read as digit "6"
# ---------------------------------------------------------------------------

def _parse_amount(raw: str) -> float:
    """Parse a euro amount, handling OCR artefact where € → '6'.

    In OCR output, amounts may appear as:
      - "260,000 6"  (number followed by €-as-6)
      - "€260,000"   (normal)
      - "260,000"    (no currency symbol)
    """
    # First try standard parse (handles €, אירו, commas, etc.)
    try:
        return parse_hebrew_amount(raw)
    except ValueError:
        pass

    # Strip trailing " 6" which is OCR artefact for €
    cleaned = raw.strip()
    if cleaned.endswith(' 6'):
        cleaned = cleaned[:-2]
    elif cleaned.endswith('6') and len(cleaned) > 1 and not cleaned[-2].isdigit():
        cleaned = cleaned[:-1]

    try:
        return parse_hebrew_amount(cleaned)
    except ValueError:
        raise ValueError(f"Cannot parse amount from: {raw!r}")


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _extract_client_name(text: str) -> str:
    """Extract buyer name from contract parties section."""
    # Format: "NAME ת.ז. XXXXXXXX" — name may be 2+ Hebrew words
    match = re.search(r'([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+)+)\s+ת\.?ז\.?\s*\.?\s*(\d{7,9})', text)
    if match:
        return match.group(1).strip()

    # Fallback: look for name before ID number in "מצד שני" area
    match = re.search(r'מצד\s+שני', text)
    if match:
        before = text[max(0, match.start() - 200):match.start()]
        id_match = re.search(r'([\u0590-\u05FF]+(?:\s+[\u0590-\u05FF]+)+)\s+ת\.?ז', before)
        if id_match:
            return id_match.group(1).strip()

    raise ExtractionError("Cannot extract client name from contract PDF")


def _extract_apartment_number(text: str) -> str:
    """Extract apartment number (e.g., 'C2')."""
    # Table format: value before label (e.g., "A10מספר דירה")
    match = re.search(r'([A-Za-z]\d+)\s*מספר\s+דירה', text)
    if match:
        return match.group(1).strip()

    # Look for "מספר דירה:" followed by value — OCR may drop letters
    # Try with letter prefix first
    match = re.search(r'מספר\s+דירה\s*:?\s*([A-Za-z]\d+)', text)
    if match:
        return match.group(1).strip()

    # Just digits (OCR may drop the letter)
    match = re.search(r'מספר\s+דירה\s*:?\s*(\d+[A-Za-z]?)', text)
    if match:
        return match.group(1).strip()

    # Fallback: look for apartment pattern near "דירה:"
    match = re.search(r'דירה\s*:\s*([A-Za-z]?\d+[A-Za-z]?)', text)
    if match:
        return match.group(1).strip()

    raise ExtractionError("Cannot extract apartment number")


def _extract_purchase_price(text: str) -> float:
    """Extract purchase price (התמורה) — the price WITHOUT deal costs."""
    # OCR: "התמורה (כהגדרתה בהסכס) הינה בסך של 242,266 6"
    match = re.search(r'התמורה[^0-9]{0,80}בסך\s+של\s+([\d,]+)\s*(?:6|€)?', text)
    if match:
        return _parse_amount(match.group(1))

    # Broader fallback
    match = re.search(r'התמורה[^0-9]{0,100}([\d,]+)\s*(?:6|€|אירו)?', text)
    if match:
        return _parse_amount(match.group(1))

    # Fallback: back-calculate from total_with_costs and cost percentage
    # Kriopigi contracts show "8.5%)" near cost breakdown but not the base price
    pct_match = re.search(r'(\d+\.?\d*)%\s*\)', text)
    if pct_match:
        cost_pct = float(pct_match.group(1))
        try:
            total = _extract_total_with_costs(text)
            return round(total / (1 + cost_pct / 100), 2)
        except ExtractionError:
            pass

    raise ExtractionError("Cannot extract purchase price (התמורה)")


def _extract_total_with_costs(text: str) -> float:
    """Extract total purchase price including costs (סכום הרכישה הכולל)."""
    # OCR: "סכוס הרכישה הכולל הינו בסך של 260,000 6" or "תכולל הינו בסך של 260,000 6"
    # Match specifically "הינו בסך של AMOUNT" after the total label
    match = re.search(
        r'הרכישה\s+(?:ה?כולל|תכולל)\s+הינו\s+בסך\s+של\s+([\d,]+)\s*(?:6|€)?',
        text
    )
    if match:
        return _parse_amount(match.group(1))

    # Broader: "סכום הרכישה הכולל" then "בסך של AMOUNT"
    match = re.search(
        r'סכו[םס]\s+הרכישה\s+(?:ה?כולל|תכולל)[^0-9]{0,80}בסך\s+של\s+([\d,]+)\s*(?:6|€)?',
        text
    )
    if match:
        return _parse_amount(match.group(1))

    # Table format: value before label (e.g., "117,127סכום הרכישה ביורו כולל")
    match = re.search(r'([\d,]+)\s*סכו[םס]\s+הרכישה\s+(?:ביורו\s+)?כולל', text)
    if match:
        return _parse_amount(match.group(1))

    raise ExtractionError("Cannot extract total purchase price (סכום הרכישה הכולל)")


def _extract_gross_sqm(text: str) -> float:
    """Extract gross area in sqm."""
    # OCR renders "מ"ר" as "מייר". Area may be garbled (75→5).
    # Look for pattern near "שטח דירה" or "מייר ברוטו"
    match = re.search(r'([\d,.]+)\s*מ["\u05F4]?[יר]+\s*ברוטו', text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            pass

    # Table format: value before label (e.g., "35.42שטח דירה")
    match = re.search(r'([\d,.]+)\s*שט[חת]\s+דירה', text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            pass

    match = re.search(r'שט[חת]\s+דירה[^0-9]{0,50}([\d,.]+)', text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            pass

    raise ExtractionError("Cannot extract gross sqm")


def _extract_balcony_sqm(text: str) -> float:
    """Extract balcony area in sqm."""
    # Table format: value before label (e.g., "6.72שטח מרפסת")
    match = re.search(r'([\d,.]+)\s*(?:שט[חת]\s+)?מרפסת', text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            pass

    # OCR: "מרפסת : 2 מייר" (may be garbled)
    match = re.search(r'מרפסת\s*:?\s*([\d,.]+)\s*מ', text)
    if match:
        try:
            return float(match.group(1).replace(',', ''))
        except ValueError:
            pass

    raise ExtractionError("Cannot extract balcony sqm")


def _extract_delivery_date(text: str) -> str:
    """Extract delivery date."""
    # OCR: "מועד מסירת הדירה (כהגדרתו בסעיף 8.1 לעיל) יהיה לא יאוחר מיוס 31/08/2026"
    # Must match near "מסירת הדירה" to avoid picking up signing date
    # Note: .{0,120} because the gap may contain "8.1" (digits)
    match = re.search(
        r'מועד\s+מסירת\s+הדירה.{0,120}?(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})',
        text, re.DOTALL
    )
    if match:
        return match.group(1)

    raise ExtractionError("Cannot extract delivery date")


def _extract_late_delivery_payment(text: str) -> float:
    """Extract late delivery penalty amount (EUR/month)."""
    match = re.search(r'פיצוי[^0-9]{0,100}([\d,]+)\s*(?:6|€|אירו)', text)
    if match:
        return _parse_amount(match.group(1))

    raise ExtractionError("Cannot extract late delivery payment")


def _extract_registration_fee(text: str) -> float:
    """Extract registration fee (דמי רצינות) amount."""
    # OCR: "דמי הרצינות בסך של 4,000 6."
    # Match specifically "רצינות בסך של AMOUNT"
    match = re.search(r'רצינות\s+בסך\s+של\s+([\d,]+)\s*(?:6|€)?', text)
    if match:
        return _parse_amount(match.group(1))

    # Fallback: "דמי רצינות" section header followed by amount
    match = re.search(r'דמי\s+(?:ה)?רצינות\n[^\n]*בסך\s+של\s+([\d,]+)\s*(?:6|€)?', text)
    if match:
        return _parse_amount(match.group(1))

    # Kriopigi terms: "דמי הרשמה" or "דמי הקמה"
    match = re.search(r'דמי\s+(?:ה)?(?:רשמה|קמה)\s+בסך\s+(?:של\s+)?([\d,]+)\s*(?:6|€)?', text)
    if match:
        return _parse_amount(match.group(1))

    # Table format: value before label (e.g., "2,000דמי הרשמה")
    match = re.search(r'([\d,]+)\s*דמי\s+(?:ה)?(?:רשמה|קמה|רצינות)', text)
    if match:
        return _parse_amount(match.group(1))

    raise ExtractionError("Cannot extract registration fee")


def _detect_mortgage(text: str) -> bool:
    """Check if mortgage appendix exists."""
    return bool(re.search(r'נספח\s+משכנתא', text))


def _detect_storage(text: str) -> bool:
    """Check if storage (מחסן) is mentioned in apartment details."""
    return bool(re.search(r'מחסן', text))


def _detect_parking(text: str) -> bool:
    """Check if parking (חניה/חנייה) is mentioned."""
    return bool(re.search(r'חניי?ה', text))


def _extract_payment_lines(text: str, warnings: list[ExtractionWarning]) -> list[PreContractPaymentLine]:
    """Extract payment schedule from the contract."""
    lines: list[PreContractPaymentLine] = []

    # Strategy 1: Match ordinal payment names with amounts and percentages
    # OCR pattern examples:
    #   "41. תשלום ראשון בסך של 26,000 6 (10% מסכוס הרכישה הכולל)."
    #   "2. תשלום שני בסך של 104,000 6 (40% מסכוס הרכישה הכולל)."
    #   "4. תשלוס רביעי בסך של 39,000 6 (15% מסכוס הרכישה הכולל)."
    # Note: OCR uses ( and ) — Hebrew RTL flips parens
    ordinals = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שביעי"]

    for ordinal in ordinals:
        # Match "תשלום ORDINAL בסך של AMOUNT 6 (PERCENT%"
        # Note: "תשלוס" is OCR variant of "תשלום"
        pattern = re.compile(
            r'תשלו[םס]\s+' + re.escape(ordinal) +
            r'\s+בסך\s+של\s+([\d,]+)\s*(?:6|€)'
            r'[^%]{0,30}?(\d+)%',
            re.DOTALL
        )
        match = pattern.search(text)
        if match:
            amount = _parse_amount(match.group(1))
            pct = float(match.group(2))
            lines.append(PreContractPaymentLine(
                name=f"תשלום {ordinal}",
                amount=amount,
                percentage=pct,
            ))

    if lines:
        return lines

    # Strategy 2: Table format (Kriopigi Appendix D)
    # Rows like: "11,743 €11,513 10% מקדמה" or "58,715 €57,563 50% תשלום ראשון"
    # Pattern: SURCHARGE €BASE PCT% — we capture the BASE amount (after €)
    table_pattern = re.compile(r'([\d,]+)\s*€\s*([\d,]+)\s+(\d+)%')
    table_matches = list(table_pattern.finditer(text))
    if table_matches:
        payment_names = ["מקדמה", "תשלום ראשון", "תשלום שני", "תשלום שלישי",
                         "תשלום רביעי", "תשלום חמישי"]
        for i, m in enumerate(table_matches):
            base_amount = _parse_amount(m.group(2))
            pct = float(m.group(3))
            # Find payment name in text following the match
            after = text[m.end():m.end() + 100]
            name = None
            for pn in payment_names:
                if pn in after:
                    name = pn
                    break
            if name is None:
                name = f"תשלום {i + 1}" if i > 0 else "מקדמה"
            lines.append(PreContractPaymentLine(
                name=name,
                amount=base_amount,
                percentage=pct,
            ))
        return lines

    # Strategy 3: Find "בסך של AMOUNT 6" patterns in payment section
    section_match = re.search(r'סכו[םס]\s+הרכישה\s+(?:ה?כולל|תכולל)\s+ישול[םס]', text)
    if section_match:
        payment_text = text[section_match.end():section_match.end() + 2000]
        amount_pattern = re.compile(r'בסך\s+של\s+([\d,]+)\s*(?:6|€)')
        idx = 1
        for m in amount_pattern.finditer(payment_text):
            amount = _parse_amount(m.group(1))
            lines.append(PreContractPaymentLine(
                name=f"תשלום {idx}",
                amount=amount,
            ))
            idx += 1

    if not lines:
        warnings.append(ExtractionWarning("payment_lines", "No payment lines found"))

    return lines


# ---------------------------------------------------------------------------
# Fault-tolerant extraction helpers
# ---------------------------------------------------------------------------

def _try_extract(field_name, fn, warnings, default=None):
    """Run an extraction function; on failure, record warning and return default."""
    try:
        return fn()
    except (ExtractionError, ValueError) as e:
        warnings.append(ExtractionWarning(field_name, str(e)))
        return default


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_safe(pdf_path: str) -> PreContractExtractionResult:
    """Extract pre-contract data from a signed Hebrew contract PDF.

    Returns partial results with warnings for any fields that fail to extract.
    """
    raw_text = get_pdf_text(pdf_path)
    text = _clean(raw_text)
    logger.debug("Cleaned PDF text (first 1000 chars): %s", text[:1000])

    warnings: list[ExtractionWarning] = []

    client_name = _try_extract("client_name", lambda: _extract_client_name(text), warnings, "")
    apartment_number = _try_extract("apartment_number", lambda: _extract_apartment_number(text), warnings, "")
    purchase_price = _try_extract("purchase_price", lambda: _extract_purchase_price(text), warnings, 0.0)
    total_with_costs = _try_extract("total_with_costs", lambda: _extract_total_with_costs(text), warnings, 0.0)
    gross_sqm = _try_extract("gross_sqm", lambda: _extract_gross_sqm(text), warnings, 0.0)
    balcony_sqm = _try_extract("balcony_sqm", lambda: _extract_balcony_sqm(text), warnings, 0.0)
    delivery_date = _try_extract("delivery_date", lambda: _extract_delivery_date(text), warnings, "")
    late_delivery = _try_extract("late_delivery_payment", lambda: _extract_late_delivery_payment(text), warnings, 0.0)
    registration_fee = _try_extract("registration_fee", lambda: _extract_registration_fee(text), warnings, 0.0)

    has_mortgage = _detect_mortgage(text)
    has_storage = _detect_storage(text)
    has_parking = _detect_parking(text)

    payment_lines = _extract_payment_lines(text, warnings)

    data = PreContractData(
        client_name=client_name,
        apartment_number=apartment_number,
        purchase_price=purchase_price,
        total_with_costs=total_with_costs,
        gross_sqm=gross_sqm,
        balcony_sqm=balcony_sqm,
        delivery_date=delivery_date,
        late_delivery_payment=late_delivery,
        has_mortgage=has_mortgage,
        has_storage=has_storage,
        has_parking=has_parking,
        payment_lines=payment_lines,
    )

    return PreContractExtractionResult(data=data, warnings=warnings)
