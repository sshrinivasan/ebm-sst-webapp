# Site Facts Cache — Unified PDF Extraction

## Purpose

PDF/doc extraction (ABAData, Phaseview, AER Phase 1 ESA, borehole logs) is the
slowest and most repetitive part of a run — the underlying documents describe the
physical site and rarely change between report runs (e.g. re-running after the
Excel analytical data is updated, or regenerating with a corrected intake answer).

This file is also where the **unified extraction pass** happens: instead of each
section prompt (`s5_1_phase1.md`, `s5_2_transport.md`) or Python function
(`generate_section2_3()`, `generate_section2_4()`, `generate_section2_5()`) or
the intake quiz (Q0) opening the borehole log, Phaseview, or AER Phase 1 ESA
PDFs separately, every one of those source documents is read
**once, here**, and every raw fact any section needs is pulled out into
`site_facts.json`. There is no longer a section-specific direct PDF read
anywhere downstream of this step — if a section needs something from one of
these documents that isn't captured below, the fix is to add the field to
this extraction pass, not to add a new direct read in that section's own
prompt file.

**This entire pass runs inside a subagent** (see SKILL.md Step 1c), not in
the main conversation. That has one consequence worth keeping in mind while
reading the rest of this file: the subagent cannot ask you a question
mid-run — it reads everything, then returns one final JSON object. Anywhere
below that would otherwise say "ask the user," the rule instead is: record
the field as `null` and add an entry to the top-level `extraction_flags`
array explaining what couldn't be resolved (see "A note on anything this
extraction pass can't resolve on its own" further down). The main
conversation is what actually asks you about anything flagged there, once
the subagent's JSON is back.

**This is a facts dump, not a judgment pass.** Extraction here is purely
mechanical: read a labeled field or a described block of text off the PDF and
copy it into the matching JSON key, verbatim or near-verbatim. Do **not**, at
this step:
- compute a cardinal direction, or decide whether one is reliable enough to state
- pick or trim a description paragraph
- resolve mixed land use into a single category
- write any bullet, sentence, or narrative wording
- decide whether a fact is "applicable" or should be omitted from the final report

**Two documented exceptions**:

1. `phase1_esa.findings_summary` / `.apecs` / `.copcs`, and the equivalent
   fields in each `other_previous_assessments[]` entry, require judgment — an
   authored summary of what a previous assessment found, plus the APEC/CoPC
   terms it names. This can't be a verbatim quote, since different assessments
   describe their findings in different places and formats — see "Findings
   summary and APEC/CoPC extraction" below for the guardrails on that one.
2. `borehole_logs.analysis` (stratigraphy, water table, and DUA) requires a
   structured analytical read of the borehole logs — texture classification,
   a tiered water-table estimate, and a DUA determination. This is a distinct
   task from the mechanical `borehole_logs.boreholes[]` facts dump described
   below (which stays purely mechanical) — see "Borehole log analysis →
   `borehole_logs.analysis`" below for the full method.

All of the *other* logic stays where it already lived — in
`generate_section2_3()`, `generate_section2_4()` (Python, formerly the retired
`s2_3_1_site_char.md`/`s2_3_2_regional.md` prompt files), and `s5_1_phase1.md`.
Those all read their raw material from `site_facts.json` (populated here)
instead of opening the PDFs themselves, but their rules, logic, and output
format are
unchanged. Only the *input source* moved.

This is **not** a cache for the Excel analytical data (EC/SAR ratings, exceedances,
chloride values) — that changes every run by design and must always be read fresh.
Only genuinely static, PDF-derived site facts belong here.

---

## File location and naming

One file per site, stored **in the same folder as that site's PDFs** (the site's
own working folder — e.g. `08-13/site_facts.json` for the 08-13 site), not inside
the skill's own folders.

Filename: always `site_facts.json`.

---

## Step 0 — Check for a cache before asking for files

