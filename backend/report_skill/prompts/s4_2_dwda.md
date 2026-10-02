# Section 4.2 — DWDA (Drilling Waste Disposal Area) subsection

A special case of the per-APEC reporting in `prompts/s4_2_2_apecs.md` —
read that file first, since the Summary of Results bullets here reuse its
wording rules verbatim. This file covers the "a DWDA sump was found"
outcome; the "no DWDA sump was found" outcome (a separate, mutually
exclusive marker pair) is `prompts/s4_2_dwda_nil.md` — read both together,
since exactly one of the two subsections gets real content and the other
gets emptied out.

## Placeholder

`<INSERT_42_DWDA_START>` / `<INSERT_42_DWDA_END>` — `replace_between`,
**separate** from `<INSERT_42_APECS_START>`/`_END` and from
`<INSERT_42_DWDA_NIL_START>`/`_END`. The "Drilling Waste Disposal Area"
`Heading 3` is *inside* this marker pair in the live template (unlike the
generic APEC section's heading, which the operation itself supplies) — so
when this outcome doesn't apply, pass an **empty `blocks` list**:
`replace_between` still removes everything between the markers (including
that heading), which is exactly "remove the whole subsection" with no
separate delete operation needed.

## Which of DWDA / DWDA-NIL applies

Ask intake Q22 (see `prompts/intake_quiz.md`) — it asks directly whether a
DWDA/soil waste-mix zone was actually identified, since nothing in the
Excel data by itself distinguishes "no DWDA search was done" from
"searched, found nothing" when there's no DWDA-tagged data. Per standing
decision, a DWDA search is always performed at every site, so Q22 is
always asked (never skipped).

- Q22 answer **"sump found"** → this file's subsection gets full content
  (below); `<INSERT_42_DWDA_NIL_START>`/`_END` gets `"blocks": []`. In this
  case `excel_data.json`'s `dwda_data` key (Step 2) should be non-`null` —
  cross-check, since a "found" answer with a `null` payload means the Excel
  data and the intake answer disagree and is worth flagging.
- Q22 answer **"sump not found"** → this file's subsection gets
  `"blocks": []`; `prompts/s4_2_dwda_nil.md`'s subsection gets full content
  instead (`dwda_data` should be `null` in this case).

## Data Source

Read `excel_data.json` (written by Step 2 to `<output_folder>` alongside
the partial DOCX) and take its `dwda_data` key — `null` when no sump was
found (see above). It has the exact same shape as one entry in
`excel_data.json`'s `ec_sar_data` list (see
`prompts/s4_2_2_apecs.md`'s field reference — `sample_ids`,
`ec_categories`, `sar_categories`, `ec_exceedances`, `sar_exceedances`,
`ph_exceedances`, `chloride_mg_l`/`chloride_mg_kg`,
`chloride_vertical_delineation`, `non_salinity_exceedances`, etc. — all
computed by the same shared `_build_apec_payload_entry()` helper), plus
these DWDA-only fields:

```json
{
  "area": "DWDA",
  "...": "... same fields as any other APEC entry ...",
  "wellbore_depth_m": 571.0,
  "required_sample_count": 3,
  "parameter_panel": ["Salinity", "Tier 1 regulated metals"],
  "characterization_boreholes": ["BH26-05", "BH26-06", "BH26-07"],
  "delineation_boreholes": ["BH26-08", "BH26-09"]
}
```

Also see `excel_data.json`'s `dwda_requirement_data` key — a small object
present *unconditionally* (whether or not a sump was found), with just
`wellbore_depth_m`/`required_sample_count`. It's what feeds the
Requirement sentence below (and `prompts/s4_2_dwda_nil.md`'s identical
sentence) — use it rather than `dwda_data`'s copies of the same two
fields, since those are only present when a sump was found.

- `wellbore_depth_m` — parsed from `site_facts.json`'s
  `abadata.wellbore_depth` (e.g. `"571 m"` → `571.0`). `null` if that field
  is missing or unparseable.
- `required_sample_count` — the AER (2014) required number of
  representative soil-waste-mix-zone samples, computed from
  `wellbore_depth_m`: **< 1500 m → 3**, **1500–2500 m → 4**,
  **> 2500 m → 5**. `null` if `wellbore_depth_m` is `null` — in that case,
  leave the requirement sentence's count as a literal placeholder ("XX
  representative samples") rather than guessing.
