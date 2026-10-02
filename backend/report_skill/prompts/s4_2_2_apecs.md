# Section 4.2 (4.2.2 onwards) — Per-APEC Reporting

Covers every non-background area of potential environmental concern
(APEC). Section 4.2.1 (Background) is handled separately and
deterministically by `generate_section4_2_1_background()` — do not
duplicate it here.

## Placeholder

`<INSERT_42_APECS_START>` / `<INSERT_42_APECS_END>` — `replace_between`,
one operation covering **every** non-background area, concatenated in
Excel row order (same order `excel_data.json`'s `ec_sar_data` list holds
them in).

## Data Source

Run the generator script (Step 2), then read `excel_data.json` (written to
`<output_folder>` alongside the partial DOCX) and take its `ec_sar_data`
key. Each entry is one non-background APEC, already carrying the mechanical
numbers pre-computed in Python (`generate_ebm_report.py`'s per-APEC payload
builder, right after `generate_section4_2_1_background()` is called in
`main()`). Read the file directly — the same values are also printed to
stdout as `EC_SAR_DATA_FOR_CLAUDE` for visibility in the run log, but that's
not the source to parse from:

```json
{
  "area": "Well Centre - Clean",
  "sample_ids": ["BH26-01", "BH26-02"],
  "num_samples": 2,
  "parameter_panel": ["Salinity", "PHCs", "Tier 1 regulated metals"],
  "ec_categories": ["Good"],
  "sar_categories": ["Good"],
  "ec_exceedances": [ {"sample_id": ..., "depth_m": ..., "value": ..., "justified": "Yes"|"No", "justification_reason": "Naturally Occurring"|null} ],
  "sar_exceedances": [ ... same shape ... ],
  "ph_exceedances": [ ... same shape ... ],
  "chloride_mg_l": {"min": 4.9, "max": 5.7},
  "chloride_mg_kg": {"min": null, "max": null},
  "chloride_guideline_mg_l": 100.0,
  "background_chloride_mg_kg_max": 79,
  "chloride_vertical_delineation": [
    {"sample_id": "BH23-02", "max_chloride_mg_l": 300, "deepest_depth_m": 5.0, "deepest_chloride_mg_l": 40, "vertical_closure_achieved": true}
  ],
  "non_salinity_exceedances": [
    {"parameter": "PHC F2-F4", "chemical_group": "PHC", "sample_id": ..., "depth_m": ..., "value": ..., "justified": ..., "justification_reason": ...}
  ]
}
```

Notes on where this comes from / what to trust:
- `parameter_panel` comes from the `Borehole Rationale` sheet's own
  `Salinity`/`Metals`/`PHC`/`PAH`/`Other` Yes/No columns for this APEC —
  the same sheet Section 4.1's table uses, so the two sections always
  agree.
- `ec_exceedances`/`sar_exceedances`/`ph_exceedances`/
  `non_salinity_exceedances` are only the rows from `Tier 1 Exceedances`
  that have that sheet's own `APEC` column (normalised to `Comments`) equal
  to this area. That column is the same underlying data as `EC & SAR
  Rating Categories`'s APEC column — verified directly against a real
  export (0 mismatches across every Sample ID present in both sheets) — so
  there's no cross-sheet lookup needed. Rows where it's `"-"` mean the
  borehole is genuinely marked `Unassigned` in `Borehole Rationale` (no
  area yet), not a data-quality problem, and are excluded the same way an
  unassigned borehole would be excluded from any per-area section.
- `chloride_vertical_delineation` is pre-computed from the full chloride
  depth series in `EC & SAR Rating Categories` for every borehole with at
  least one chloride reading above `chloride_guideline_mg_l` (100 mg/L):
  `vertical_closure_achieved: true` means that borehole's **deepest sampled
  depth** is back below the guideline; `false` means it's still exceeding
  there (residual concentration). The list is sorted worst-case-first (by
  `max_chloride_mg_l` descending).
- **Not derivable from data — do not compute, always leave as a manual
  placeholder** (per standing decision on this section):
  - the site-context clause in the intro paragraph ("near the former
    wellhead", "within the surface staining area observed during the
    Phase 1 ESA", etc.) — the payload has no field for this;
  - the maximum drilled depth per area's boreholes (cross-reference this
    area's `sample_ids` against `site_facts.json`'s
    `borehole_logs.boreholes[].total_depth_m`, and take the max; if that
    lookup can't resolve for every borehole in the area, leave `X mbgs`
    literal placeholder text rather than guessing);
  - any "naturally occurring" justification narrative (chemistry source,
    background comparison, root-zone depth, risk conclusion) — see below.

## Placeholder for Section Numbering

Do **not** type "4.2.2", "4.2.3", etc. into the heading text. The
template's `Heading 3` style auto-numbers sections; just set the
paragraph text to the area name exactly as it appears in Excel (e.g.
`"Well Centre - Clean"`), same as the live template's own example
headings.

## Structure (repeat for every area, in Excel row order)