Before Step 1 (SKILL.md's file-collection step), check whether the user's
indicated site folder already contains a `site_facts.json`.

- **If found**, read it and show the user a short summary of what's cached
  (site name, client, LSD, natural subregion name, site type — headline fields,
  not every raw value). Ask:
  - **Reuse cached facts** — skip re-reading ABAData, Phaseview, and AER Phase 1
    ESA entirely for this run. Still ask for the Excel analytical file (and
    figures zip if applicable) and the borehole log PDFs as normal — **borehole
    logs are read fresh every run, regardless of this choice** (a rerun can add
    new logs, e.g. a later BH24-* set on top of an earlier BH23-* one). This is
    unchanged from before — the only thing that changed is *where* that read
    happens: still once, here in Step 1c, never later inside `s5_2_transport.md`
    or the Q0 intake step.
  - **Force a fresh re-extraction** — if the PDFs/doc changed, ignore the cache,
    re-extract everything per the field list below, and overwrite the cache at
    the end with the new raw values.
- **If not found**, proceed with Step 1 as normal — read ABAData, Phaseview,
  AER Phase 1 ESA, and every borehole log PDF once each, extract every field
  below, and write a new `site_facts.json` at the end of the run (see Step 5).

---

## Extraction field list

Read each PDF exactly once. For each field, copy the value as it appears —
no interpretation, no reformatting beyond what's needed to represent it as a
JSON string/number/boolean. (The one exception — `findings_summary` /
`apecs` / `copcs`, covered below — does involve reading a whole document
and writing authored content.)

### ABAData Word doc → `abadata` (plus the top-level `site_type` key)

The ABAData source is now a **Word doc** (e.g. `Abadata_102-08-13-016-01W4.docx`),
not a PDF — the user's ABAData tool changed output format. Read the whole
document, not just the tables — the surrounding paragraphs carry disclaimer/
caveat language (e.g. "proximity matches only, not confirmed") that matters
for how spill records get worded below.

The doc **typically** has four tables, in this typical order — but identify
each one by its column headers and content, never by its position or
table-index number. The ABAData tool's output layout has already changed
once (PDF → Word doc) and individual docs have shown extra/duplicate
paragraph content outside the tables too (see the Landscape note below), so
nothing here should assume a fixed table count or order:
1. An "Attribute / Information" summary table — duplicates most of the
   "Field / Information" table below in slightly different wording.
   **Do not extract from this one.**
2. A **"Field / Information" table — this is the canonical source.** Always
   extract the well-attribute fields below from this table, not the
   "Attribute / Information" one, even where they overlap.
3. A location/land-context table — identify it by its content (rows for
   county/municipality, natural region or subregion, **landscape**, land
   ownership, disposition/PLA), not by assuming it's "the third table."
   Most of its rows aren't mapped to any `abadata` key (skip those), except
   its **`Landscape`** row, extracted as `abadata.landscape` (see the key
   table below).
4. A spill-records table (columns: `Date`, `Record details`) — see "Spill
   records" below. Absent entirely if the doc found no spill records at all
   (not even proximity matches).

**Landscape — search by label, not by table position.** Find the row (in
whichever table actually carries it) whose label reads exactly `Landscape`,
and extract its value verbatim, e.g. `"Low relief – hummocky"`. This is a
short relief/terrain descriptor — a genuinely different value from
`phaseview.natural_subregion_name`/`.natural_subregion_full_text` or
`phaseview.soil_description_text`, which are different sources describing
different things; don't derive it from those. Some docs also carry a
stray duplicate line earlier in the document's plain paragraphs reading
something like `"Landscape: Not established"` — that's a placeholder left
over from an earlier draft pass in the doc generator, not the real answer;
prefer the actual table row's value whenever both are present. If no row
or line anywhere in the doc is labeled "Landscape," or the only value found
reads as a non-answer ("Not established," "N/A," etc.), set
`abadata.landscape` to `null` and add an `extraction_flags` entry
describing what was found instead of guessing.

| Key | Where to find it (Field / Information table) | Notes |
|---|---|---|
| `site_name` | "Well name" row | |
| `uwi` | "Full UWI" row | new field — not in the old PDF schema |
| `surface_location` | "Surface Location" row | **The ABAData doc has no "Legal Land Description" row at all** — do not add a `legal_land_description` key under `abadata`; that field belongs only to `phase1_esa` (see below), not here. Extract this row verbatim, whatever format it actually shows (it may be DLS style or UWI style — don't assume). This is a newly added field; a `site_facts.json` cached before this field existed will not have it, and needs a fresh Step 1c extraction to pick it up. |
| `licensee` | "Licensee" row | |
| `license_no` | "License number" row | |
| `license_status` | "License status" row | new field — free text now, e.g. `"Abandoned (status date: January 25, 2021)"`, not the old coded value |
| `spud_date` | "Spud date" row | |
| `abandonment_date` | "Abandonment date" row | |
| `wellbore_depth` | "Wellbore depth" row | |
| `total_gas_production` | "Total gas production" row (include units) | |
| `total_water_production` | "Total water production" row (include units) | |
| `total_oil_production` | "Total crude oil/bitumen production" row (include units) | |
| `area_office` | "Area office" row | new field |
| `landscape` | The row/line labeled "Landscape," found anywhere in the doc — see "Landscape — search by label, not by table position" above | new field |
| `spill_records` | Table 4 (spill-records table) + surrounding narrative paragraphs | see "Spill records" below |
| `associated_spills_text` | Derived from `spill_records` | see "Spill records" below |
| `initial_copcs` | See "Initial COPCs derivation" below | unchanged from the old PDF logic |

This is the one source in this pass with fields that are a rule rather than a
straight lookup (`initial_copcs`, `spill_records`/`associated_spills_text`,
and the top-level `site_type` key) — still mechanical/deterministic, not
open-ended wording judgment, so they stay in this extraction step rather than
moving to a section prompt.

**Site type** (stored top-level in `site_facts.json`, not inside `abadata`) —
from `license_status`. The new doc gives this as a free-text sentence, not a
coded column, so match on the plain-English status word rather than an exact
code:

| `license_status` contains... | `site_type` |
|---|---|
| "Abandoned", "Suspended", "Active", or any other well-status wording | `"wellsite"` |
| No ABAData doc provided, or the status indicates a facility asset | `null` — see note below |

**Initial COPCs derivation** — apply to the combined production totals across
all rows:

| Condition | `initial_copcs` |
|---|---|
| Gas > 0, Oil = 0, Water = 0 (dry gas) | `"Salinity, PHC F1–F2"` |
| Gas > 0, Oil > 0 (gas + oil) | `"Salinity, PHC F1–F4, BTEX"` |
| Oil > 0, Gas = 0 (oil well) | `"Salinity, PHC F1–F4, BTEX"` |
| Water > 0 (produced water) | add `"Chloride, Sodium"` |

If the site has an unusual production profile not covered above, set
`initial_copcs` to `null` — see note below rather than guessing.

**A note on anything this extraction pass can't resolve on its own**: this
extraction runs inside a subagent (see SKILL.md Step 1c), which has no way
to ask you a question mid-run — it only returns one final JSON object. So
anywhere this file previously said "ask the user" or "flag for user
confirmation," the rule is now: **record the field as `null`, and add one
entry to a top-level `extraction_flags` array** in the returned JSON
describing what couldn't be resolved and why (e.g. `"site_type could not be
determined — ABAData doc's license_status does not indicate a well or
facility asset"`). The calling conversation is responsible for actually
asking you about anything in `extraction_flags` once the subagent returns —
this file just needs to make sure nothing gets silently guessed or dropped.
`extraction_flags: []` (empty array) when there's nothing to flag.

**Spill records — store in a standard, structured format**

The doc separates two very different claims, and extraction must **not
conflate them**:
- Whether any spill is confirmed as directly associated with this well by an
  **exact** match (well ID, license number, or surface-location match).
- A separate list of nearby spill records found only by **proximity search**
  (e.g. "within 1 km") — explicitly *not* confirmed to be associated with
  this well or license, even though they show up in the same document.

Store every record found (from the spill-records table, one row per record)
in a structured array:

```json
"spill_records": [
  {
    "date": "2022-07-27",
    "substance": "Water",
    "volume": "0.1 m³ released, 0 m³ recovered",
    "match_type": "proximity",
    "notes": "Named Canadian Natural Resources Limited and a licensed flowline."
  },
  {
    "date": "2008-02-01",
    "substance": "Unspecified",
    "volume": null,
    "match_type": "proximity",
    "notes": "Pre-IRIS legacy incident."
  }
]
```

- One entry per row of the spill-records table. Parse `date` to `YYYY-MM-DD`
  where the source gives a resolvable calendar date. Pull `substance`/`volume`
  out of the "Record details" text where it cleanly separates; anything that
  doesn't split cleanly goes into `notes` verbatim instead of being forced
  into the wrong field.
- `match_type`: `"exact"` only if the document explicitly states this record
  is confirmed by an exact well ID/license/location match. `"proximity"`
  otherwise — this is the normal case for this doc format. Never infer
  `"exact"` from a record simply appearing in the table.
- `[]` (empty array) if the spill-records table is absent and no proximity
  matches are mentioned anywhere in the narrative text either.

`associated_spills_text` — the sentence `generate_ebm_report.py` places
directly into the report's spill bullet — is then **authored from
`spill_records`**, not copied verbatim from any single doc sentence. This is
a judgment case, like `phase1_esa.findings_summary` below: the wording must
not overstate what the source doc actually claims.

- `spill_records` empty → use the doc's own no-spills statement, e.g.
  `"No spill records were found in the regulator's records associated with this site or these licenses."`
- Every entry `match_type: "proximity"` → state plainly that these are
  proximity matches only, not confirmed as linked to this well:
  `"No spill records were confirmed as directly linked to this well by exact license or location match. {N} spill record(s) were identified within {radius of the site} as proximity matches only (not confirmed to be associated with this well): {one-line summary per record, e.g. '2022-07-27 water release (0.1 m³)'}."`
- Any entry `match_type: "exact"` → format those the same way the old
  PDF-sourced field did, one per line: `Incident # {ID}. {Date}. Substance spilled: {vol} {unit} of {substance}.`
  (multiple substances comma-separated with "and" before the last) — then
  append any remaining proximity-only records as a separate, clearly-labeled
  sentence per the bullet above.

### Phaseview PDF → `phaseview`

| Key | Where to find it | Notes |
|---|---|---|
| `nearest_settlement_name` | Site Location Map, bottom label | e.g. `"Schuler"` |
| `nearest_settlement_distance_km` | Same label | numeric, e.g. `5.48` |
| `site_coordinates` | Top of Site Reconnaissance Report | raw `"{lat}N, {lon}W"` string, for direction math done later by the section prompt |
| `municipality` | Site Reconnaissance Report highlights table, "Municipal Areas" row | verbatim |
| `natural_subregion_name` | Natural Subregion & Vegetation section, bold heading | verbatim, e.g. `"Grassland - Dry Mixedgrass"` |
| `natural_subregion_full_text` | The full descriptive paragraph beneath that heading | verbatim, complete paragraph — do not trim or select; leave that to the section prompt |
| `soil_dominant` | Soils (AGRASID) narrative, dominant soil name | verbatim |
| `soil_codominant` | Soils (AGRASID) narrative, co-dominant soil name, if stated | verbatim, or `null` if none |
| `soil_description_text` | The full narrative sentence(s) about soil types | verbatim — the section prompt trims out CLI ratings/map-unit table separately, not this step |
| `surface_geology_genesis` | Surficial Geology table, "Genesis" row | verbatim, e.g. `"Stagnant Ice Moraine"` |
| `surface_geology_age` | Surficial Geology table, "Age" row | verbatim |
| `surface_geology_bedrock` | Surficial Geology table, "Bedrock" row | verbatim |
| `surface_geology_highlights_text` | Site Reconnaissance Summary highlights table, "Surface Geology" row | verbatim |
| `topography_elevation` | Elevation & Topography table | verbatim value + unit, e.g. `"800.9 m ASL"` |
| `topography_slope_degrees` | Same table | numeric, e.g. `4.9` |
| `topography_slope_percent` | Same table | numeric, e.g. `8.6` |
| `topography_facing_direction` | Same table | verbatim, e.g. `"Northwest"` |
| `surface_water_nearest_distance` | Water Distance Analysis Report, detailed results table, row 1 (nearest, i.e. smallest Distance) — the table is already sorted nearest-first | verbatim distance string as printed, e.g. `"112 m"` or `"1.45 km"` |
| `surface_water_nearest_bearing_deg` | Same row, Bearing column | numeric degrees, e.g. `169.4` — leave as a raw degree value; converting to a compass word (e.g. "south") is `generate_section2_5()`'s job (Python), not extraction's |
| `water_wells_filtered` | Water Wells Analysis Report, detailed results table — **only rows whose Well Use column reads Domestic, Livestock, or Unknown** (skip Irrigation, Municipal, Industrial, or any other use) | array, one entry per qualifying row: `{"distance": "1012 m", "bearing_deg": 12.0, "well_id": "232262", "well_use": "Domestic"}`. Empty array `[]` if the report lists wells but none qualify. |
| `water_wells_none_found_text` | Water Wells Analysis Report, verbatim message when the report itself reports zero features (e.g. `"No water wells identified within 1.6 km search radius"`) | `null` if the report found any wells at all (whether or not they passed the Domestic/Livestock/Unknown filter above) |
| `building_nearest_distance` | Building Distance Analysis Report, detailed results table, row 1 (nearest) | verbatim distance string, e.g. `"490 m"` |
| `building_nearest_bearing_deg` | Same row, Bearing column | numeric degrees, e.g. `249.4` |

These six fields are still a mechanical dump — grabbing the nearest-row values
and filtering the wells table by its own Well Use column is not judgment,
it's reading what the report already sorted/labeled. Converting a bearing in
degrees to a compass direction word, and formatting the Table 2.5 cell text
(including the Well ID), happens in `generate_section2_5()` (Python), not
here. Dugout has no Phaseview source and is intentionally not extracted —
that cell is left untouched in the report by `generate_section2_5()`.

### AER Phase 1 ESA PDF → `phase1_esa`

If no Phase 1 ESA PDF is supplied for this run, set `"provided": false` and
leave every other key in this block `null`.

| Key | Where to find it | Notes |
|---|---|---|
| `provided` | — | `true` if a Phase 1 ESA PDF was supplied |
| `asset_name` | Asset Information table | verbatim |
| `lld` | Asset Information table | verbatim, even if it appears to mismatch the site LLD — extraction does not judge this, it just records what the PDF says |
| `uwi` | Asset Information table | verbatim |
| `company_name` | Professional Assurance Table, Phase 1 ESA row, "Company" field | verbatim, as printed — used directly for the citation, no trimming |
| `phase1_completed_date` | "Phase 1 ESA Completed Date" | verbatim date string |
| `spud_date` | Drilling Information | verbatim date string |
| `final_drill_date` | Drilling Information | verbatim date string |
| `infrastructure_flags` | "Describe all historical and/or current infrastructure" checkboxes | object of `{checkbox_label: true/false}` for every checkbox on the form (Access Road, Pipeline, Flare Pits, etc.) |
| `spills_releases` | "Have there been any Spills/Releases/Complaints..." | `"Yes"` or `"No"`, verbatim |
| `land_use_north` / `_south` / `_east` / `_west` | Site Visit → surrounding Land Use row | verbatim per direction |
| `receptor_proximities` | "proximity of receptors" (Residence, Water Well, Surface water body) | object of `{receptor_type: value}`, verbatim |
| `additional_info_text` | "Additional Notes/Comments/Information" free-text block | full text, verbatim — this is where produced water volume/duration, pipeline directions, and nearby wellsite/facility/road mentions live; the section prompt searches this text for those specifics |
| `findings_summary` | Read the whole PDF, not one section | authored 2–5 sentence account of what it found/recommended — see "Findings summary and APEC/CoPC extraction" below |
| `apecs` | Same read as `findings_summary` | short list of the areas of concern it identified, e.g. `["Drill mud disposal area", "Well centre"]` |
| `copcs` | Same read as `findings_summary` | short list of the contaminants of potential concern it identified, e.g. `["Salinity", "Chloride"]` |

#### Findings summary and APEC/CoPC extraction (the one judgment exception)

`findings_summary`, `apecs`, and `copcs` — here and in each
`other_previous_assessments[]` entry below — are the one place in this
extraction pass where judgment is required; everywhere else in this file is a
mechanical lookup.

- Read the **whole** source PDF, not just its Conclusions/Recommendations
  section — the detail these fields need (e.g. compliance determinations,
  DWDA/well-centre recommendations) is often stated elsewhere in the document.
- `findings_summary` is an authored, normalized account — **not a verbatim
  quote**. Different assessments structure their findings differently; writing
  this once, here, gives every downstream section a consistent factual account
  to work from instead of each one re-interpreting the source PDF itself.
- `apecs` / `copcs` are short noun-phrase lists, not sentences — pull the
  actual named areas/contaminants the source document identifies.
- Do **not** apply any report-specific wording or formatting here (how to
  phrase it for the exec summary, what register Section 1.2.1's table wants,
  etc.) — those decisions stay in `exec_summary.md` and
  `s1_2_1_previous_assessments.md`, which read these fields and reshape them
  for their own output.
- Do not invent findings that aren't actually stated in the source.
- **Normalize known APEC terminology** in `apecs` and `findings_summary`
  (but not in verbatim fields like `additional_info_text`): a source document
  may phrase an APEC as "drill mud disposal area," "drilling mud disposal
  area," or "mud disposal area" — always write it as **"drilling waste
  disposal area (DWDA)"**, the skill's standard term. Apply the same
  principle to any other APEC name that's clearly the same concept under a
  different phrasing — the goal is one consistent vocabulary across every
  site's cache, not a verbatim echo of each source document's own wording.

### Borehole log PDFs → `borehole_logs`

All borehole log PDFs provided this run (both the 2023 and 2024 EBM BH log
sets, or whichever years are provided) are read here, **once each**, the same
as every other source in this pass. No section prompt reads a borehole log
PDF directly anymore — `s5_2_transport.md` and Q0 (`intake_quiz.md`) both
consume this block instead.

Two things live in this block: one **header entry per source PDF** (the
`CLIENT: ... LOCATION: ... DRILL DATE: ...` line repeated on every page — one
read is enough per file), and one **entry per individual borehole** across
every log PDF provided.

`log_sets` — one entry per borehole log PDF:

| Key | Where to find it |
|---|---|
| `source_pdf` | The filename this entry was extracted from |
| `client_name_header` | The `CLIENT:` value from the repeated header line |
| `site_location_header` | The `LOCATION:` value from the same header line, verbatim (e.g. `"102/08-13-016-01 W4M"`) — leave the `102/` prefix and any trailing `M` in place here; stripping that formatting is Q0's job, not extraction's |
| `drill_date_header` | The `DRILL DATE:` value from the same header line |
| `drilling_method` | The auger/drilling method actually in effect for this log set (e.g. `"Solid Stem Auger"`, `"S.S. Auger"`) | **Label placement is not consistent across log templates** — some PDFs put this correctly under `DRILLING METHOD:`; others (seen in 2023 08-13 logs) leave `DRILLING METHOD:` blank and put the auger type under `DRILLING CONTRACTOR:` instead, with the real contractor name absent. Read both fields on the page and use judgment: if `DRILLING METHOD:` is blank and `DRILLING CONTRACTOR:` holds an auger-type phrase (contains "auger", "solid stem", "hollow stem", etc.) rather than a company name, treat that value as the drilling method instead, and record the mislabel in `review_notes.log_errors`. Use the same value for every borehole in this log set unless a page disagrees, in which case flag it. |
| `bh_diameter_in` | The `BH DIAMETER:` value from the same header line, as a number (e.g. `6.0`) — strip the `"` mark | |

`boreholes` — one entry per borehole (i.e. per log page/section within a
PDF), across all log PDFs provided:

| Key | Where to find it | Notes |
|---|---|---|
| `borehole_id` | The borehole's own ID as printed on its log page, e.g. `"BH23-12"` | |
| `source_pdf` | The filename this borehole's log page came from | |
| `easting` | The borehole's EASTING (UTM) | numeric |
| `northing` | The borehole's NORTHING (UTM) | numeric |
| `mottling_gleying_text` | The soil description text, verbatim, if it mentions "gleying" or "mottl" anywhere | `null` if no such mention |
| `has_notes_line` | Whether this log page has a "Notes" line at all | boolean — 2024-style logs may have none; record that fact here rather than guessing later |
| `water_table_notes_text` | The "Notes" line text verbatim (e.g. `"No evidence of water table observed."`) | `null` if `has_notes_line` is `false` |
| `total_depth_m` | The `TOTAL DEPTH:` value from this borehole's own log page, in metres (e.g. `7.5`) | numeric, `null` if the field is missing/unreadable on that page — strip any trailing unit text; this is the depth the borehole was **drilled** to, not the deepest lab-sampled interval (those two routinely differ — do not substitute the Excel `Borehole_Characteristics` sheet's "Deepest Sample mbgs" column for this field, it understates depth whenever sampling stopped short of the drilled total) |

`total_depth_m` and `drilling_method`/`bh_diameter_in` are best-effort: if a
log page is scanned/garbled and the field cannot be read, record `null` rather
than guessing. Section 4's intro paragraph (<INSERT_4_INTRO_START>/_END,
Python-authored -- see the report script) degrades gracefully when these are
missing: it falls back to an "XX" placeholder for whichever piece (depth
range, borehole count, or drilling method) it could not compute, rather than
failing the whole paragraph -- a partial fact gap here should never block the
rest of the report.