- `parameter_panel` — unlike every other APEC (whose panel list comes from
  its own single `Borehole Rationale` row), DWDA's panel comes
  specifically from the **characterization** row (`Borehole Rationale`'s
  APEC column value starting with `"DWDA-Char"`, e.g. `"DWDA-Char"` or
  `"DWDA-Characterization"` — matched case-insensitively). `null` if no
  such row exists — leave the panel bullets as a manual placeholder in
  that case, same rule as any other APEC with no matching row.
- `characterization_boreholes` / `delineation_boreholes` — the raw
  borehole-ID lists from the `"DWDA-Char..."` and `"DWDA-Delin..."` (e.g.
  `"DWDA-Delin"` / `"DWDA-Delineation"`) `Borehole Rationale` rows
  respectively. `[]` if a group's row isn't present — omit that group's
  clause from the sentence below rather than writing an empty list.

**Detection note**: in real workbooks the DWDA characterization and
delineation samples are themselves tagged with two *different* APEC
values in the data sheets — `"DWDA-Char"` / `"DWDA-Delineation"`, not a
plain `"DWDA"` (confirmed against an actual site workbook). The generator
script folds any APEC value starting with `"dwda"` (case-insensitive)
into one merged `"DWDA"` bucket before computing the `dwda_data` payload —
so its EC/SAR categories, chloride ranges, and exceedances already span
both groups' samples together. Don't re-derive this from a literal
`"DWDA"` string match anywhere else; go by `excel_data.json`'s `dwda_data`
key.

## What's NOT derivable — ask the user (intake Q22)

The **exploratory** boreholes — the round of drilling advanced first, at
the most likely DWDA location based on site layout, landscape position,
topography, and historical drilling practices, *before* the soil
waste-mix zone (SWMZ) was actually found — are a separate, earlier round
of drilling from the characterization/delineation boreholes above, and
nothing in the Excel data or `site_facts.json` identifies them. Ask
intake Q22 for exploratory borehole count/IDs, then look up each ID's
`total_depth_m` in `site_facts.json`'s `borehole_logs.boreholes[]` and
take the max — see `prompts/intake_quiz.md` Q22 for the exact question and
lookup steps.

The waste-mix-zone identification bullet's depth range is **not** in this
category — see step 8 above. It IS derivable, from the `Borehole
Characteristics` sheet's `Top of Impact`/`Bottom of Impact` columns for the
characterization borehole — now computed automatically into
`excel_data.json`'s `dwda_data.characterization_impact_depth_ranges`
(`[{"borehole_id", "top_of_impact_m", "bottom_of_impact_m"}, ...]`, one
entry per characterization borehole) by `_dwda_impact_depth_range()`. A
previous version of this file wrongly claimed this was a field/visual
observation with no analytical source; always check the actual Excel
sheet before writing off a field as "not derivable" — don't repeat a
claim like that without checking it against real data first.

## Structure

1. **Heading 3** — literal text `"Drilling Waste Disposal Area"` (not
   auto-derived from Excel like the generic APECs — DWDA doesn't have a
   site-specific area name)
2. **Requirement sentence** (`Normal`) — see wording below
3. **Exploratory-boreholes sentence** (`Normal`) — see wording below
   (intake Q22-sourced)
4. **Characterization/delineation-boreholes sentence** (`Normal`) — see
   wording below (computed from `characterization_boreholes`/
   `delineation_boreholes`)
5. **Panel lead-in** (`Normal`): "Per the Phase 1 Compliance Options, each
   characterization sample was analyzed for the following:"
6. **Parameter panel bullets** (`Normal`, one paragraph per entry — the
   live template renders this list as plain `Normal` paragraphs, not the
   `Bullets` style, despite reading as a bulleted list) — one per entry in
   `parameter_panel`
7. **"Summary of Results"** — `Small Titles` style
8. **Waste-mix-zone identification bullet** (`Bullets`): "The soil waste
   mix zone was identified in {borehole} ({depth range} mbgs), …" —
   **the borehole is `characterization_boreholes` (already computed,
   never re-ask or re-placeholder it — it was already stated one sentence
   earlier in step 4, so repeating it as a placeholder is both wrong and
   redundant).** The depth range **is derivable**: the `Borehole
   Characteristics` sheet's `Top of Impact`/`Bottom of Impact` columns for
   that borehole give exactly this range (e.g. BH24-5: Top of Impact 1.25,
   Bottom of Impact 7.5 -> "1.25 to 7.5 mbgs") — this was wrongly documented
   as "always placeholder, a field/visual observation, never computed" in
   an earlier version of this file; that was incorrect, caught only by
   manually checking the Excel sheet, not because the underlying claim was
   ever verified. Only fall back to a literal placeholder if the
   characterization borehole has no `Top of Impact`/`Bottom of Impact`
   values in that sheet (e.g. row present but those two cells blank).
