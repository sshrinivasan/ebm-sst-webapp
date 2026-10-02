# Section 5 — Background Chloride Intro

## Placeholder

`<INSERT_5_INTRO_START>` / `<INSERT_5_INTRO_END>` — bracket the intro paragraphs. Op type: `replace_between`.

## Data source

**`Tier 1 Exceedances`** sheet — filter for:
- `APEC = "Background"`
- `Chemical Group = "Chloride"`

Also read **`EC & SAR Rating Categories`** sheet — filter for `APEC = "Background"`
to get the full background borehole list.

---

## Logic

### Step 1 — Get all background boreholes

From `EC & SAR Rating Categories`, collect all distinct `Sample ID` values where
`APEC = "Background"`. These are the background boreholes.

Format as a natural list: `BH23-12, BH23-13, BH23-14, BH24-6, BH24-7, BH24-8,
and BH24-9` (Oxford comma; "and" before last).

### Step 2 — Check for background chloride exceedances

From `Tier 1 Exceedances`, filter rows where `APEC = "Background"` AND
`Chemical Group = "Chloride"` (either mg/L or mg/kg row — deduplicate by
`Sample ID` + `Depth (m)`).

- If **no such rows exist** → omit the "However…" sentence entirely.
- If **rows exist** → collect:
  - Distinct boreholes with exceedances (for the "identified at…" clause)
  - The two highest chloride values across those boreholes (by `Value` column),
    recording `Sample ID` and `Depth (m)` for each

### Step 3 — Format the "two maximum values" clause

From the exceedance rows, find the top-2 highest `Value` entries (use the mg/kg
rows to match the example wording). Format as:

- Two values: `"two maximum values of {val1} mg/kg at {BH1} ({depth1} m) and
  {val2} mg/kg at {BH2} ({depth2} m)"`
- One value: `"a maximum value of {val} mg/kg at {BH} ({depth} m)"`
- More than two: still report only the top two, using "two maximum values of…"

Round depths to one decimal place. Round chloride values to the nearest integer.

---

## Output

Always lead with this fixed boilerplate sentence (matches the template's own wording verbatim
— it's a cross-reference to Section 4.2.1's background-borehole rationale, not site-specific,
so it never varies):

> As noted in Section 4.2.1, boreholes were advanced in undisturbed areas, away from former
> facility locations and known contaminant sources, to characterize background soil chemistry
> and native soil profiles.

### If background chloride exceedances exist

Leading sentence, then two body blocks:

> Boreholes {background_borehole_list} were advanced near the lease boundaries,
> with no evidence of soil disturbance noted in the borehole logs. However,
> chloride concentrations exceeding the Tier 1 delineation guideline of 100 mg/L
> were identified at {exceedance_borehole_list}, with {max_values_clause}.

> As naturally occurring chloride associated with saline lakes and seeps are well
> documented in the region (Last & Ginn, 2005; Kwiatkowski et al., 1996;
> Vance et al., 1993), a review of the historical activities and site-specific
> soil and groundwater information was completed to evaluate the elevated chloride
> in the outlying background locations.

### If no background chloride exceedances

Leading sentence, then one body block:

> Boreholes {background_borehole_list} were advanced near the lease boundaries,
> with no evidence of soil disturbance noted in the borehole logs. All background
> samples had chloride concentrations below the Tier 1 delineation guideline of
> 100 mg/L.

---

## JSON output

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_5_INTRO_START>",
  "end_placeholder": "<INSERT_5_INTRO_END>",
  "blocks": [
    {"style": "body", "text": "As noted in Section 4.2.1, boreholes were advanced in undisturbed areas, away from former facility locations and known contaminant sources, to characterize background soil chemistry and native soil profiles."},
    {"style": "body", "text": "[paragraph 1]"},
    {"style": "body", "text": "[paragraph 2 — omit if no exceedances]"}
  ]
}
```

## Excluded background boreholes (rule added 2026-10-01; applies only when Section 5 is present)

If the Excel contains any APEC named "Excluded Background" (e.g. `BH26-28`), those boreholes were advanced as background locations but excluded from the background evaluation. Section 5's intro must always say so, in its own sentence, using the word "excluded": name the borehole(s), state that they were excluded from the background evaluation `[REASON — PRACTITIONER TO CONFIRM]`, and give their chloride result (mg/L and depth(s) of any value above 100 mg/L, and whether vertical delineation was achieved at the maximum investigation depth). Never silently drop them and never fold them into the "Background" list. Add the exclusion (and the reason placeholder) to the Practitioner Information hand-off. Sections 5.2/5.3 describe the "Background" APEC boreholes only; mention an excluded borehole in 5.2 only when its chloride is relevant to the transport interpretation.
