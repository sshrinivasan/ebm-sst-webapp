# Section 1.2.1 — Previous Environmental Assessments

## Placeholder (new template naming — no underscores)

`<INSERT_121_START>` / `<INSERT_121_END>` wrap the whole section in
`Automation Template_20260924.docx`. Inside that range the template offers
two alternatives, divided by a literal `OR` paragraph:

1. A fixed no-previous-assessments sentence.
2. A table, one row per previous assessment, columns `Year+Reference` /
   `Summary`. The table has no header row — its example rows are
   placeholder content to be replaced entirely.

Exactly one alternative survives in the final document.

**Outstanding template fix needed before this table variant can be
authored:** unlike the table's other markers, there is currently no
`<INSERT_121_TABLE>` anchor paragraph directly before the table (the table
sits right after the bare `OR` paragraph with nothing in between).
`replace_table_rows`/`delete_table` in `apply_operations.py` both require a
dedicated anchor paragraph immediately before the table they target — add
`<INSERT_121_TABLE>` as its own paragraph, right after `OR` and right
before the table, matching the convention used elsewhere (e.g.
`<INSERT_3_2_SCARG_TABLE>`, `<INSERT_FACILITY_TABLE>`).

---

## This is a reshaping task, not a fresh read

The `Summary` cell for a previous-assessment row needs the kind of detail
shown in the template's own example — e.g. whether drilling mud additives
met compliance option requirements, whether a DWDA or well-centre
investigation is recommended. That detail is captured once, during the
unified extraction pass (Step 1c), in `site_facts.json`'s
`phase1_esa.findings_summary` (and each
`other_previous_assessments[].findings_summary`) — see
`prompts/site_facts_cache.md`'s "Findings summary and APEC/CoPC extraction".
Those fields are already an authored, factual account of what each source
document found, read from the whole document (not just its Conclusions
section).

**Use `findings_summary` as the source for the Summary cell — do not
re-open the PDF.** Your job here is to reshape/reword that cached summary
into the template's own register (a plain narrative paragraph, specific and
factual, matching the style of the template's own example rows) — not to
re-derive the facts from scratch. Do not invent findings that aren't
actually in `findings_summary`; if it seems to be missing detail the table
clearly needs, flag that rather than inventing it.

---

## Data sources

| Input | Source |
|---|---|
| Whether a Phase 1 ESA exists for this site | `site_facts.json`'s `phase1_esa.provided` flag |
| Phase 1 ESA year | `site_facts.json`'s `phase1_esa.phase1_completed_date` (year portion) |
| Phase 1 ESA summary content | `site_facts.json`'s `phase1_esa.findings_summary` (cached, Step 1c) — reshape into the table's register, don't re-read the PDF |
| Any other previous assessments (Phase 2 ESA, EM/geophysical survey, prior soil investigation, etc.) | `site_facts.json`'s `other_previous_assessments[]` array — one cached entry per document (`document_type`, `year`, `findings_summary`), same reshaping rule |
| Short reference name (e.g. "Canlin" in "Canlin, 2026") | The resolved top-level `client_name`'s short name — read `prompts/clients/*.md`'s `## Short Name` section for the matching client file (same lookup as the exec summary's/Section 1's client acronym — see `prompts/exec_summary.md`'s Section 1 note). Do not invent an abbreviation independently. |

Both this table and the Executive Summary's previous-assessments paragraph
draw from the same cached fields — the register differs (this is a full
narrative paragraph per assessment; the exec summary just names each
assessment and pools APECs/CoPCs) but the underlying facts should stay
consistent between them.

---

## Condition

- **No previous assessments** (`phase1_esa.provided` is `false` and
  `other_previous_assessments` is empty) → use the fixed sentence (Option 1
  below).
- **One or more previous assessments** (`phase1_esa.provided` is `true`,
  and/or `other_previous_assessments` has one or more entries) → use the
  table (Option 2 below), one row per assessment — the Phase 1 ESA first if
  present, then each `other_previous_assessments[]` entry — ordered
  chronologically (oldest first).

---

## Option 1 — No previous assessments

Keep the template's existing fixed sentence verbatim (do not rewrite it):

> "The Phase 1 ESA was unavailable for review, and to our knowledge, no other contaminant investigations have been conducted."

Remove the table entirely, the `OR` divider, and the START/END markers.

```json
[
  { "op": "delete_table", "placeholder": "<INSERT_121_TABLE>" },
  { "op": "delete_paragraph", "text": "OR", "after": "<INSERT_121_START>", "before": "<INSERT_121_END>" },
  { "op": "strip_markers", "start_placeholder": "<INSERT_121_START>", "end_placeholder": "<INSERT_121_END>" }
]
```

---

## Option 2 — Table of previous assessments

Write one `[Year+Reference, Summary]` row per previous assessment, sourced
from that assessment's cached `findings_summary`
(`phase1_esa.findings_summary` for the Phase 1 ESA,
`other_previous_assessments[].findings_summary` for each other one).

**First column — two lines in the same cell:**
1. The four-digit year, **bold**.
2. A short reference directly below it, not bold, in the form
   `(ShortName, Year)` — e.g. `(Canlin, 2026)`. `ShortName` is the client's
   short name (see Data sources above); `Year` repeats the same year as
   line 1. Always both lines, even when there's only one row in the table.

The template already shades that column's cell dark green
(`<w:shd w:fill="52796F">`) with white run text on its own example rows —
`replace_table_rows` inherits that formatting (font, size, color)
automatically from the template row it clones, so it doesn't need to be
respecified here. Don't add explicit font/color fields to the operation
JSON for this table; if the rendered output ever comes out wrong, fix it by
checking what's on the template's own row rather than hardcoding values in
the operation.

**Second column:** a plain narrative paragraph (no bullets) reshaping that
assessment's cached summary into the same register as the template's own
example rows — specific and factual, not generic ("the ESA identified some
potential concerns" is too vague; name the actual APEC/compliance
determination found in `findings_summary`).

```json
[
  {
    "op": "replace_table_rows",
    "table_anchor": "<INSERT_121_TABLE>",
    "header_rows": 0,
    "rows": [
      [
        {"lines": [{"text": "2020", "bold": true}, {"text": "(Canlin, 2020)", "bold": false}]},
        "The historical Phase 1 ESA made the following conclusions: ..."
      ]
    ]
  },
  { "op": "delete_paragraph", "text": "The Phase 1 ESA was unavailable for review", "exact": false, "after": "<INSERT_121_START>", "before": "<INSERT_121_END>" },
  { "op": "delete_paragraph", "text": "OR", "after": "<INSERT_121_START>", "before": "<INSERT_121_END>" },
  { "op": "strip_markers", "start_placeholder": "<INSERT_121_START>", "end_placeholder": "<INSERT_121_END>" }
]
```

**Cell formatting is handled by `op_replace_table_rows()` itself**: it
inherits font/size/color from whatever is already on the template's own
row (matching the bold "year" line to the template's bold line, the
non-bold "reference" line to its non-bold line), so this operation's JSON
only ever needs `text`/`bold` per line. An operation-level `"cell_font"`
override and a per-line `"color"` override do exist in
`scripts/apply_operations.py` for a table with no representative template
row to inherit from, but skip them here — this table has one.

`replace_table_rows` must run **before** the `delete_paragraph`/
`strip_markers` calls in this list — it locates the table via the
`<INSERT_121_TABLE>` anchor paragraph and removes that anchor itself once
done, so the anchor has to still exist when it runs.

All operations above (or the three for Option 1) go into the single
combined JSON array passed to `apply_operations.py` alongside every other
section's operations — see `SKILL.md` for how they're all run together.