1. **Heading 3** — area name exactly as in Excel (no manual numbering)
2. **Intro paragraph** (`Normal` style): "{N word} borehole(s) ({BH list})
   were advanced [SITE-CONTEXT PLACEHOLDER] to a maximum depth of {X or
   placeholder} mbgs. {N} sample(s) were analyzed for some or all of the
   following:"
3. **Parameter panel bullets** (`Bullets` style) — one per entry in
   `parameter_panel`
4. **"Summary of Results"** — `Small Titles` style (**not** bold body
   text — this differs from how 4.2.1 was implemented; use `Small Titles`
   here since that's what the live template's own heading uses)
5. **pH bullet** (`Bullets`) — only if `ph_exceedances` is non-empty (see
   wording below)
6. **EC/SAR bullet(s)** (`Bullets`) — see wording rules
7. **Chloride bullet** (`Bullets`) — see wording rules
8. **Non-salinity exceedance bullets** (`Bullets`) — one per parameter in
   `non_salinity_exceedances`, grouped by `parameter`
9. **Compliance bullet** (`Bullets`) — "All other parameters complied
   with Tier 1." — only if any exceedance bullet exists above
10. **Chloride vertical delineation bullet(s)** (`Bullets`) — only if
    `chloride_vertical_delineation` is non-empty; see wording rules
11. **Naturally-occurring justification block(s)** — only when an
    EC/SAR/pH exceedance has `justified: "Yes"` — always placeholder
    text, see below

## Wording Rules

### EC/SAR combined bullet
If `ec_categories == sar_categories`, both are a single category, AND
both `ec_exceedances` and `sar_exceedances` are empty:
"Both EC and SAR were in the **{Category}** soil rating category, with
no SCARG exceedances."

### EC bullet (when not combined)
- No exceedances, single category: "EC values were within the
  **{Category}** soil rating category, with no SCARG exceedances."
- No exceedances, multiple categories: "EC values ranged from the
  **{Lowest}** to **{Highest}** soil rating categories, with no SCARG
  exceedances."
- With exceedances (`len(ec_exceedances)` = N), single category: "EC
  values were within the **{Category}** soil rating category, with {N
  word} SCARG exceedance(s) ({sample_id} at {depth_m} m, ... — join all
  N)."
- With exceedances, multiple categories: "EC values ranged from the
  **{Lowest}** to **{Highest}** soil rating categories, with {N word}
  SCARG exceedance(s) ({sample_id} at {depth_m} m, ...)."

### SAR bullet
Same rules as EC, substituting `sar_categories`/`sar_exceedances`, and
keep the existing "SCARG soil rating category" wording (singular
"category" even for a range — matches the live template's own SAR
examples, unlike the EC bullet's plural "categories").

### pH bullet
- One sample: "The soil pH value in one sample ({sample_id}, {depth_m} m)
  exceeded the guideline range of 6.0–8.5, with a value of {value}."
- Multiple: "The soil pH value in {N word} samples ({sample_id} at
  {depth_m} m, ...) exceeded the guideline range of 6.0–8.5, with values
  of {value1}, {value2}, ...."

### Chloride bullet
- No values above `chloride_guideline_mg_l` anywhere in the area: "The
  chloride concentration was {value} mg/L ({value} mg/kg)." (single
  value) or "Chloride concentrations ranged from {min} to {max} mg/L
  ({min} to {max} mg/kg)." (range) — same as the existing 4.2.1 rule.
- At least one exceeding value: append to the range/single sentence:
  "...and exceeded the {chloride_guideline_mg_l:g} mg/L delineation
  guideline at borehole(s) {sample_id list} ({depth_m list} mbgs)." —
  list every borehole/depth from `chloride_vertical_delineation`.

### Chloride vertical delineation bullet(s)
Split `chloride_vertical_delineation` into `achieved = [d for d if
vertical_closure_achieved]` and `not_achieved = [d for d if not
vertical_closure_achieved]` (both already worst-case-first).

- `not_achieved` empty, one entry in `achieved`: "Vertical closure to
  {guideline:g} mg/L for chloride was achieved at the worst-case borehole
  ({sample_id}) at {deepest_depth_m} mbgs." — optionally use the "...100
  mg/L chloride or background chloride concentration of {XX} mg/kg..."
  variant (substitute `background_chloride_mg_kg_max` for XX) when the
  guideline being tested against is ambiguous between the flat 100 mg/L
  screening value and the site's own background chloride — otherwise
  default to the plainer "100 mg/L for chloride" wording.
- `not_achieved` empty, multiple entries in `achieved`: "Vertical closure
  to {guideline:g} mg/L for chloride was achieved at {sample_id_1} and
  {sample_id_2}[, and {sample_id_3}, ...] at {depth_1}, {depth_2}[, and
  {depth_3}, ...] mbgs, respectively."
- `achieved` non-empty and `not_achieved` non-empty: "Vertical closure to
  {guideline:g} mg/L for chloride was achieved at {achieved sample_id
  list} at {achieved depth list} mbgs but not at the {N word}
  worst-case location(s). At {not_achieved sample_id list}, residual
  chloride concentration(s) of {not_achieved deepest_chloride_mg_l list}
  mg/L were identified at {not_achieved deepest_depth_m list} mbgs."
