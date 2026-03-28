# Skill: Hebrew PDF Data Extraction

## When to Use
Extracting structured fields (names, numbers, dates, IDs) from Hebrew-language PDF documents — both digital and scanned.

## Strategy

### Step 1: Determine PDF Type
```python
from pypdf import PdfReader

def get_text_or_ocr(pdf_path: str) -> str:
    """Try text extraction first, fallback to OCR."""
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    
    # If text is too short, PDF is likely scanned
    if len(text.strip()) < 50:
        return _ocr_extract(pdf_path)
    return text

def _ocr_extract(pdf_path: str) -> str:
    """OCR fallback for scanned PDFs."""
    import pytesseract
    from pdf2image import convert_from_path
    
    images = convert_from_path(pdf_path, dpi=300)
    text = ""
    for img in images:
        page_text = pytesseract.image_to_string(img, lang='heb')
        text += page_text + "\n"
    return text
```

### Step 2: Hebrew Number Parsing
```python
import re

def parse_hebrew_amount(raw: str) -> float:
    """
    Parse a number from Hebrew text.
    Handles: "122,224", "€122,224", "122224", "122.224" (European)
    """
    # Remove currency symbols, spaces, non-breaking spaces
    cleaned = re.sub(r'[€\s\u00a0]', '', raw)
    # Remove thousands separators (commas)
    cleaned = cleaned.replace(',', '')
    # Handle European notation (period as thousands separator)
    # Only if there are exactly 3 digits after the period
    if re.match(r'^\d+\.\d{3}$', cleaned):
        cleaned = cleaned.replace('.', '')
    return float(cleaned)
```

### Step 3: Regex Patterns for Hebrew Documents
Key patterns for real estate reservation forms:

```python
PATTERNS = {
    'apartment_number': r'דירה\s+מספר\s+(\d+)',
    'floor':            r'בקומה/מפלס\s+(\S+)',
    'area_sqm':         r'שטח\s+של\s+כ?-?\s*([\d,.]+)\s*מטר',
    'price_base':       r'במחיר\s+רכישה\s+של\s+([\d,]+)\s*אירו',
    'price_total':      r'ובמחיר\s+כולל\s+של\s+([\d,]+)\s*אירו',
    'reg_fee':          r'דמי\s+רצינות\s+בסך\s+([\d,]+)\s*אירו',
    'project_name':     r'בפרויקט\s+"?([^",(]+)',
    'israel_id':        r'ת\.?ז\.?\s*:?\s*(\d{5,9})',
    'client_name':      r'שם\s+ו?שם\s+משפחה\s*:\s*(.+)',
    'email':            r'דוא"?ל\s*:\s*(\S+@\S+)',
    'phone':            r'טלפון\s*:\s*([\d-]+)',
}
```

## Critical Rules

1. **Always log raw extracted text** before applying regex. Hebrew text extraction can silently reverse character order.
2. **Never assume page structure.** Search the full text for patterns, don't assume "field X is on page 1."
3. **Handle both "אירו" and "€"** — reservation forms use the Hebrew word, contracts use the symbol.
4. **Test with both digital and scanned versions** of the same document type.
5. **OCR quality:** Use DPI 300 for Tesseract. Lower DPI degrades Hebrew character recognition significantly.
6. **Right-to-left numbers:** Hebrew PDF extractors sometimes flip number order. Always sanity-check that extracted amounts are in the expected range (e.g., apartment price should be 50K-500K€).

## Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Numbers extracted as 0 or garbage | Scanned PDF, no text layer | Use OCR fallback |
| Regex matches nothing | Hebrew characters reversed or have invisible Unicode markers | Use `\s+` instead of spaces, strip `\u200f` (RTL mark) |
| Amount is 10x too high or low | Thousands separator misinterpreted | Route through `parse_hebrew_amount()` |
| Client name garbled | Mixed Hebrew/Latin in OCR | Extract Hebrew and Latin names separately |
