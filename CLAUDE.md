# CLAUDE.md — Contract Verifier

## What This Project Does

CLI tool that verifies real estate purchase contracts (.docx) against reservation agreements (.pdf). Pulls reservation from Google Drive, extracts data from both documents, runs deterministic checks, reports mismatches.

**Zero LLM in the verification path.** All checks are regex + arithmetic. This is a data extraction + math problem, not an AI problem.

## Language & Stack

- Python 3.11+
- `python-docx` for .docx table parsing
- `pypdf` + `pytesseract` for PDF text extraction / OCR
- `google-api-python-client` for Drive API
- `rich` for terminal output
- No web framework, no database, no LLM API

## Architecture (Three Clean Layers)

```
1. EXTRACTION    → extract_reservation.py, extract_contract.py
2. VERIFICATION  → verify.py (pure deterministic math/comparison)
3. REPORTING     → report.py (terminal + optional JSON output)
```

Plus `drive_fetch.py` for Google Drive integration, `models.py` for shared dataclasses, and `project_config.py` for loading per-project financial rules.

## Project Configuration (Critical)

**Each project has different cost structures and payment schedules.** These are NOT hardcoded. They live in JSON config files in `projects/`:

```
projects/
├── _template.json     # blank template for new projects
├── kriopigi.json      # Kriopigi Halkidiki project
├── peraia.json        # Peraia project (create when needed)
└── ...
```

Each config defines:
- Cost line items with exact percentages
- What the cost percentages are calculated on (price_without_costs vs total)
- Payment tranches with percentages and destinations
- Registration fee amount
- Surcharge percentage and breakdown
- Rounding tolerances

**The verification engine MUST load the project config first and use it for all math checks.** Never hardcode percentages or cost structures. The `verify()` function signature is:
```python
def verify(reservation: ReservationData, contract: ContractData, config: ProjectConfig) -> VerificationReport
```

The config also enables a second layer of validation: check that the cost line items and percentages IN the contract match what the project config says they should be. This catches cases where the office manager accidentally uses the wrong template.

## Document Context

### Reservation Agreement (Source of Truth)
- Hebrew-language PDF (sometimes digital, sometimes scanned)
- Key data in paragraph 2: apartment number, floor, area, price without costs, price with costs, registration fee
- Client details on page 2: name, ID, phone, email
- Template is consistent across all projects
- File lives in Google Drive: `Customers / [Project] / [Client Name] /`

### Purchase Contract (Document Under Verification)
- Hebrew-language .docx
- Key data in two appendix tables:
  - **Appendix A (נספח א'):** property details + cost breakdown
  - **Appendix D (נספח ד'):** payment schedule with surcharge calculations
- Client details in contract preamble
- Template is project-specific but consistent within each project

## Key Domain Rules

- All amounts in euros (€)
- **Cost percentages, payment structures, and surcharge rules vary per project** — always load from `projects/<project>.json`
- Cost percentages are typically calculated on price_without_costs (not total) — but check project config
- Registration fee (דמי הרשמה / דמי רצינות) is defined per project (typically €2,000)
- Rounding tolerance: defined per project config (typically ±1€)
- Hebrew word for euros: "אירו" (in reservation), "€" symbol (in contract)

## Skills (Read Before Working)

Before working on extraction logic, READ the relevant skill:
- `skills/hebrew-pdf-extraction.md` — patterns, OCR fallback, number parsing
- `skills/docx-table-extraction.md` — table finding, RTL column order, cost/payment extraction
- `skills/drive-folder-navigation.md` — auth, folder traversal, fuzzy Hebrew name matching

## Implementation Rules

1. **Tables by content, not index.** Find tables by searching for Hebrew label text, never by table[N].
2. **One parse function for numbers.** All euro amounts go through `parse_hebrew_amount()`. No inline parsing.
3. **Extraction before comparison.** Extract both documents into dataclasses FIRST, then compare. Never mix extraction and verification logic.
4. **Log raw values.** In verbose mode, print every extracted field before verification starts.
5. **Fail loud.** If a field can't be extracted, raise an error with the field name and document location. Never silently return None or 0.
6. **Test with fixtures.** Every extraction function must have a test against the sample documents in `tests/fixtures/`.

## Testing

- Sample reservation: `tests/fixtures/טופס_הצטרפות_--_קריופיגי_-דירה_1.pdf`
- Sample contract: `tests/fixtures/נילי_שטרן_ביבר-_הסכם_מאסטר_חלקידיקי_סופי.docx`
- NOTE: These are from DIFFERENT clients/apartments — the verifier should flag mismatches between them
- For all-pass testing, need a matched pair (same client, same apartment)

## Plan / Progress

See `tasks/todo.md` for the full implementation plan with checkboxes.
See `tasks/lessons.md` for accumulated patterns and rules from corrections.

## Commands

```bash
# Full flow with Drive (project config loaded from projects/kriopigi.json)
python -m contract_verifier --project "קריופיגי" --client "נילי שטרן ביבר" --contract path/to/contract.docx

# Local mode (skip Drive, still needs --project for config)
python -m contract_verifier --local --project "קריופיגי" --reservation path/to/reservation.pdf --contract path/to/contract.docx

# List available project configs
python -m contract_verifier --list-projects

# Verbose (show extracted values + loaded config)
python -m contract_verifier --local --project "קריופיגי" --reservation res.pdf --contract contract.docx --verbose

# JSON output
python -m contract_verifier --local --project "קריופיגי" --reservation res.pdf --contract contract.docx --json
```