This is a mechanical facts dump like the rest of this file — record what's on
each log page, don't decide yet whether "no mention" means "not observed"
(that interpretation, and the centroid/bearing math for background-borehole
directions, stays in `s5_2_transport.md`, which now reads `easting`/
`northing`/`mottling_gleying_text`/`water_table_notes_text` from this block
instead of re-parsing the PDFs). If a borehole named in the Excel exceedance
data has no matching entry in `boreholes` here (its log wasn't provided this
run), that's a genuine gap `s5_2_transport.md` still needs to flag — extraction
doesn't invent an entry for it.

### Borehole log analysis → `borehole_logs.analysis`

This is a **second, separate pass over the same borehole logs**, done in the
same subagent run (the logs are still only read once each — this and the
mechanical `boreholes[]` dump above are two outputs of that one read, not two
separate reads). Where `boreholes[]` above is a raw facts dump, this block is
the one place borehole-log *interpretation* happens: a site-wide stratigraphy
summary, a tiered water table estimate, and a Domestic Use Aquifer (DUA)
determination. It feeds Section 2.6 (Soil Characteristics) and Section 2.7
(Groundwater Characteristics) of the report — see `prompts/s2_6_soil_char.md`
and `prompts/s2_7_groundwater_char.md`.

**Method — apply this in full when producing `analysis`:**

