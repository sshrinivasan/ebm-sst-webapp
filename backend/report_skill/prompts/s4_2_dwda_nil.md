# Section 4.2 — DWDA NIL FINDINGS subsection

The "no DWDA sump was found" counterpart to `prompts/s4_2_dwda.md` — read
that file first for the gating logic (which of the two subsections gets
content) and the shared Requirement sentence. This file only covers what's
different here: no analytical data exists at all (samples were never
collected), so the whole subsection is a short narrative with three
possible variants depending on whether a geophysical (EM) survey was
considered.

## Placeholder

`<INSERT_42_DWDA_NIL_START>` / `<INSERT_42_DWDA_NIL_END>` —
`replace_between`, **separate** from `<INSERT_42_DWDA_START>`/`_END` and
`<INSERT_42_APECS_START>`/`_END`. The "Drilling Waste Disposal Area – NIL
FINDINGS" `Heading 3` is *inside* this marker pair (same convention as
`prompts/s4_2_dwda.md`'s heading) — when a sump WAS found instead, pass an
**empty `blocks` list** here (removes this whole subsection, heading
included).

## When this subsection applies

See `prompts/s4_2_dwda.md`'s "Which of DWDA / DWDA-NIL applies" section —
gated by intake Q22's "was a sump found?" answer, always asked (a DWDA
search is always performed). This subsection gets content exactly when
Q22's answer is "not found"; `<INSERT_42_DWDA_START>`/`_END` gets
`"blocks": []` in that case.

## Data Source

- `excel_data.json`'s `dwda_requirement_data` key (`wellbore_depth_m`,
  `required_sample_count`) — same object, same Requirement sentence wording
  as `prompts/s4_2_dwda.md` (see that file).
- Intake Q22's exploratory-boreholes answer (count/IDs) plus the
  `site_facts.json` `total_depth_m` lookup for the max-depth clause — same
  mechanism as `prompts/s4_2_dwda.md`'s Exploratory-boreholes sentence,
  reused verbatim here.
- Intake Q22's EM sub-answer — one of **no survey** / **survey done, no
  anomaly** / **survey done, anomaly present but not attributed to a
  DWDA** — picks which of the three variants below to write. See
  `prompts/intake_quiz.md` Q22.

## Citation / reference placeholders — always literal

The three variants below reference a geophysical survey citation (e.g.
"AKS, 2020"), an appendix letter, a figure number, and (variant 3 only) a
region name. None of these are asked in intake or derivable from Excel —
always leave them as literal bracketed placeholders for the practitioner
to fill in from documents this skill doesn't have access to (the
geophysical report, the figure numbering, the site's region). Do not guess
a real company name, year, appendix letter, or region.

## Structure and Wording (three variants)

All three variants share the **Requirement sentence** (identical wording
and computation to `prompts/s4_2_dwda.md`'s Requirement sentence — reuse
it verbatim, including the AER (2014) citation) and the same closing
"search locations shown in Figure [X]" reference. Author the whole
subsection as:

1. **Heading 3** — literal text `"Drilling Waste Disposal Area – NIL
   FINDINGS"`
2. One or two `Normal` paragraphs per the chosen variant below

### Variant A — no EM survey considered
One paragraph:
> "As the wellbore depth was {range}, {required_sample_count word}
> representative samples of the DWDA soil-waste mix zone are required
> (AER, 2014). {N word} boreholes ({exploratory BH list,
> range-compressed}) were advanced to a maximum depth of {max
> total_depth_m} mbgs in the most likely locations for a DWDA based on the
> site layout, landscape position, topography, and historical drilling
> practices. No indications of soil disturbance, drilling waste, or
> contaminant impacts were identified in any of the exploratory boreholes.
> As such, samples were not collected or analyzed for this APEC
> assessment. It was concluded that a DWDA is not present or is of such
> low volume as to pose little to no environmental risk. The DWDA search
> locations are shown in Figure [X]."

### Variant B — EM survey done, no anomaly
Two paragraphs:
> "As the wellbore depth was {range}, {required_sample_count word}
> representative samples of the DWDA soil-waste mix zone are required
> (AER, 2014). {N word} boreholes ({exploratory BH list,
> range-compressed}) were advanced to a maximum depth of {max
> total_depth_m} mbgs at the most likely locations for a DWDA, based on
> the site layout, landscape position, topography, and historical
> drilling practices. Additional consideration was given to the
> geophysical surveys ([SURVEY CITATION — PRACTITIONER TO CONFIRM]), which
> did not show a significant response indicative of a drilling waste
> disposal area (Appendix [X])."

> "No indications of soil disturbance, drilling waste, or contaminant
> impacts were identified in the exploratory boreholes. As such, samples
> were not collected or analyzed for this APEC assessment. It was
> concluded that a DWDA is either absent or of such low volume that it
> poses little to no environmental risk. The DWDA search locations are
> shown in Figure [X]."

### Variant C — EM survey done, anomaly present but not attributed to a DWDA
Two paragraphs:
> "As the wellbore depth was {range}, {required_sample_count word}
> representative samples of the DWDA soil-waste mix zone are required
> (AER, 2014). {N word} boreholes ({exploratory BH list,
> range-compressed}) were advanced to a maximum depth of {max
> total_depth_m} mbgs at the most likely locations for a DWDA based on the
> site layout, landscape position, topography, and historical drilling
> practices. Additional consideration was given to the geophysical
> surveys ([SURVEY CITATION — PRACTITIONER TO CONFIRM]), which did not
> indicate elevated conductivity representative of a drilling waste
> disposal area (Appendix [X]). In the [REGION — PRACTITIONER TO CONFIRM]
> region, drilling waste disposal areas are characterized by [SHALLOW
> IMPACTS NEAR THE WELLBORE — PRACTITIONER TO CONFIRM]."

> "No indications of soil disturbance, drilling waste, or contaminant
> impacts were identified in any of the exploratory boreholes. As such,
> samples were not collected or analyzed for this APEC assessment. It was
> concluded that a DWDA is not present or is of such low volume as to pose
> little to no environmental risk. The DWDA search locations are shown in
> Figure [X]."

Note the small wording differences between variants A/B/C are intentional
(e.g. "in the most likely locations" in A vs. "at the most likely
locations," in B/C; "identified in any of the exploratory boreholes" vs.
"identified in the exploratory boreholes") — they mirror the live
template's own placeholder text exactly, so match them precisely rather
than normalizing to one phrasing.

## Number Formatting
Same as `prompts/s4_2_dwda.md`: numerals throughout, 1 decimal place for
depths.

## Output Format

Same `blocks` JSON / `replace_between` schema, targeting
`<INSERT_42_DWDA_NIL_START>`/`_END`:

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_42_DWDA_NIL_START>",
  "end_placeholder": "<INSERT_42_DWDA_NIL_END>",
  "blocks": [ ... ]
}
```

Author this as its own operation in the same combined JSON array as every
other section's operations (see `SKILL.md`) — never merge it with
`<INSERT_42_DWDA_START>`/`_END`'s operation. As with that file, always
submit an operation for both marker pairs — whichever doesn't apply still
needs its `"blocks": []` operation.
