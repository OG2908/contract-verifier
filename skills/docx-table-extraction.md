# Skill: DOCX Table Extraction for Hebrew Contracts

## When to Use
Extracting structured data from tables in Hebrew-language Word documents, specifically real estate contracts with appendices containing property details, cost breakdowns, and payment schedules.

## Strategy

### Step 1: Find Tables by Content, Not Position
```python
from docx import Document

def find_table_by_label(doc: Document, label: str) -> 'Table | None':
    """
    Find a table containing a specific Hebrew label.
    NEVER use table index — template variations shift positions.
    """
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if label in cell.text:
                    return table
    return None

# Usage
doc = Document("contract.docx")
appendix_a = find_table_by_label(doc, "מספר דירה")
appendix_d = find_table_by_label(doc, "פרויקט")
```

### Step 2: Extract Rows by Label Matching
```python
def get_row_value(table, label: str, value_col: int = 1) -> str:
    """
    Find a row where any cell contains `label`, return value from `value_col`.
    Handles merged cells and varying column counts.
    """
    for row in table.rows:
        cells = row.cells
        for i, cell in enumerate(cells):
            if label in cell.text.strip():
                # Value is typically in the cell to the left (Hebrew RTL)
                # or at a specific column index
                for j in range(len(cells)):
                    if j != i:
                        val = cells[j].text.strip()
                        if val and val != cell.text.strip():
                            return val
    return ""
```

### Step 3: Extract Cost Breakdown (Appendix A)
```python
import re

def extract_cost_lines(table) -> list[dict]:
    """
    Extract cost breakdown lines from Appendix A.
    Pattern: each row has cost name, percentage, and amount in €.
    """
    costs = []
    in_costs_section = False
    
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        full_row = " ".join(cells)
        
        # Start capturing after "עלויות הנלוות" row
        if "עלויות הנלוות" in full_row:
            in_costs_section = True
            continue
        
        if in_costs_section:
            # Look for percentage pattern like (3.09%) or (1%)
            pct_match = re.search(r'\(([\d.]+)%\)', full_row)
            # Look for euro amount
            amount_match = re.search(r'€([\d,]+)', full_row)
            
            if pct_match and amount_match:
                # Extract the name (Hebrew text before the percentage)
                name = re.sub(r'\([\d.]+%\)', '', full_row)
                name = re.sub(r'€[\d,]+', '', name).strip()
                
                costs.append({
                    'name': name,
                    'percentage': float(pct_match.group(1)),
                    'amount': parse_amount(amount_match.group(1)),
                })
    
    return costs
```

### Step 4: Extract Payment Schedule (Appendix D)
```python
PAYMENT_LABELS = ["מקדמה", "תשלום ראשון", "תשלום שני", "תשלום שלישי"]

def extract_payment_lines(table) -> list[dict]:
    """
    Extract payment schedule from Appendix D.
    Each row: name | percentage | base_amount | amount_with_surcharge | notes
    """
    payments = []
    
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        full_row = " ".join(cells)
        
        for label in PAYMENT_LABELS:
            if label in full_row:
                # Extract percentage (e.g., "10%", "50%")
                pct = re.search(r'(\d+)%', full_row)
                # Extract euro amounts (there will be two: base and with surcharge)
                amounts = re.findall(r'€([\d,]+)', full_row)
                
                if pct and len(amounts) >= 2:
                    payments.append({
                        'name': label,
                        'percentage': float(pct.group(1)),
                        'base_amount': parse_amount(amounts[0]),
                        'amount_with_surcharge': parse_amount(amounts[1]),
                        'notes': _extract_notes(cells),
                    })
                break
    
    return payments
```

## Critical Rules

1. **NEVER hardcode table indices.** Use `find_table_by_label()`. Table count changes if the template has optional sections.
2. **NEVER hardcode row indices.** Search by Hebrew label text. Row order can vary.
3. **Cell text includes merged cells.** `python-docx` may return the same text for multiple cells if they're merged. Always deduplicate.
4. **RTL column order.** In a Hebrew Word doc, the visual "first" column (rightmost) may be `cells[-1]` in python-docx. Test with your actual document.
5. **Strip aggressively.** Use `.strip()` on every cell value. Hebrew text often has invisible RTL markers (`\u200f`, `\u200e`), zero-width spaces (`\u200b`), and non-breaking spaces (`\u00a0`).
6. **Euro symbol variations.** Handle both `€` (U+20AC) and the rare Hebrew "אירו" in the same extraction logic.

## Testing Approach

```python
def test_appendix_a_extraction():
    """Verify against known values from the sample contract."""
    doc = Document("tests/fixtures/sample_contract.docx")
    data = extract_contract(doc)
    
    assert data.apartment_number == 6
    assert data.area_gross_sqm == 37.07
    assert data.total_purchase_price == 122224
    assert len(data.cost_lines) == 6
    assert data.cost_lines[0].name == "מס רכישה"
    assert data.cost_lines[0].percentage == 3.09
    assert data.cost_lines[0].amount == 3481
```

## Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| Table not found | Label has extra whitespace or Hebrew marks | Use `label in cell.text` not `==` |
| Wrong column value | RTL layout — visual column order ≠ code order | Print all cells with indices to map |
| Missing cost lines | "in_costs_section" flag never triggered | Check exact Hebrew spelling of trigger label |
| Euro amount off by 1 | Rounding in Word vs. computed | Use ±1€ tolerance in verification |
