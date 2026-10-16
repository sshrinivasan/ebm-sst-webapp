# Section 5.2 — Contaminant Transport Mechanisms

> **Data source override (workbook is never opened).** Every value this file says to read from an Excel sheet
> (`Borehole_Characteristics`, `EC & SAR Rating Categories`, `Tier 1 Exceedances`) is already computed in
> `excel_data.json` → `authoring_facts` (see the map in `prompts/one_call_authoring.md`). Use those values;
> do not look for or ask for the workbook. If a value you need is missing there, write a bracketed
> practitioner placeholder and list it under Practitioner Information.


## Placeholder

`<INSERT_5_2_START>` / `<INSERT_5_2_END>` — Op type: `replace_between`.

## Scope note

NPP vertical-gradient analysis (sulphate profile interpretation) and lab
soil-texture/grain-size classification are **not part of the routine report**
— they belong to a more detailed (non-routine) report type and are never
expected here, regardless of whether an `NPP-Profile Interpretation` or
`Texture 0.0-1.5`/`Texture 1.5-100.0` sheet happens to exist in a given site's
Excel output. Do not look for these sheets, do not ask the user for this data,
and do not add placeholder bullets for it. If a routine-report Excel file
happens to include those sheets anyway, ignore them for this section.

## Data sources

This section does **not** read the borehole log PDFs directly. Every
borehole-derived fact below (mottling/gleying text, Notes-line text, and
EASTING/NORTHING) comes from `site_facts.json`'s `borehole_logs.boreholes[]`
array, populated once by the unified extraction pass — see
`prompts/site_facts_cache.md`. Only the Excel-derived rows below still read
the live analytical file, since that data changes every run.

| Data | Source |
|---|---|
| Mottling / gleying / water table | `site_facts.json` → `borehole_logs.boreholes[]` — `.mottling_gleying_text`, `.has_notes_line`, `.water_table_notes_text`, one entry per borehole. There is no separate synthesized "borehole analysis" step in this skill — these are the raw per-borehole facts as extracted; interpret them per Step 1 below. |
| Max investigation depth | `Borehole_Characteristics` sheet — max of the `Deepest Sample (mbgs)` column across all boreholes |
| Impact area chloride range and depth | `EC & SAR Rating Categories` sheet — non-Background APEC rows, **`Chloride (mg/kg)` column** |
| Background chloride exceedances | `Tier 1 Exceedances` sheet — filter `APEC` = "Background" AND `Chemical Group` = "Chloride". **Use the `Chloride (mg/kg)` column, not the `Value` column** — for Chloride rows, `Value` is actually the mg/L reading (it mirrors the `Chloride (mg/L)` column), not mg/kg. Using `Value` directly will silently report mg/L numbers as if they were mg/kg. |
| Background borehole directions | Compute from survey coordinates — see Step 3 below. Do **not** ask the user; `site_facts.json`'s `borehole_logs.boreholes[].easting`/`.northing` carry the real coordinates for this. |
| Closing interpretation | Author it yourself from the computed depth facts above. Do **not** ask the user (intake Q18 was removed). |

---

## Intake quiz additions

| # | Question | Answer drives |
|---|---|---|
| ~~Q17~~ | ~~Removed — directions are computed from borehole log survey coordinates, not asked~~ | Bullet 3 direction clause |
| ~~Q18~~ | ~~Removed — the closing paragraph is authored automatically, not asked~~ | Closing paragraphs |

---

## Step 1 — No mottling/gleying (Bullet 1)

Read every borehole entry in `site_facts.json`'s `borehole_logs.boreholes[]`
(covering every log set provided).
For each borehole, check:
- `.mottling_gleying_text` — non-null means the source log mentioned
  "gleying" or "mottl" somewhere in its soil description
