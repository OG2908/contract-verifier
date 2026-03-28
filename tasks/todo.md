# Contract Verifier — Implementation Plan

## Project Summary

A CLI tool that verifies real estate purchase contracts against their source reservation agreements. Pulls the reservation PDF from Google Drive, extracts terms from both documents, runs deterministic math and field checks, and produces a pass/fail verification report.

**Core principle:** Zero LLM in the verification path. All checks are regex extraction + arithmetic. Accuracy over sophistication.

---

## Phase 0: Project Setup

- [x] 0.1 Initialize Python project with `pyproject.toml` (Python 3.11+)
- [x] 0.2 Create virtual environment and install core dependencies:
  - `python-docx` (contract .docx parsing)
  - `pypdf` (reservation PDF text extraction)
  - `pytesseract` + `Pillow` (OCR fallback for scanned PDFs)
  - `google-api-python-client` + `google-auth-oauthlib` (Drive API)
  - `rich` (terminal output formatting)
- [x] 0.3 Create project directory structure:
  ```
  contract-verifier/
  ├── src/
  │   ├── __init__.py
  │   ├── main.py              # CLI entry point
  │   ├── extract_reservation.py  # PDF → structured data
  │   ├── extract_contract.py     # DOCX → structured data
  │   ├── verify.py               # comparison engine
  │   ├── report.py               # pass/fail output
  │   ├── drive_fetch.py          # Google Drive file retrieval
  │   ├── project_config.py       # load per-project financial rules
  │   └── models.py               # dataclasses for extracted data
  ├── projects/
  │   ├── _template.json       # blank config for new projects
  │   ├── kriopigi.json        # Kriopigi Halkidiki project config
  │   └── ...                  # one JSON per project
  ├── tests/
  │   ├── test_extract_reservation.py
  │   ├── test_extract_contract.py
  │   ├── test_verify.py
  │   ├── test_project_config.py
  │   └── fixtures/            # sample docs for testing
  ├── tasks/
  │   ├── todo.md
  │   └── lessons.md
  ├── skills/
  │   ├── hebrew-pdf-extraction.md
  │   ├── docx-table-extraction.md
  │   └── drive-folder-navigation.md
  └── pyproject.toml
  ```
- [x] 0.4 Copy sample reservation PDF and contract DOCX into `tests/fixtures/`
- [x] 0.5 Verify Tesseract is installed with Hebrew language pack (`heb.traineddata`)

---

## Phase 1: Data Models

- [x] 1.1 Create `models.py` with dataclasses:

```python
@dataclass
class ReservationData:
    """Source of truth — extracted from reservation agreement PDF"""
    client_name: str
    client_id: str          # תעודת זהות
    apartment_number: int
    floor: str              # e.g., "קרקע"
    area_gross_sqm: float   # e.g., 29.59
    price_without_costs: float   # מחיר רכישה e.g., 91,322
    price_with_costs: float      # מחיר כולל e.g., 99,085
    registration_fee: float      # דמי רצינות e.g., 2,000
    project_name: str            # e.g., "קריופיגי"

@dataclass
class CostLine:
    """Single line in the deal costs breakdown"""
    name: str           # e.g., "מס רכישה"
    percentage: float   # e.g., 3.09
    amount: float       # e.g., 3,481

@dataclass
class PaymentLine:
    """Single line in the payment schedule"""
    name: str               # e.g., "מקדמה", "תשלום ראשון"
    percentage: float       # e.g., 10, 50, 20, 20
    base_amount: float      # e.g., 12,022
    amount_with_surcharge: float  # e.g., 12,263
    notes: str              # payment terms/destination

@dataclass
class ContractData:
    """Extracted from the purchase contract DOCX"""
    client_name: str
    client_id: str
    apartment_number: int
    floor: str
    area_gross_sqm: float
    balcony_sqm: float
    total_purchase_price: float      # סכום הרכישה כולל עלויות
    total_costs_percentage: float    # e.g., 8.5
    cost_lines: list[CostLine]
    registration_fee: float          # דמי הרשמה
    remaining_after_registration: float
    surcharge_percentage: float      # e.g., 2.0
    payment_lines: list[PaymentLine]
    project_name: str
    delivery_date: str

@dataclass
class VerificationResult:
    """Single check result"""
    check_name: str
    passed: bool
    expected: str
    actual: str
    severity: str  # "error" or "warning"

@dataclass
class VerificationReport:
    """Full report"""
    client_name: str
    project_name: str
    apartment_number: int
    results: list[VerificationResult]
    timestamp: str

@dataclass
class ProjectCostLine:
    """Expected cost line from project config"""
    name: str
    percentage: float

@dataclass
class ProjectPaymentLine:
    """Expected payment line from project config"""
    name: str
    percentage: float
    destination: str   # "company_bank" or "escrow"
    timing: str

@dataclass
class ProjectConfig:
    """Per-project financial rules — loaded from projects/<name>.json"""
    project_name: str
    project_name_variants: list[str]
    total_costs_percentage: float
    costs_calculated_on: str          # "price_without_costs" or "total_price"
    expected_cost_lines: list[ProjectCostLine]
    registration_fee: float
    surcharge_percentage: float
    surcharge_clearshift: float
    surcharge_security_buffer: float
    payments_calculated_on: str       # "total_minus_registration"
    expected_payment_lines: list[ProjectPaymentLine]
    rounding_tolerance_eur: float
    area_tolerance_sqm: float
```