Read every borehole's full log page (soil descriptions at every depth
interval, not just the gleying/mottling/Notes fields captured in `boreholes[]`
above) across every log PDF provided this run.

*Classify each logged unit* as fine-grained (clay, silt, clay loam, silty clay
loam, sandy clay) or coarse-grained (sand, loamy sand, sandy loam, gravel).
Judge this from the full description, not just the texture name: a unit named
"sandy clay" but described as loose and mostly fine sand is coarse-grained.
Depths may be reported in cm; convert to m, and use the depth ranges stated in
the text/depth column rather than the graphic. The maximum drilling depth is
the deepest depth actually logged in any borehole; if a header total depth
disagrees with the logged profile, use the logged depth and note the mismatch
in `review_notes.log_errors`.

*Site stratigraphy* (`analysis.stratigraphy`, under 100 words): summarize the
major stratigraphic units across the site as a whole — approximate depth
ranges, general textures, fine- or coarse-grained — without describing
boreholes one by one or listing minor lenses/stringers. Third-person technical
prose, no bullets, no invented values.

*Overall texture* (`analysis.texture_overall`): `"Fine"`, `"Coarse"`, or
`"Fine and Coarse"` if the site has a genuine mix — this fills Table 2.6's
one-line Texture cell, so it's a single site-wide call, not a per-borehole
list.

