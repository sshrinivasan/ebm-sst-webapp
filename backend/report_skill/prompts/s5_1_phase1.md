# Section 5.1 — Phase 1 ESA Review

## Condition

Only generate this section if `phase1_esa.provided` is `true` in `site_facts.json`.
If `false`, omit this section entirely.

## Placeholder

`<INSERT_5_1_START>` / `<INSERT_5_1_END>` — bracket the section content. Op type: `replace_between`.

## Data source

All raw facts below come from `site_facts.json`'s `phase1_esa` block (populated
by the unified extraction pass — see `prompts/site_facts_cache.md`). This
section does **not** re-read the AER Phase 1 ESA PDF — it applies judgment and
writes narrative wording from facts already extracted.

---

## Extraction rules

### Citation
- **Company**: `phase1_esa.company_name` — use verbatim, as printed on the Phase 1 ESA's Professional Assurance Table.
- **Year**: from `phase1_esa.phase1_completed_date` (not any other date field).
- Format: `(CompanyName, YYYY)`

### Spills
- Field: `phase1_esa.spills_releases`
- If **"No"** → bullet: "There were no recorded spills associated with the site or
  nearby pipelines."
- If **"Yes"** → bullet: "Spills/releases were recorded associated with the site.
  Refer to the Phase 1 ESA for details." (do not attempt to summarise)

### Drilling flare pit
- Field: `phase1_esa.infrastructure_flags["Flare Pits"]`
- Also use `phase1_esa.spud_date` and `.final_drill_date`
- If Flare Pits **false** OR drill duration ≤ 2 days → bullet: "A drilling
  flare pit was likely in place but not used, as drilling was completed within
  {N} day(s), with no kicks or upsets."
- If Flare Pits **true** AND drill duration > 2 days → bullet: "A drilling
  flare pit was in place during drilling operations."
- Drill duration = `final_drill_date` − `spud_date` (in days, inclusive).

### Produced water
- Search `phase1_esa.additional_info_text` for any mention of produced water
  volume (m³) and production period.
- If found → bullet: "During production, the well produced {volume} m³ of produced
  water over a {duration}-year period{cessation}."
  - `{cessation}` = " before ceasing operation in {year}" if a cessation year is
    mentioned, otherwise omit.
- If no produced water mentioned → omit this bullet.

### Gas production
- Search `phase1_esa.additional_info_text` for any mention of gas production
  (dry gas, sweet gas, dry sweet gas, etc.) and a production period/duration —
  distinct from produced water above; a well can have one, the other, both, or
  neither.
- If found → bullet: "{Gas type, capitalized, e.g. 'Dry sweet gas'} production
  occurred over a {duration}-year period ({start_year}–{end_year}), which
  typically presents low environmental risk." Only include the "typically
  presents low environmental risk" clause if `additional_info_text` itself
  characterizes the production as low-risk; otherwise state the duration only
  and let the closing paragraph or other bullets carry any risk framing.
- If no gas production mentioned → omit this bullet.
- Produced water and gas production are independent checks — run both, include
  whichever bullet(s) apply (zero, one, or both).

### Pipelines
- Field: `phase1_esa.infrastructure_flags["Pipeline"]`
- If **true** → bullet: "There are pipelines associated with the site."
  - If directions are mentioned in `additional_info_text` → append: ", which head
    {directions} from the well centre."
- If **false** → omit this bullet.

### Surrounding land use / other infrastructure
- Fields: `phase1_esa.land_use_north/_south/_east/_west`
- If all four = Agriculture → bullet: "The area is likely used for
  cattle grazing, which could result in some salt-related impacts at the
  near-surface."
- If mixed land use → bullet: "The surrounding land use is {N: X, S: Y, E: Z,
  W: W}."
- Field: `phase1_esa.receptor_proximities` — Residence, Water Well, Surface water body
  - If all values are ">300m" or "Not Applicable" → bullet: "There are no residences, water
    wells, or surface water bodies within 300 m of the site."
  - If any within 300 m → note the distance.

### Other wellsites / facilities / roads
- Search `phase1_esa.additional_info_text` for any mention of nearby wellsites,
  facilities, municipal roads, or highways.
- If none mentioned → bullet: "There are no other wellsites, facilities,
  municipal roads, or highways near the site."

---

## Closing paragraph

After the bullets, always add this paragraph — it is boilerplate:

> The background borehole locations are shown in Figure XX, overlayed onto a
> post-disturbance aerial photograph. Each background location is at least
> {distance} beyond the area of historical disturbance, with no other known
> sources in proximity.

- `{distance}` — cannot be derived from cached facts. Use `[XX m]` as a
  placeholder for the report author to fill in.
- If any background boreholes are near pipelines or other infrastructure
  (cross-reference the background borehole list in `excel_data.json`'s `section5_data.background_boreholes` with
  pipeline/infrastructure mentions in `phase1_esa.additional_info_text`) →
  append: "Two potential exceptions would be {BH list}, which are in the
  general vicinity of {infrastructure} (Figure XX)."

---

## Output

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_5_1_START>",
  "end_placeholder": "<INSERT_5_1_END>",
  "blocks": [
    {"style": "body", "text": "The Phase 1 ESA was reviewed for potential sources of chloride impact in the outlying areas, and the following was noted {citation}:"},
    {"style": "bullet", "text": "[other wellsites/facilities/roads bullet]"},
    {"style": "bullet", "text": "[spills bullet]"},
    {"style": "bullet", "text": "[flare pit bullet]"},
    {"style": "bullet", "text": "[produced water bullet — omit if not applicable]"},
    {"style": "bullet", "text": "[gas production bullet — omit if not applicable]"},
    {"style": "bullet", "text": "[pipelines bullet — omit if not applicable]"},
    {"style": "bullet", "text": "[land use bullet]"},
    {"style": "bullet", "text": "[receptor proximity bullet — residences/water wells/surface water, omit if not applicable per rule above]"},
    {"style": "body", "text": "[closing paragraph]"}
  ]
}
```

Omit any bullet whose condition above says "omit". Order the bullets as shown.
