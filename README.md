# Contract Verifier

Verify real estate purchase contracts against reservation agreements. Extracts data from both documents, runs 17 deterministic checks, and reports mismatches.

## Setup

### Prerequisites
- Python 3.11+
- Tesseract OCR with Hebrew language support
- Google Cloud project with Drive API enabled (for Drive integration)

### Install Tesseract (macOS)
```bash
brew install tesseract tesseract-lang
```

### Install Tesseract (Ubuntu/Debian)
```bash
sudo apt install tesseract-ocr tesseract-ocr-heb
```

### Install Python dependencies
```bash
cd contract-verifier
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Google Drive Setup (Optional — needed for auto-fetch)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project
3. Enable the **Google Drive API**
4. Go to Credentials → Create OAuth 2.0 Client ID → Desktop application
5. Download the JSON and save it as `~/.contract-verifier/credentials.json`
6. First run will open a browser for authorization

## Usage

### Local mode (both files provided manually)
```bash
python -m contract_verifier \
  --local \
  --reservation path/to/reservation.pdf \
  --contract path/to/contract.docx
```

### With Google Drive (auto-fetch reservation)
```bash
python -m contract_verifier \
  --project "קריופיגי" \
  --client "נילי שטרן ביבר" \
  --contract path/to/contract.docx
```

### Options
- `--verbose` — show raw extracted values before verification
- `--json` — output report as JSON instead of terminal table
- `--local` — skip Google Drive, use local file paths

## What It Checks

**Cross-document (reservation ↔ contract):** apartment number, floor, area, total price, registration fee, project name, client name, client ID.

**Internal math (contract only):** cost line calculations, cost sum, payment percentages sum to 100%, payment base amounts, surcharge calculations, total payments sum.

## Project Structure
```
contract-verifier/
├── src/contract_verifier/
│   ├── main.py              # CLI entry point
│   ├── extract_reservation.py  # PDF → ReservationData
│   ├── extract_contract.py     # DOCX → ContractData
│   ├── verify.py               # 17 deterministic checks
│   ├── report.py               # Terminal + JSON output
│   ├── drive_fetch.py          # Google Drive integration
│   └── models.py               # Shared dataclasses
├── tests/
├── tasks/                    # Implementation plan & lessons
├── skills/                   # Reusable extraction patterns
├── CLAUDE.md                 # Project context for Claude Code
└── pyproject.toml
```
