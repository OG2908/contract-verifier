# Lessons Learned — Contract Verifier

## Document Extraction

### Hebrew Text Processing
- **Pattern:** Hebrew text in PDFs often has reversed character order when extracted with basic tools. Always test `pdftotext` output visually before writing regex.
- **Rule:** After extracting Hebrew text, log the raw string before regex matching. If regex fails, the problem is almost always character order or invisible Unicode characters, not the pattern itself.

### Number Parsing
- **Pattern:** Euro amounts in Hebrew documents use inconsistent formatting: sometimes `€122,224`, sometimes `122,224 אירו`, sometimes `122.224` (European decimal notation).
- **Rule:** Always strip currency symbols, whitespace, and commas before parsing. Build one `parse_amount()` function and route ALL number extraction through it. Never inline number parsing.

### PDF OCR Fallback
- **Pattern:** Some reservation PDFs are scanned, some are digital. You can't know until you try text extraction.
- **Rule:** Always try text extraction first. Only fallback to OCR if extracted text length < 50 characters for a page that should have content. Log which path was taken.

## python-docx Tables
- **Pattern:** Table cell positions can shift between templates. A cost line that's in row 6 in one contract might be in row 7 in another.
- **Rule:** NEVER use hardcoded row indices. Always search for rows by matching label text in the first column. Use `cell.text.strip()` for comparison.

## Verification Logic
- **Pattern:** Rounding differences between the reservation agreement and contract are normal (±1€).
- **Rule:** Use `math.isclose(a, b, abs_tol=1.0)` for all Euro amount comparisons. Use exact match for percentages and integers.

## Google Drive
- **Pattern:** Hebrew folder names in Google Drive API queries need proper encoding.
- **Rule:** Use `name = 'folder_name'` in Drive API queries, not path-based search. Navigate folder by folder.

---

## Contract Template Structure
- **Finding:** The Kriopigi contract template does NOT contain individual cost line items with amounts. Only the total costs percentage (8.5%) appears in Appendix A, Row 5. Individual cost amounts must be computed during verification using config percentages × base price.
- **Rule:** Don't assume all contract templates will have cost line breakdowns. The `ContractData.cost_lines` field may be empty. The verification engine computes expected amounts from `ProjectConfig.expected_cost_lines`.

## Client Details in Reservation PDF
- **Finding:** In the sample reservation, client details (name, ID, phone, email) appear as free text lines AFTER the bank details section, not in labeled key-value rows. The labels ("שם ושם משפחה:", "מס' ת.ז:") appear earlier but their values are in a different section.
- **Rule:** Extract client details by finding lines after "סיבת העברה" — name is first line, ID is second line.

## Process Lessons

_(Add entries here after any correction from the user)_

- 2026-03-26: Contract project name includes region ("קריופיגי-חלקידיקי") while reservation has just "קריופיגי" → use 'contains' matching for project name comparison
- 2026-03-26: **pypdf strips whitespace unpredictably in Hebrew PDFs.** Apartment 1 PDF produces `דירה מספר1` (space after דירה, no space before digit). Apartment 6 PDF produces `דירה6` (no space at all, no "מספר"). Never assume whitespace exists between Hebrew words and numbers in pypdf output. Use `\s*` (zero or more) instead of `\s+` (one or more) around Hebrew-to-digit boundaries. The working pattern is `r'דירה\s*(?:מספר\s*)?(\d+)'`.
- 2026-03-26: **Floor field may have trailing punctuation.** pypdf extracts `קרקע,` with a trailing comma from some PDFs. Use `[^\s,]+` instead of `\S+` in the floor regex to exclude commas.
- 2026-03-26: **Apartment number is a string, not an integer.** Real-world apartment identifiers include "A06", "B12", "12א" etc. The regex must require at least one digit but allow optional letter prefix/suffix: `r'דירה\s*(?:מספר\s*)?([A-Za-z]?\d+[A-Za-z\u0590-\u05FF]?)'`. Do NOT use a broad Hebrew character class in the capture group or it will match Hebrew words following "דירה" in unrelated contexts.
- 2026-03-26: **Client ID was removed from the data model.** Not needed for verification — only client name is compared cross-document.
