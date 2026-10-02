# Practitioner Information (end-of-run hand-off)

A Claude-authoring guide, run **after** Step 4 (operations applied) and before
the final message. It produces a short hand-off for the practitioner: what to
check, what Claude was unsure about, what could not be found, and what is still
incomplete. It is **not** part of the report — it is saved as a separate file
next to the report, and summarised in the chat reply.

## Why this exists
Some text in the report is Claude's own interpretation, not a data lookup (for
example the Section 5.2 closing paragraph, intake Q18), and some sections leave
placeholders or skip silently. The practitioner should not have to discover
these by reading the whole report. Be specific, cite the section number, and
say *what to do*.

## The four categories (always all four headings, in this order)

1. **Check / verify** — Claude-authored judgment or inference the practitioner
   should confirm. State what Claude concluded and what it rested on. Always
   include: any text written from intake Q18 when the practitioner asked Claude
   to draft it; delineation/"achieved" statements that depend on an override or
   a `no_coverage` direction; any conclusion sentence ("further remediation
   required", "not recommended", etc.) and the rule that produced it.
2. **Uncertain** — places Claude made a call between reasonable options, or
   the data was ambiguous (e.g. which borehole set counts toward a total, which
   sample depth was quoted, a defaulted intake answer, an excluded row class
   such as Unassigned boreholes). Name the choice made and the alternative.
3. **Not found / not available** — facts the skill looked for and could not
   get: missing borehole logs or coordinates, blank log Notes lines, markers
   absent from the template (e.g. Section 8), source-document mismatches
   (Phase 1 ESA LLD/UWI vs borehole logs), any `extraction_flags` from
   `site_facts.json`, any operation or generator line that printed `✗` or
   `⚠` (quote the section and message).
4. **Incomplete** — everything still left for the practitioner to fill:
   every literal placeholder left in the report (scan the final DOCX for
   `XX`, `Figure XX`, `Tables XX`, `[SITE-CONTEXT PLACEHOLDER]`,
   `[PRACTITIONER`, template example text that the skill deliberately leaves
   alone such as the 4.2.1 "FOR T1 with BG" pH bullet), sections skipped, and
   values left blank on purpose (e.g. impact volume when intake Q6 was blank).

## How to build it
1. Re-open the final DOCX and the generator's run log. Do not rely on memory:
   grep the DOCX for the placeholder strings above, and grep the log and the
   apply-operations output for `✗` / `⚠`.
2. Read `site_facts.json`'s `extraction_flags` and `borehole_logs.analysis.review_notes`
   (`judgment_calls`, `log_errors`) and carry over anything still relevant.
3. Compare borehole sets: boreholes with a log but no lab data, and lab data
   but no log.
4. Write each item as one or two sentences: **where** (section number),
   **what**, **what to do**. No generic advice. Omit a category's items only if
   truly none, and then write "None identified." under its heading.
5. Save it with `scripts/write_practitioner_info.py` (below) as
   `Practitioner_Information_<site>.docx` in the same folder as the report.
6. In the chat reply, give the top 3–5 items in a few lines and the file name.
   Do not paste the whole list.

## Input to the script — a JSON file
```json
{
  "site": "08-13-016-01 W4",
  "report": "EBM_Report_08-13_Canlin_20260930.docx",
  "check": ["Section 5.2 closing paragraph: ... (what it rested on; what to confirm)"],
  "uncertain": ["..."],
  "not_found": ["..."],
  "incomplete": ["..."]
}
```
```bash
python3 scripts/write_practitioner_info.py practitioner_info.json "<output_folder>"
```
