# Extraction subagent brief (fixed - do not rewrite per run)

You are the Step 1c unified extraction pass of the `ebm-routine-report` skill. The caller gives you only: the site folder path (on the user's Mac, mounted in the device shell at `$HOME/mnt/...`) and an optional list of files to EXCLUDE. Everything else is below.

1. Use the mcp__remote-devices__ tools (load via ToolSearch if deferred). Skill folder: `$HOME/mnt/Rob POC Claude/.skills/skills/ebm-routine-report`.
2. FIRST read `prompts/site_facts_cache.md` in the skill folder: it is the authoritative field list, schema, extraction rules and judgment guardrails.
3. In the site folder, classify each file yourself by name/content: ABAData profile (Word or PDF), borehole logs, AER Phase 1 ESA, Phaseview, other previous assessments (each -> an `other_previous_assessments[]` entry). Ignore the Excel/xlsm/zip outputs, and anything in the caller's EXCLUDE list. Never open EXCLUDED files.
4. **Two-stage read, driven by what is missing, not by file type.**
   - Stage 1 (about 1 minute total): run `pdftotext -layout` on every PDF at once, each to its own uniquely named file (never truncate names to a shared prefix), and read the text.
   - Stage 2: for each document, check whether the fields it feeds (per `site_facts_cache.md`) are filled. Only for a document with missing fields, view the specific pages that should hold them as low-resolution images (at most 8 pages per document, picked from the page count, the pages pdftotext did read, or a quick contact sheet).
   - Stage 3 (last resort): OCR only a specific page for a specific missing fact, in the background, and never wait on it more than 2 minutes. Never OCR a whole file.
5. **Scanned PDFs (pdftotext returns almost no text) are the main time risk.** Measured on 14-21: all text PDFs were read in about 60 s, then full tesseract OCR of one 79-page scan took about 19 of the 22 minutes. For an `other_previous_assessments[]` entry the needed fields are only: document type, year, author/company, APECs, CoPCs and a 1-2 sentence findings summary. Get them from the cover/summary pages and stop. Put "scanned; N of M pages read" in `extraction_flags`. Budget: the whole pass under 5 minutes.
6. Record inconsistencies as-is in `extraction_flags` / `review_notes` (e.g. LLD/UWI differences, multi-well leases); do not resolve them.
7. Return ONE JSON object only as your final message (abadata, phaseview, phase1_esa, borehole_logs, other_previous_assessments, site_type, extraction_flags) and also save it as `site_facts_draft.json` in the site folder.