- [x] 1.2 Write unit tests for model serialization / deserialization
- [x] 1.3 Verify models cover ALL fields from both sample documents

---

## Phase 1.5: Project Configuration Loader

- [x] 1.5.1 Write `project_config.py` with:
  ```python
  def load_config(project_name: str) -> ProjectConfig
  def list_projects() -> list[str]
  ```
- [x] 1.5.2 Config files live in `projects/` directory. Loader:
  - Scans all `.json` files in `projects/` (skip `_template.json`)
  - Matches `project_name` or any value in `project_name_variants` (case-insensitive, whitespace-normalized)
  - If no match found: raise clear error listing available projects
- [x] 1.5.3 Validate config on load:
  - All cost line percentages must sum to `total_costs_percentage`
  - All payment line percentages must sum to 100
  - No negative or zero values where not expected
  - Required fields are present
- [x] 1.5.4 **Test:** load `projects/kriopigi.json`, verify all fields populate correctly
- [x] 1.5.5 **Test:** call with unknown project name, verify helpful error message

---

## Phase 2: Reservation PDF Extraction

> **Subagent task:** Research and test Hebrew OCR accuracy on sample PDF before writing extraction logic.

- [x] 2.1 Write `extract_reservation.py` with `extract(pdf_path: str) -> ReservationData`
- [x] 2.2 Implement dual extraction strategy:
  - Try `pypdf` text extraction first
  - If text is empty or < 50 chars → fallback to Tesseract OCR with `lang='heb'`
- [x] 2.3 Write regex patterns for each field from paragraph 2:
  ```
  apartment_number:    r'דירה\s+מספר\s+(\d+)'
  floor:               r'בקומה/מפלס\s+(\S+)'
  area_gross_sqm:      r'שטח\s+של\s+כ?-?\s*([\d,.]+)\s*מטר\s*ברוטו'
  price_without_costs: r'במחיר\s+רכישה\s+של\s+([\d,]+)\s*אירו'
  price_with_costs:    r'ובמחיר\s+כולל\s+של\s+([\d,]+)\s*אירו'
  registration_fee:    r'דמי\s+רצינות\s+בסך\s+([\d,]+)\s*אירו'
  project_name:        r'בפרויקט\s+"?([^"]+)"?'
  ```
- [x] 2.4 Write `parse_hebrew_number(s: str) -> float` utility (strips commas, handles Hebrew formatting)
- [x] 2.5 Extract client details from page 2 (name, ID, phone, email) — regex on table-like structure
- [x] 2.6 **Test against sample:** verify all 8 fields extracted correctly from `טופס_הצטרפות_--_קריופיגי_-דירה_1.pdf`
- [x] 2.7 **Test OCR fallback:** convert sample PDF to image-only PDF, verify extraction still works
- [x] 2.8 Handle edge cases:
  - Multiple spaces / line breaks in middle of number
  - "אלפיים" (two thousand) written as word vs. "2,000" as digits
  - Missing fields → raise clear error, don't silently return None

---

## Phase 3: Contract DOCX Extraction

> **Subagent task:** Explore python-docx table structure to map table indices to appendices.

- [x] 3.1 Write `extract_contract.py` with `extract(docx_path: str) -> ContractData`
- [x] 3.2 Implement table finder — locate appendix tables by header content, not by position:
  - Appendix A table: contains "מספר דירה" in first column
  - Appendix D table: contains "פרויקט" in first column or "נספח תשלומים" nearby