*Water table* (`analysis.water_table_depth_m`, `.water_table_range_m`,
`.water_table_tier`, `.water_table_basis`, `.water_table_statement`):
estimate from the highest tier of evidence available anywhere on site.
Boreholes without that tier's evidence are excluded from the estimate, not
treated as zero:

  - Tier 1 — Observed water: water observed during drilling, recorded in the
    log notes, a water level symbol, or the soil descriptions.
  - Tier 2 — Wet or saturated soils: top of the shallowest interval described
    as wet or saturated, or with seepage/sloughing.
  - Tier 3 — Gleying: top of the shallowest gleyed interval.
  - Tier 4 — Oxidation change: depth of the change from oxidized (e.g. olive
    brown, yellowish brown, "oxidation", iron oxides) to unoxidized (e.g. dark
    grey, dark brown) soil. Ignore colour changes at contacts with fill,
    disturbed soil, or sump material.
  - Tier 5 — Mottling: top of the shallowest mottled interval.
  - Tier 6 — Maximum drilling depth, if none of the above are present anywhere
    on site.

For tiers 1–5, average the depth (rounded to 0.1 m) across the boreholes with
that evidence and give the range; exclude any single value more than double
the median as an outlier and note the exclusion in `review_notes`. Water
observations, wet/saturated soils, gleying, and mottling are checked in the
log notes, any water-level symbol, *and* the soil descriptions — not just one
of the three. `water_table_basis` names the indicator used (e.g. "observed
water", "wet or saturated soils", "the oxidized-to-unoxidized colour change",
"mottling", or "the maximum depth of drilling" for Tier 6).

