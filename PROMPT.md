# Claude Code Starter Prompt

## Copy everything below this line and paste it into Claude Code:

---

Read CLAUDE.md to understand the project context, then read tasks/todo.md for the full implementation plan.

This is a contract verification tool for a real estate company. It extracts data from two Hebrew documents (a reservation agreement PDF and a purchase contract DOCX), compares them deterministically, and reports mismatches.

Before writing any code:

1. Read all three skills in the `skills/` folder — they contain extraction patterns, known pitfalls, and tested code snippets that you must use.
2. Read `tasks/checks-reference.md` — it has the complete verification formula table and pre-verified math from the sample documents.
3. Read `tasks/critical-finding-cost-base.md` — it documents a non-obvious math rule about how cost percentages are calculated.
4. Check that sample fixtures exist in `tests/fixtures/`.
5. Read `projects/kriopigi.json` — this is the per-project config that defines cost structures, payment schedules, and surcharge rules. Each project has its own config file. The verification engine loads the right config and uses it for all math checks. Never hardcode financial parameters.

Then start executing the plan from Phase 0:

- Set up the virtual environment and install all dependencies from pyproject.toml
- Verify Tesseract is available with Hebrew support
- Create the full src/contract_verifier/ package structure

After Phase 0 is done, continue through Phase 1 (models), Phase 1.5 (project config loader), Phase 2 (reservation PDF extraction), Phase 3 (contract DOCX extraction), Phase 4 (verification engine — must use ProjectConfig for all math), Phase 5 (report output), Phase 6 (Google Drive integration), and Phase 7 (CLI entry point).

At each phase:
- Mark completed items in tasks/todo.md
- Test against the sample fixtures in tests/fixtures/
- If anything fails or surprises you, document it in tasks/lessons.md before moving on
- Run the test suite after each phase to confirm nothing is broken

After Phase 7, run the full end-to-end pipeline in local mode using both sample fixtures. The reservation is apartment 1 and the contract is apartment 6 — they are deliberately mismatched, so the verifier MUST catch and flag the differences. That is the acceptance test.

Work autonomously through all phases. Do not stop to ask me questions unless you hit a blocker that genuinely cannot be resolved from the project files. Use subagents for research tasks like testing OCR accuracy or exploring python-docx table structure.
