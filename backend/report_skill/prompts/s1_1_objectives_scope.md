# Section 1.1 "Objectives and Scope" Prompt

**Not the same as Section 1.** The template has two separate marker pairs
under Section 1: `<INSERT_1_START>`/`_END` sits under the "Introduction"
heading (see `prompts/s1_introduction.md`), and `<INSERT_1_1_START>`/`_END`
sits under this section's own "Objectives and Scope" heading, further down.

## Placeholder
`<INSERT_1_1_START>` / `<INSERT_1_1_END>` — brackets the existing example
content in the Word template, under the "Objectives and Scope" heading
(`Automation Template_20260924.docx`). Op type: `replace_between`.

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_1_1_START>",
  "end_placeholder": "<INSERT_1_1_END>",
  "blocks": [
    {"style": "body", "text": "<objective sentence — one of the two variants below>"},
    {"style": "body", "text": "The scope of work included the following:"},
    {"style": "bullet", "text": "Review the historical investigation data."},
    {"style": "bullet", "text": "Evaluate background conditions."},
    {"style": "bullet", "text": "Evaluate each APEC for the associated CoPCs."},
    {"style": "bullet", "text": "Develop a conceptual site model (CSM)."},
    {"style": "bullet", "text": "Prepare a summary report to current regulatory standards."}
  ]
}
```

## Objective sentence — two variants, chosen by intake (not derivable from data)

There is no field in `site_facts.json`, the Excel workbook, or any source
PDF that tells us which of these two report types this run is. **Always
ask** — see `prompts/intake_quiz.md` Q21.

**"Presence/Absence P2"** — use when the answer is a lighter-touch
presence/absence-style Phase 2 assessment:
> The objective of the assessment was to investigate each area of potential environmental concern (APEC) for the presence or absence of the contaminants of potential concern (CoPCs).

**"OR-Standard Tier 1 P1"** — use when the answer is a full/standard
routine report (characterization + delineation + closure evaluation):
> The objectives of the assessment were to characterize soil quality at the identified areas of potential environmental concern (APECs), delineate the extent of impacts for the relevant contaminants of potential concern (CoPCs), and evaluate the site for closure.

Use the chosen sentence verbatim — do not blend or paraphrase the two
variants.

## Scope of work — always the same, regardless of which variant was chosen

Both variants are followed by the identical, fixed scope-of-work paragraph
and bullet list below — this part never changes and is not a per-run
choice:

> The scope of work included the following:
> - Review the historical investigation data.
> - Evaluate background conditions.
> - Evaluate each APEC for the associated CoPCs.
> - Develop a conceptual site model (CSM).
> - Prepare a summary report to current regulatory standards.