- [x] 3.3 Extract Appendix A fields:
  - `apartment_number` from row containing "מספר דירה"
  - `floor` from row containing "קומה"
  - `area_gross_sqm` from row containing "שטח דירה"
  - `balcony_sqm` from row containing "שטח מרפסת"
  - `total_purchase_price` from row containing "סכום הרכישה"
  - `total_costs_percentage` from row containing "עלויות הנלוות" (extract % value)
  - Each cost line: iterate remaining rows, extract name + percentage + amount
- [x] 3.4 Extract Appendix D fields:
  - `project_name` + `apartment_number` from header row
  - `total_price_with_costs` from "מחיר רכישה כולל"
  - `registration_fee` from "דמי הרשמה"
  - `remaining_after_registration` from "נותר לשלם"
  - `surcharge_percentage` from notes column (extract "בתוספת X%")
  - Each payment line: name, percentage, base_amount, amount_with_surcharge, notes
- [x] 3.5 Extract client details from contract preamble (name, ID, email, phone)
- [x] 3.6 Extract delivery date from section 2.7 ("מועד מסירה")
- [x] 3.7 **Test against sample:** verify all fields from both appendix images match extracted data
- [x] 3.8 Handle edge cases:
  - Tables with merged cells
  - Euro sign (€) mixed with numbers
  - Hebrew quotation marks (״) vs standard quotes
  - Percentage signs with/without spaces

---

## Phase 4: Verification Engine

- [x] 4.1 Write `verify.py` with `verify(reservation: ReservationData, contract: ContractData, config: ProjectConfig) -> VerificationReport`
- [x] 4.2 Implement cross-document checks (reservation ↔ contract):

```
CHECK 1:  reservation.apartment_number == contract.apartment_number
CHECK 2:  reservation.floor == contract.floor
CHECK 3:  reservation.area_gross_sqm == contract.area_gross_sqm
CHECK 4:  reservation.price_with_costs == contract.total_purchase_price
CHECK 5:  reservation.registration_fee == contract.registration_fee
CHECK 6:  reservation.project_name matches contract.project_name
CHECK 7:  reservation.client_name == contract.client_name
CHECK 8:  reservation.client_id == contract.client_id
```

- [x] 4.3 Implement config validation checks (contract ↔ project config):

```
CHECK 9:   contract.registration_fee == config.registration_fee
CHECK 10:  contract.total_costs_percentage == config.total_costs_percentage
CHECK 11:  contract.surcharge_percentage == config.surcharge_percentage
CHECK 12:  Number of cost lines in contract matches config
CHECK 13:  Each cost line name in contract matches config (normalized Hebrew comparison)
CHECK 14:  Each cost line percentage in contract matches config
CHECK 15:  Number of payment lines in contract matches config
CHECK 16:  Each payment line percentage in contract matches config
```

- [x] 4.4 Implement internal contract math checks (using config for formulas):

```
CHECK 17:  Derive price_without_costs based on config.costs_calculated_on:
           if "price_without_costs": base = total_price / (1 + total_costs_pct/100)
           Each cost_line.amount ≈ base × cost_line.percentage / 100
           (tolerance: config.rounding_tolerance_eur)
CHECK 18:  Sum of cost_line amounts ≈ total_price - base
CHECK 19:  Cross-doc: reservation.price_without_costs ≈ computed base price
CHECK 20:  remaining_after_registration == total_purchase_price - config.registration_fee
CHECK 21:  Sum of payment_line percentages == 100
CHECK 22:  Each payment_line.base_amount ≈ remaining × percentage / 100
CHECK 23:  Each payment_line.amount_with_surcharge ≈ base_amount × (1 + config.surcharge_percentage/100)
CHECK 24:  Sum of all base_amounts == remaining_after_registration
```

- [x] 4.5 Define tolerance rules (from config):
  - Euro amounts: config.rounding_tolerance_eur (typically ±1€)
  - Percentages: exact match
  - Text fields: normalized comparison (strip whitespace, normalize Hebrew)
  - Area: config.area_tolerance_sqm (typically ±0.01 sqm)
- [x] 4.5 Each check produces a `VerificationResult` with `severity`:
  - **error**: any price / amount mismatch → blocks contract signing
  - **warning**: text normalization differences, minor formatting issues
- [x] 4.6 **Test with known-good pair:** both sample docs should pass all checks (or we identify real mismatches to flag)
- [x] 4.7 **Test with deliberately broken data:** modify fixture values to confirm each check catches errors

---

## Phase 5: Report Output