*Domestic Use Aquifer* (`analysis.dua_identified`, `.dua_depth_m`,
`.dua_statement`): a qualifying layer is logged with SAND or GRAVEL as its
texture name (not loamy sand, sandy loam, clayey sand, or other modified
textures, even if described as coarse-grained), described as wet or
saturated, greater than 0.5 m thick as a single uninterrupted interval, with
its top below the observed water table *in that borehole*. Do not add
separate layers together to reach 0.5 m. Classify qualifying layers by how
many boreholes drilled deep enough to encounter them actually show them:
potentially continuous (present in more than half), potentially discontinuous
(two or more, not the majority), or potentially isolated (one). Only a
potentially continuous layer counts as a potential DUA — report discontinuous/
isolated layers, and anything that nearly qualified, in `review_notes`. If no
potential DUA is identified, `dua_depth_m` is the maximum drilling depth and
`dua_identified` is `false`.

*Review notes* (`analysis.review_notes.judgment_calls[]` and
`.log_errors[]`): this is for the practitioner reviewing the write-ups and the
logs, not report text. Use `judgment_calls` for things like which tier the
water table estimate rests on and which boreholes were included/excluded,
weaker indicators not used in the estimate, boreholes whose logs disagree with
each other (e.g. different loggers using different colour-description
conventions), and the shallow-DUA caveat (note if `dua_depth_m` is less than
6 m, more strongly if less than 3 m). Use `log_errors` for header/log
mismatches, missing or contradictory water observations, duplicate or
implausible coordinates, possible duplicated logs, contradictory descriptors,
and transcription anomalies in screening data. Name the borehole and depth
where relevant. Write `[]` for either list with no genuine items — don't
invent filler.

*Groundwater comments* (`analysis.groundwater_comments`): one short sentence
for Table 2.7's Comments cell, in the report's own register — e.g. "No
evidence of groundwater was observed to the maximum depth of investigation;
the estimated water table is based on the oxidized-to-unoxidized colour
change." Keep this consistent with `water_table_statement` and
`dua_statement`, just shorter.

Do not invent or estimate values not recorded in the logs. Refer to the
location as "the site" in `stratigraphy`/statements, not by client or
location name.

### Other previous-assessment PDF(s) → `other_previous_assessments` (array)

A site can have previous assessments beyond just a Phase 1 ESA — a prior
Phase 2 ESA, a geophysical/EM survey, an earlier soil investigation, etc. Any
such document provided at the start of the run (besides the Phase 1 ESA) gets
one entry in this array, extracted the same way as `phase1_esa.findings_summary`
/ `apecs` / `copcs` above — read the whole document once, write an authored
summary plus APEC/CoPC lists.

| Key | Notes |
|---|---|
| `document_type` | What kind of assessment it is, e.g. `"Phase 2 ESA"`, `"Geophysical/EM survey"`, `"Soil investigation"` — verbatim or the closest plain description if the document doesn't label itself |
| `year` | Four-digit year the assessment was completed |
| `findings_summary` | Same rules as `phase1_esa.findings_summary` above |
| `apecs` | Same rules as `phase1_esa.apecs` above |
| `copcs` | Same rules as `phase1_esa.copcs` above |
| `source_pdf` | The filename this entry was extracted from |

If no additional previous-assessment documents were provided this run,
`other_previous_assessments` is an empty array `[]` — not omitted, not `null`.

---

## Step 5 — Write/update the cache after a run

At the end of any run where the PDFs were read fresh, write `site_facts.json` to
the site folder with the raw-fact schema below, overwriting any existing file.

Do **not** write or update this file when the cache was reused unchanged.

---

## Schema