- `.water_table_notes_text` — the "Notes" line text, if present (e.g. "No
  evidence of water table observed.")
- `.has_notes_line: false` (some logs have no Notes line and no
  gleying/mottling mention at all) — treat the absence of any such flag as
  "not observed".

Also pull the max investigation depth from `Borehole_Characteristics`
(`Deepest Sample mbgs` column — no parentheses in the actual header, despite
how it reads in prose — max across all boreholes).

**Do not claim the max investigation depth is "the current estimate of the
water table."** An earlier version of this bullet did that, copied verbatim
from the template's own example wording, but it's wrong in general: the real
water table estimate (if any) is computed independently in Section 2.7 from
`site_facts.json`'s `borehole_logs.analysis.water_table_depth_m` /
`.water_table_basis` (e.g. an oxidized-to-unoxidized colour change at some
shallower depth) — not from "how deep we drilled without seeing gleying."
Asserting the two are the same number silently contradicts Section 2.7
whenever they differ, which they usually will.

- If **none observed in any log** →
  "The borehole logs indicate that significant mottling, gleying, or saturated
  intervals were not observed to the maximum investigation depth of {max depth}
  mbgs." If `borehole_logs.analysis.water_table_depth_m` exists and is
  meaningfully shallower than {max depth}, optionally add a second clause
  noting the two are separate lines of evidence, e.g.: "This is consistent
  with the water table estimate of {water_table_depth_m} mbgs presented in
  Section 2.7, based on {water_table_basis}." Only add this if it's actually
  consistent (max depth ≥ water table estimate) — if the water table estimate
  is somehow deeper than the max investigation depth, don't paper over that,
  flag it instead of writing a sentence that contradicts the data.

- If **observed** →
  "The borehole logs indicate mottling/gleying/saturated intervals at
  {description of locations and depths}."

---

## Step 2 — Impact area chloride (Bullet 2)

From `EC & SAR Rating Categories`, filter rows where APEC is not "Background",
not "Excluded Background" and not None. ("Excluded Background" boreholes are
background locations that were left out of the background evaluation — they are
neither impact area nor background here, so they must not be counted in either
group.) Using the **`Chloride (mg/kg)` column**, find:
- Maximum chloride value (mg/kg) across all impact rows
- Depth range of elevated chloride (min to max Z where chloride exceeds
  100 mg/kg)
- The distinct APEC labels among those elevated rows (there may be more than
  two — list all of them, don't assume only one or two areas)

→ "At the impacted {area name(s)}, elevated chloride concentrations are
concentrated in the root zone (maximum of {max} mg/kg), extending from
approximately {min depth} to {max depth} mbgs."

`{area name(s)}` = the APEC labels from those rows (e.g. "well centre and DWDA").

---

## Step 3 — Background chloride (Bullet 3)

From `Tier 1 Exceedances`, filter APEC = "Background" AND Chemical Group =
"Chloride". Collect, using the **`Chloride (mg/kg)` column** (not `Value`):
- Chloride range (min to max, mg/kg)
- Depth range (min to max `Depth (m)`)
- Distinct boreholes

### Computing directions (replaces the old Q17 intake question)

`site_facts.json`'s `borehole_logs.boreholes[]` gives each borehole's
EASTING/NORTHING (UTM), already extracted from the log PDFs. Use these to
compute a real bearing instead of asking the user:

1. Look up EASTING/NORTHING for every borehole from `borehole_logs.boreholes[]`
   (no PDF read needed — this was extracted once, in Step 1c).
2. Compute a source/impact centroid: the mean easting and mean northing of
   all impact-area boreholes (every borehole whose APEC/Ref — from this
   run's Excel data, not the cached facts — is not "Background" and not
   "Excluded Background").
3. For each background borehole with a chloride exceedance, compute the
   bearing from the centroid to that borehole:
   `angle = atan2(easting - centroid_easting, northing - centroid_northing)`
   in degrees, normalized to 0–360, then mapped to a 16-point compass
   direction (N/NNE/NE/.../NNW).
4. If a background borehole named in the Excel exceedance data has **no**
   matching entry in `borehole_logs.boreholes[]` (a real gap that can
   happen — e.g. a borehole logged in one year's Excel output but whose log
   wasn't included in the PDF set provided, so it was never extracted), do
   not invent a direction for it. State the direction for the boreholes you
   can compute, and separately flag that the direction for the missing
   borehole could not be determined because its log/coordinates were not
   available in the provided files.

→ "At the background locations, elevated chloride concentrations
({min} to {max} mg/kg) were identified from {min depth} to {max depth} mbgs,
to the {directions} of the known impact area on-site."

Format directions as: "northwest (BH23-12), south (BH23-13), and southeast
(BH24-7)" — one direction per borehole or group, using only boreholes with
computed coordinates.

---

## Step 4 — Closing paragraphs

Author the closing paragraph(s) yourself — do not ask the user. Write 2–3
sentences on the expected transport pathway and why background chloride cannot
be explained by on-site transport, grounded in the actual figures computed in
Steps 1–3 (max investigation depth, depth of impact vs. estimated water table)
rather than generic boilerplate language. Only state conclusions the computed
facts support; if they do not clearly support "cannot be explained by on-site
transport", write the narrower statement they do support.

---

## Output

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_5_2_START>",
  "end_placeholder": "<INSERT_5_2_END>",
  "blocks": [
    {"style": "body", "text": "Potential contaminant transport mechanisms were evaluated in relation to the elevated chloride in the outlying boreholes."},
    {"style": "bullet", "text": "[Bullet 1 — no mottling/gleying]"},
    {"style": "bullet", "text": "[Bullet 2 — impact area chloride]"},
    {"style": "bullet", "text": "[Bullet 3 — background chloride + directions]"},
    {"style": "body", "text": "[Closing paragraph(s), authored per Step 4]"}
  ]
}
```