- [x] 5.1 Write `report.py` with `print_report(report: VerificationReport)`
- [x] 5.2 Terminal output using `rich`:
  - Header: client name, project, apartment number, timestamp
  - Section 1: Cross-document checks (reservation ↔ contract)
  - Section 2: Internal math checks
  - Each check: ✅ PASS or ❌ FAIL with expected vs. actual
  - Summary: X/Y checks passed, overall PASS/FAIL
- [x] 5.3 Optional: export report as JSON for later integrations
- [x] 5.4 Optional: export as simple text/markdown file for archival

---

## Phase 6: Google Drive Integration

> **Subagent task:** Set up Google OAuth credentials and test Drive API file listing.

- [x] 6.1 Write `drive_fetch.py` with `fetch_reservation(project_name: str, client_name: str) -> str`
  - Returns local path to downloaded PDF
- [x] 6.2 Implement folder navigation:
  ```
  Root → Customers → [Project Name] → [Client Name] → find PDF
  ```
  - Search by folder name match (fuzzy: handle Hebrew spacing variations)
  - Within client folder: find file matching "טופס הצטרפות" or "reservation" in name
  - If multiple matches: pick most recent by modified date
- [x] 6.3 Set up Google OAuth2 flow:
  - First run: browser auth → save token to `~/.contract-verifier/token.json`
  - Subsequent runs: use saved token, refresh if expired
  - Credentials file: `~/.contract-verifier/credentials.json`
- [x] 6.4 Add `--local` CLI flag to skip Drive and use a local PDF path instead (for testing)
- [x] 6.5 Cache downloaded PDFs in `~/.contract-verifier/cache/` to avoid re-downloading
- [x] 6.6 **Test:** verify correct PDF is fetched for sample client + project

---

## Phase 7: CLI Entry Point

- [x] 7.1 Write `main.py` with argparse:
  ```bash
  # Full flow with Google Drive (project config auto-detected from --project)
  python -m contract_verifier --project "קריופיגי" --client "נילי שטרן ביבר" --contract path/to/contract.docx

  # Local mode (both files local, still needs --project for config)
  python -m contract_verifier --local --project "קריופיגי" --reservation path/to/reservation.pdf --contract path/to/contract.docx

  # List available project configs
  python -m contract_verifier --list-projects
  ```
- [x] 7.2 Implement flow:
  1. Parse args
  2. **Load project config** from `projects/<project>.json` — fail early if not found
  3. Fetch/load reservation PDF
  4. Extract reservation data
  5. Extract contract data
  6. **Run verification with config** (all three inputs: reservation, contract, config)
  7. Print report
  8. Exit code: 0 = all pass, 1 = any failure
- [x] 7.3 Add `--verbose` flag for debug output (shows raw extracted values + loaded config)
- [x] 7.4 Add `--json` flag to output report as JSON instead of terminal
- [x] 7.5 Add `--list-projects` flag to show available project configs with their cost/payment structure summary

---

## Phase 8: End-to-End Testing

- [x] 8.1 Run full pipeline on sample reservation + contract pair
- [x] 8.2 Verify the intentional mismatch is caught:
  - Sample reservation is apartment 1 (€99,085) — sample contract is apartment 6 (€122,224)
  - The verifier MUST flag this as a mismatch
- [ ] 8.3 Create a matched fixture pair (same apartment) and verify all-pass
- [ ] 8.4 Test with 2-3 real contracts from your actual deals
- [ ] 8.5 Document any edge cases found in `tasks/lessons.md`

---

## Phase 9: Documentation

- [ ] 9.1 Write `README.md` with setup instructions, usage examples
- [ ] 9.2 Document Google Drive setup (OAuth credentials, required scopes)
- [ ] 9.3 Write "Adding a new project template" guide for future contract formats

---

## Future Phases (NOT for V1)

### Phase 10: Streamlit Web UI
- Drag-and-drop interface for office manager
- File upload for contract, auto-fetch reservation from Drive
- Visual report with green/red indicators

### Phase 11: Monday.com Integration
- Pull reservation data directly from Monday.com board instead of PDF
- Post verification results back to the deal's Monday.com item

### Phase 12: Multi-Project Template Support
- Template registry: map project names to extraction configurations
- Handle different cost structures per project (e.g., Peraia vs. Halkidiki)

### Phase 13: Contract Generation
- Auto-generate the contract from reservation data
- Then verify the generated output (close the loop)

---

## Review Notes

_(To be filled after each implementation phase)_