```json
{
  "site_lsd": "08-13-016-01 W4",
  "uwi": "102/08-13-016-01W4/0",
  "client_name": "Canlin Energy Corporation",
  "site_type": "wellsite",
  "abadata": {
    "site_name": "Canlin MEDHAT 8-13-16-1",
    "uwi": "102/08-13-016-01W4/0",
    "surface_location": "<verbatim value from the doc's 'Surface Location' row — not yet extracted for this site's cache; do not fabricate>",
    "licensee": "Canlin Energy Corporation",
    "license_no": "0102497",
    "license_status": "Abandoned (status date: January 25, 2021)",
    "spud_date": "August 9, 1983",
    "abandonment_date": "January 25, 2021",
    "wellbore_depth": "571 m",
    "total_gas_production": "4,169,300 m³",
    "total_water_production": "No production total found; not confirmation of zero production.",
    "total_oil_production": "No production total found; not confirmation of zero production.",
    "area_office": "Medicine Hat",
    "landscape": "Low relief – hummocky",
    "spill_records": [
      {
        "date": "2022-07-27",
        "substance": "Water",
        "volume": "0.1 m³ released, 0 m³ recovered",
        "match_type": "proximity",
        "notes": "Named Canadian Natural Resources Limited and a licensed flowline."
      }
    ],
    "associated_spills_text": "No spill records were confirmed as directly linked to this well by exact license or location match. 3 spill record(s) were identified within 1 km of the site as proximity matches only (not confirmed to be associated with this well): 2022-07-27 water release (0.1 m³); 2008-02-01 unspecified substance; 2008-01-02 unspecified substance.",
    "initial_copcs": "Salinity, PHC F1–F2"
  },
  "phaseview": {
    "nearest_settlement_name": "Schuler",
    "nearest_settlement_distance_km": 5.48,
    "site_coordinates": "{lat}N, {lon}W",
    "municipality": "Cypress County",
    "natural_subregion_name": "Grassland - Dry Mixedgrass",
    "natural_subregion_full_text": "full paragraph, verbatim",
    "soil_dominant": "Fort Mackay",
    "soil_codominant": "Maughan",
    "soil_description_text": "full narrative sentence(s), verbatim",
    "surface_geology_genesis": "Stagnant Ice Moraine",
    "surface_geology_age": "Pleistocene",
    "surface_geology_bedrock": "Bearpaw Formation (Upper Cretaceous)",
    "surface_geology_highlights_text": "Sediment is mainly till but locally includes stratified glaciolacustrine or glaciofluvial sediments deposits.",
    "topography_elevation": "800.9 m ASL",
    "topography_slope_degrees": 4.9,
    "topography_slope_percent": 8.6,
    "topography_facing_direction": "Northwest",
    "surface_water_nearest_distance": "112 m",
    "surface_water_nearest_bearing_deg": 169.4,
    "water_wells_filtered": [
      {"distance": "1012 m", "bearing_deg": 12.0, "well_id": "232262", "well_use": "Domestic"}
    ],
    "water_wells_none_found_text": null,
    "building_nearest_distance": "490 m",
    "building_nearest_bearing_deg": 249.4
  },
  "phase1_esa": {
    "provided": true,
    "asset_name": "...",
    "lld": "...",
    "uwi": "...",
    "company_name": "...",
    "phase1_completed_date": "...",
    "spud_date": "...",
    "final_drill_date": "...",
    "infrastructure_flags": {"Access Road": true, "Pipeline": true, "Flare Pits": false},
    "spills_releases": "No",
    "land_use_north": "Agriculture",
    "land_use_south": "Agriculture",
    "land_use_east": "Agriculture",
    "land_use_west": "Agriculture",
    "receptor_proximities": {"Residence": ">300m", "Water Well": ">300m", "Surface water body": "Not Applicable"},
    "additional_info_text": "full free-text block, verbatim",
    "findings_summary": "authored 2–5 sentence account, verbatim not required",
    "apecs": ["Drill mud disposal area", "Well centre"],
    "copcs": ["Salinity", "Chloride"]
  },
  "other_previous_assessments": [
    {
      "document_type": "Phase 2 ESA",
      "year": "2022",
      "findings_summary": "authored 2–5 sentence account",
      "apecs": ["..."],
      "copcs": ["..."],
      "source_pdf": "prior_phase2_esa.pdf"
    }
  ],
  "borehole_logs": {
    "log_sets": [
      {
        "source_pdf": "2023 EBM BH Logs_08-13.pdf",
        "client_name_header": "Canlin Energy Corporation",
        "site_location_header": "102/08-13-016-01 W4M",
        "drill_date_header": "2023-09-12"
      },
      {
        "source_pdf": "2024 EBM Borehole Logs_08-13.pdf",
        "client_name_header": "Canlin Energy Corporation",
        "site_location_header": "102/08-13-016-01 W4M",
        "drill_date_header": "2024-08-06"
      }
    ],
    "boreholes": [
      {
        "borehole_id": "BH23-12",
        "source_pdf": "2023 EBM BH Logs_08-13.pdf",
        "easting": 471234.5,
        "northing": 5511234.0,
        "mottling_gleying_text": null,
        "has_notes_line": true,
        "water_table_notes_text": "No evidence of water table observed."
      },
      {
        "borehole_id": "BH24-7",
        "source_pdf": "2024 EBM Borehole Logs_08-13.pdf",
        "easting": 471300.2,
        "northing": 5511180.4,
        "mottling_gleying_text": null,
        "has_notes_line": false,
        "water_table_notes_text": null
      }
    ],
    "analysis": {
      "stratigraphy": "The site is underlain by topsoil (0 to approximately 0.5 m) over fine-grained soils to the maximum depths investigated (3.0 to 12.0 m). Near-surface intervals (to about 1.0 m) are locally disturbed or fill-affected sandy clay/silty clay. Below this, the 2023 program (to 3.0-7.5 m) encountered brown sandy clay and sandy clay loam with trace oxides; the 2024 program (to 4.5-12.0 m) encountered an olive-brown to greyish-brown silty clay grading to grey sandy clay at depth. No sand or gravel units were logged anywhere on site; all units are fine-grained.",
      "texture_overall": "Fine",
      "water_table_depth_m": 4.8,
      "water_table_range_m": "3.0 to 6.5",
      "water_table_tier": 4,
      "water_table_basis": "the oxidized-to-unoxidized colour change",
      "water_table_statement": "The water table was not observed during drilling; the water table depth is estimated at 4.8 m, with a range of 3.0 to 6.5 m, based on the oxidized-to-unoxidized colour change at 9 boreholes.",
      "dua_identified": false,
      "dua_depth_m": 12.0,
      "dua_statement": "A potential DUA was not identified; the DUA depth is estimated at 12.0 m, the maximum depth of drilling.",
      "groundwater_comments": "No evidence of groundwater was observed to the maximum depth of investigation; the estimated water table is based on the oxidized-to-unoxidized colour change.",
      "review_notes": {
        "judgment_calls": ["..."],
        "log_errors": ["..."]
      }
    }
  },
  "source_pdfs": {
    "abadata": "Abadata_102-08-13-016-01W4.docx",
    "phaseview": "comprehensive_environmental_analysis_2026_08-13-016-01W4.pdf",
    "phase1_esa": "ESA1_30642221.pdf",
    "borehole_logs": ["2023 EBM BH Logs_08-13.pdf", "2024 EBM Borehole Logs_08-13.pdf"]
  },
  "extraction_flags": [],
  "extracted_at": "2026-09-18"
}
```