9. **EC/SAR/chloride/non-salinity/compliance/delineation bullets** — same
   wording rules as `prompts/s4_2_2_apecs.md`, computed from
   `dwda_data`'s shared fields exactly as for any other APEC
10. **Naturally-occurring justification block(s)** — same rule as
    `prompts/s4_2_2_apecs.md`: always placeholder, only when
    `justified == "Yes"` on an EC/SAR/pH exceedance

## Wording Rules (DWDA-specific)

### Requirement sentence
"As the wellbore depth was {less than 1,500 m | between 1,500 and 2,500 m |
greater than 2,500 m}, {required_sample_count word} representative samples
of the DWDA soil-waste mix zone (SWMZ) are required (AER, 2014)." — pick
the depth-range clause to match whichever threshold produced
`required_sample_count` (from `excel_data.json`'s `dwda_requirement_data` key).
Introduce the "SWMZ" abbreviation here; use "SWMZ" in every subsequent
reference within this subsection. If `required_sample_count` is `null`,
use "XX representative samples" and "the wellbore depth" (no range clause)
as a literal placeholder rather than guessing.

### Exploratory-boreholes sentence
"{N word} exploratory boreholes ({exploratory BH list, range-compressed})
were advanced to a maximum depth of {max total_depth_m across those
boreholes, from site_facts.json} mbgs at the most likely locations for a
DWDA, based on the site layout, landscape position, topography, and
historical drilling practices." Use intake Q22's answer for the borehole
list; use the range-compression convention from
`prompts/s4_2_2_apecs.md`/Section 4.1 (contiguous numeric ID ranges as "X
to Y"). If the depth lookup can't resolve for every exploratory borehole,
leave "X mbgs" as a literal placeholder rather than guessing.

### Characterization/delineation-boreholes sentence
"The SWMZ was identified and characterized in {N word} borehole(s)
({characterization_boreholes, range-compressed}){ and further delineated
in {N word} borehole(s) ({delineation_boreholes, range-compressed}), if
`delineation_boreholes` is non-empty}." — drop the "and further
delineated..." clause entirely if `delineation_boreholes` is `[]` (no
separate delineation boreholes were advanced). If `characterization_boreholes`
is also `[]` (no matching `"DWDA-Char..."` row found), leave this whole
sentence as a literal placeholder ("The SWMZ was identified and
characterized in [BOREHOLE(S) — PRACTITIONER TO CONFIRM]...") rather than
guessing which boreholes were involved.

### Panel lead-in
Always the literal sentence: "Per the Phase 1 Compliance Options, each
characterization sample was analyzed for the following:" — followed by the
`parameter_panel` list. If `parameter_panel` is `null` (no matching
`"DWDA-Char..."` row), leave the panel list as a manual placeholder, same
as any other APEC with no matching `Borehole Rationale` row.

## Number Formatting
Same as `prompts/s4_2_2_apecs.md`: numerals throughout (project-wide
"always numeral" rule), 1 decimal place for depths.

## Output Format

Same `blocks` JSON / `replace_between` schema as
`prompts/s4_2_2_apecs.md`, targeting `<INSERT_42_DWDA_START>`/`_END`
instead:

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_42_DWDA_START>",
  "end_placeholder": "<INSERT_42_DWDA_END>",
  "blocks": [ ... ]
}
```

Author this as its own operation in the same combined JSON array as every
other section's operations (see `SKILL.md`) — do not merge it into the
`<INSERT_42_APECS_START>`/`_END` operation or into
`<INSERT_42_DWDA_NIL_START>`/`_END`'s operation, since all three are
separate marker pairs in the template. Always submit an operation for
*both* `<INSERT_42_DWDA_START>`/`_END` and
`<INSERT_42_DWDA_NIL_START>`/`_END` — whichever one doesn't apply still
needs its `"blocks": []` operation to remove its (unused) heading and
placeholder text.
