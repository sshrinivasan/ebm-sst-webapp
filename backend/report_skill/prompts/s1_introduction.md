# Section 1 "Introduction" Prompt

**Not the same as Section 1.1.** The template has two separate marker pairs
under Section 1: `<INSERT_1_START>`/`_END` sits under the "Introduction"
heading (this file), and `<INSERT_1_1_START>`/`_END` sits under a separate
"Objectives and Scope" heading further down (objectives wording + scope
bullet list — not covered here; needs its own prompt file once content for
it is provided).

## Placeholder
`<INSERT_1_START>` / `<INSERT_1_END>` — brackets the existing example
paragraph in the Word template, under the "Introduction" heading
(`Automation Template_20260924.docx`). Op type: `replace_between`.

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_1_START>",
  "end_placeholder": "<INSERT_1_END>",
  "blocks": [
    {"style": "body", "text": "Facility opening sentence + fieldwork-completed sentence..."}
  ]
}
```

## Content — reuses the Executive Summary's Section 1 facts, do not re-derive

This is the **same information** as the Executive Summary's "Section 1 —
Facility" paragraph (see `prompts/exec_summary.md`) — same client/EBM/ESA/
site-name/surface-location opening sentence, same OWA vs non-OWA variant
rule, same field sources (client name + acronym, site name, site type,
surface location/LSD). Compute that opening sentence once and reuse it
**verbatim** here — the opening sentence in both places must always match
word for word. Do not re-derive the client acronym, site type wording, or
OWA/non-OWA choice independently for this section.

**Site type wording (`[wellsite/compressor station/facility]`) is the same
locked lookup as the Executive Summary's — see `prompts/exec_summary.md`'s
Section 1 note: use `site_facts.json`'s top-level `site_type` field
verbatim, never chosen independently here.

**Difference from the Executive Summary version:** this section does
**not** include the "The purpose of the assessment was to investigate..."
second sentence. Instead, replace that second sentence with a single
fieldwork-completion sentence:

> Fieldwork was completed on [date].

**Date source:** the same "Investigation date groups" input the Executive
Summary's Section 3 already uses (see `prompts/exec_summary.md`'s Inputs
table) — borehole logs' `DRILL DATE` header. Use the **end date of the most
recent investigation date group** this run (if a group is itself a range,
e.g. "November 22–23, 2024", use its end date; if there were multiple
drilling events across different dates, use the latest one). Always format
as a single date "Month D, YYYY" (e.g. "November 19, 2025") — never a range,
even when the underlying drilling event spanned multiple days.

## Full worked example (Canlin, non-OWA, single drilling event Nov 19, 2025)

> Canlin Energy Corporation (Canlin) retained EBM Geoscience Inc. (EBM) to complete a Phase 2 Environmental Site Assessment (ESA) at the Canlin MEDHAT 9-2-14-3 wellsite at surface location 100/09-02-014-03W4M (the site). Fieldwork was completed on November 19, 2025.

## OWA project variant (mirrors the Executive Summary's OWA variant)

> The Orphan Well Association (OWA) retained EBM Geoscience Inc. (EBM) on behalf of [Client] to complete a Phase 2 Environmental Site Assessment (ESA) at the [Site Name] [wellsite/compressor station/facility] at surface location [LSD] (the site). Fieldwork was completed on [date].