Notes on fields:
- `site_type`: "wellsite" or "facility" (intake Q1, auto-derived from ABAData
  `license_status`).
- `phase1_esa.provided`: `false` (all other `phase1_esa` fields `null`) if no
  Phase 1 ESA PDF was supplied that run — `s5_1_phase1.md` skips its section
  entirely in that case.
- A mismatch between `phase1_esa.lld`/`uwi` and the site's own `site_lsd` is not
  an extraction concern — the subagent records what the PDF says, verbatim,
  and does not try to "correct" it. Surfacing the mismatch to you is Q0's
  job, in the main conversation, after the subagent returns (see
  `prompts/intake_quiz.md` Q0 step 3) — not something the subagent itself
  needs to flag via `extraction_flags`.
- `initial_copcs`: intake Q10, auto-derived from ABAData production totals.
- Areas of Environmental Concern and Remaining COCs **for the current
  investigation** are not cached — those APECs come from the Excel file
  (changes every run) and Remaining COCs are now auto-derived from
  `Tier 1 Exceedances`' unresolved-classification chemical groups (formerly
  intake Q11 — see `prompts/intake_quiz.md`), not from a PDF. This is separate from
  `phase1_esa.apecs` / `other_previous_assessments[].apecs`, which describe
  what a *previous* assessment found, not the current one.
- `phase1_esa.findings_summary`/`.apecs`/`.copcs` and each
  `other_previous_assessments[]` entry are the one judgment exception in this
  extraction pass — see "Findings summary and APEC/CoPC extraction" above.
- `borehole_logs.boreholes[]` is read fresh every run regardless of the Step 0
  cache choice (see Step 0 above) — but is still only read **once per run**,
  here, not re-read later by `s5_2_transport.md` or Q0. Which boreholes count
  as "background" vs. impact-area is not stored here — that's an Excel-driven,
  per-run classification `s5_2_transport.md` applies on top of these raw
  coordinates.
- `borehole_logs.analysis` is rebuilt fresh in the same run as `boreholes[]`
  (same reasoning: a rerun can add new logs, which can change the
  stratigraphy/water-table/DUA picture) — it is not reused from a prior cache
  either, even when the rest of the cache is reused. It's produced as a
  second output of the same borehole-log read, not a second read of the PDFs.
- Cache reuse (Step 0) is all-or-nothing. If a run supplies a previous-assessment
  document that wasn't part of the original cache (e.g. a Phase 2 ESA the user
  didn't have on the first run), reusing the cache as-is won't pick it up — force
  a fresh re-extraction instead, or flag this to the user if it looks like it
  might apply.
- Borehole log header facts (client name, site LSD) are cached under the
  top-level `site_lsd` / `client_name` keys since Q0 derives them from
  `borehole_logs.log_sets[]`, but the underlying `borehole_logs` block
  itself is still rebuilt fresh every run (see below) — it's not reused from
  a prior `site_facts.json` the way `abadata`/`phaseview`/`phase1_esa` are.
- `uwi` (top-level) is the one reconciled value across `abadata.uwi` and
  `phase1_esa.uwi`, resolved by Q0 the same way as `site_lsd` — see
  `prompts/intake_quiz.md` Q0. It can be `null` if neither source has a
  value; nothing downstream currently reads it (no section prompt or
  generator code displays UWI in the report), it's cached purely so there's
  one agreed-upon value on record.
- `site_lsd` is likewise the one reconciled value across **four** sources
  (borehole log headers, `abadata.surface_location`, `abadata.uwi`,
  `phase1_esa.lld`) — not just the borehole logs with the others as
  fallback/cross-check — see `prompts/intake_quiz.md` Q0. `abadata.uwi` is
  normalized to the same DLS-style comparison format as the other three
  before checking agreement, since it carries UWI-style
  event-code/meridian-letter formatting the others don't. Downstream,
  `generate_section2_1()` uses this reconciled value for Section 2.1's
  "Legal Land Description" table cell too, not any raw per-source field
  directly — so the raw per-source fields inside `abadata`/`phase1_esa`
  stay untouched (extraction never "corrects" what a source document
  said), but the report itself only ever shows the one reconciled LLD.

---

## What this does NOT change

- Excel analytical file: always read fresh, every run.
- Figures zip: always read fresh, every run.
- Borehole log PDFs: always provided and read fresh, every run, into
  `borehole_logs` (coordinates and mottling/gleying/water-table facts for
  Section 5.2, and the header for Q0) — because a re-run may include
  additional/updated logs. This is unchanged from before; only *where* the
  read happens changed (once, here in Step 1c, not separately inside
  `s5_2_transport.md` or Q0 anymore).
- The intake questionnaire (Q3–Q20 area): unaffected — these are per-run
  judgment calls, not source-document facts, so they are never cached.
- The logic in `generate_section2_3()`, `generate_section2_4()`,
  `generate_section2_5()` (Python), `s5_1_phase1.md`, and `s5_2_transport.md`
  — unchanged. They all just read `site_facts.json` instead of the source
  documents directly now.