- `achieved` empty, `not_achieved` non-empty (all failed): "Vertical
  [and lateral, if this area's own context says lateral delineation was
  also attempted — otherwise just vertical] delineation for chloride was
  not achieved[, although vertical delineation of the SCARG exceedances
  was achieved at {X} m — PLACEHOLDER if this nuance applies]."

Always double-check depth/value lists against the actual
`chloride_vertical_delineation` entries — never invent a borehole ID or
depth that isn't in the payload.

### Non-salinity exceedance bullets (PHC/Metals/Methanol/PAH)
Group `non_salinity_exceedances` by `parameter`. For each group:
- One sample: "One sample, {sample_id} ({depth_m} m), exceeded for
  {parameter}. [Vertical delineation PLACEHOLDER — was achieved at {X}
  mbgs, and lateral delineation was PLACEHOLDER.]"
- Multiple: "{N word} samples exceeded for {parameter} (reference
  boreholes/depths: {list})."

The delineation-status clause for these parameters is **not** computed —
the payload has no depth-series data for PHC/Metals/Methanol the way it
does for chloride. Leave it as literal placeholder text unless/until a
depth-series field is added for these parameters too (flag this gap
rather than guessing "achieved"/"not achieved").

### Compliance bullet
"All other parameters complied with Tier 1." — add whenever any bullet
above (pH, EC, SAR, chloride, or non-salinity) reported an exceedance.
Skip entirely if the area had zero exceedances anywhere.

### Naturally-occurring justification block — ALWAYS PLACEHOLDER
Whenever an entry in `ec_exceedances`, `sar_exceedances`, or
`ph_exceedances` has `justified == "Yes"`, insert (as its own `Bullets`
block, after the compliance bullet) a fill-in template like:

```
For the {EC|SAR} exceedance at {sample_id} ({depth_m} m):
  - The chloride concentration of {co-located chloride value if known,
    else "XX"} mg/L is comparable to background conditions. [PRACTITIONER
    TO CONFIRM/EDIT]
  - The {EC|SAR} value is associated with elevated levels of
    naturally occurring [PRACTITIONER TO SPECIFY — e.g. sulphate /
    sodium sulphate ion imbalance].
  - The sample location is [below/within] the shallow root zone at
    {depth_m} mbgs. [PRACTITIONER TO CONFIRM]
  - Based on the above, the elevated {EC|SAR} is due to naturally
    occurring conditions and is assumed to have little or no
    environmental risk. [PRACTITIONER TO CONFIRM]
```

Do **not** invent the specific chemistry (which ion, which compound) —
the `justification_reason` field only ever carries a short category label
("Naturally Occurring"), never the actual geochemical narrative. Auto-fill
only the sample ID, depth, and exceedance value; leave every reasoning
line as an explicit placeholder for the practitioner.

## Rating Category Order (low → high)
Good → Fair → Poor → Very Poor → Unsuitable

## Number Formatting
- Integers: no decimal places
- Floats: 1 decimal place
- Counts 1–12 in prose: **numerals** (project-wide "always numeral" rule
  from `exec_summary.md`, same override already applied in
  Section 4.2.1 — do **not** spell out "One"/"Two" even though the live
  template's own example text does)

## Formatting
- Area headings: Word style `Heading 3` (auto-numbered — no literal
  "4.2.N" in the text)
- "Summary of Results": Word style `Small Titles`
- Everything else: `Bullets` (fallback `List Bullet`, fallback unstyled)
  for bullet lines, `Normal` for the intro paragraph
- Rating category names and parameter names: bold `runs`, same convention
  as Section 4.2.1

## Output Format — `blocks` JSON for `apply_operations.py`

Same schema as Section 4.2.1: build one flat array of blocks covering
every area (concatenated, not one call per area), then wrap it as a
single `replace_between` operation:

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_42_APECS_START>",
  "end_placeholder": "<INSERT_42_APECS_END>",
  "blocks": [ ... ]
}
```

Each block: `{"style": "heading3" | "smalltitle" | "body" | "bullet",
"bold": true|false, "text": "...", "runs": [...]}`. `"smalltitle"` maps to
the `Small Titles` Word style (style ID `SmallTitles`) in
`apply_operations.py`'s `build_block_element()` — added specifically for
this section, since the live template's own "Summary of Results"
paragraphs use that style, not bold body text (the approach 4.2.1 used).

See `SKILL.md` for how all operations are combined and run together.


## Exceedance list length (standing rule, 2026-09-30)
Do NOT list every exceedance sample. For the EC and SAR bullets:
- 3 or fewer exceedances: list them ("{sample_id} at {depth} m, ...").
- More than 3: give the count, the distinct boreholes (each named once) and the depth range, e.g. "with 18 SCARG exceedances (BH26-01, BH26-02, and BH26-03; 0.3 to 6 m)." This overrides any earlier "join all" wording above. The full detail is in the Tier 1 Exceedances sheet and Section 7.
