# Executive Summary Prompt

## Placeholders
`<INSERT_EXEC_SUMMARY_START>` / `<INSERT_EXEC_SUMMARY_END>` — bracket the
existing variant-text block in the Word template. Op type: `replace_between`.

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_EXEC_SUMMARY_START>",
  "end_placeholder":   "<INSERT_EXEC_SUMMARY_END>",
  "blocks": [
    {"style": "body", "text": "Facility paragraph..."},
    {"style": "body", "text": "History + purpose paragraph..."},
    {"style": "body", "text": "Recent investigation summary + chloride delineation paragraph(s)..."},
    {"style": "body", "text": "Exceedance summary + conclusion paragraph..."}
  ]
}
```

The executive summary is organized as four logical sections. Each section
below can produce one or more `body` blocks; combine them all, in order,
into the single `replace_between` operation's `blocks` array. There is no
literal heading text inserted for these section names — they are just this
document's own organization of the content.

---

## Inputs required

The following must be known before authoring this section. Most come from
the intake quiz; the investigation details come from the borehole logs or
the `Borehole_Characteristics` sheet in the Excel output.

| Input | Source |
|---|---|
| Client name (+ acronym, if used) | Borehole log headers (the "Client" field on the log) |
| OWA project? (yes/no) | Borehole log headers — OWA projects show OWA as the client or name OWA in the project field |
| Site name (as it appears in the report title) | Intake quiz / Site Profile PDF |
| Site type (wellsite / compressor station / facility) | Intake quiz Q1 |
| Surface location (LSD) | Site Profile PDF |
| Previous assessments? (yes/no) | `site_facts.json` — `phase1_esa.provided` is `true` and/or `other_previous_assessments` is non-empty |
| Phase 1 ESA company + year (if a Phase 1 ESA is among the previous assessments) | `site_facts.json` — `phase1_esa.company_name` / `phase1_esa.phase1_completed_date` (year portion) |
| APECs (pooled across all previous assessments) | `site_facts.json` — `phase1_esa.apecs` + every `other_previous_assessments[].apecs`, deduplicated |
| CoPCs (pooled across all previous assessments) | `site_facts.json` — `phase1_esa.copcs` + every `other_previous_assessments[].copcs`, deduplicated |
| **Is this the site's first soil investigation?** (yes/no) | Intake quiz — drives whether "recent" qualifies "soil investigation(s)" in Section 3 |
| Investigation date groups (one or more drilling events, each a single date or a contiguous date range) | Borehole logs' `DRILL DATE` header — see grouping rule below |
| Number of boreholes (this run) | Borehole logs / `Borehole_Characteristics` sheet — **always rendered as a numeral**, never spelled out (e.g. "8 boreholes", "20 boreholes") |
| Maximum borehole depth (m) | Borehole logs / `Borehole_Characteristics` sheet |
| Delineation outcome (achieved / achieved except one lateral direction, inferred / not achieved / background-chloride variant) | Intake quiz + Excel |
| Background chloride identified? (yes/no) | Excel — presence of `Background` rows in `Borehole_Characteristics` with Chloride (mg/L) > 100 |
| Named areas/APECs investigated this run, with per-area exceedance status | `Tier 1 Exceedances` sheet — see "Named areas" rule in Section 4, below. **Fully data-driven — do not assume a fixed pair of areas.** |
| Per-area chemical group(s) exceeded, and justification status/reason | `Tier 1 Exceedances` sheet's `APEC`, `Chemical Group`, `Justified (yes/No)`, `Justification` columns |
| Remedial action required? (not required / not recommended (justified) / required / further investigation needed to complete delineation) | Intake quiz + Excel |
| Volume of impact (m³ and tonnes) | Required only if remediation required and a volume is known; may attach to a specific area's sentence or stand alone — see Section 4 |

### Intake quiz additions for this section

Add the following to `intake_quiz.md`:

| # | Question | Answer drives |
|---|---|---|
| Q2 | ~~Removed — previous assessments, APECs, and CoPCs auto-derived by reading the Phase 1 ESA and any other previous-assessment PDF(s) provided at the start of the run~~ | Whether to include the History + Purpose paragraph |
| Q2b | ~~Removed — derived from whether any `other_previous_assessments[]`/`phase1_esa` entry is itself a prior soil investigation or Phase 2 ESA (same pooled data Q2 already reads); "first investigation" if none is~~ | "recent" qualifier + singular/plural phrasing in Section 3 |
| Q3 | ~~Removed — both vertical and lateral status now auto-derived from `chloride_delineation_data` (the same computation `s4_3_chloride.md` uses), via borehole UTM coordinates instead of a directional ask~~ | 3B-i's lateral clause in Section 3 |
| Q4 | ~~Removed — Section 4 Step 2 (below) already classifies every area's justification status mechanically from `Tier 1 Exceedances`~~ | Section 4 per-area justification clauses |
| Q5 | ~~Removed — Section 4 Step 4 (below) already computes this deterministically from Step 2 + 3B-i. `s8_summary.md` must consume this same computed value~~ | Section 4 conclusion sentence |
| Q6 | If required: what is the estimated volume of impact (m³ and tonnes), and does it attach to a specific area? | Section 4 volume sentence/clause |

---

## Section 1 — Facility (always present, one paragraph)

**Site type wording (`[wellsite/compressor station/facility]`) is a locked
lookup, not a per-run choice:** use `site_facts.json`'s top-level `site_type`
field verbatim (auto-derived at Q1 — see `prompts/intake_quiz.md`). Do not
pick this independently from context or examples. This same value must also
be used, word for word, in Section 1's "Introduction" paragraph at
`<INSERT_1_START>`/`_END` (see `prompts/s1_introduction.md`) — the two
paragraphs share this fact and must never disagree on it.

**OWA project:**
> The Orphan Well Association (OWA) retained EBM Geoscience Inc. (EBM) on behalf of [Client] to complete a Phase 2 Environmental Site Assessment (ESA) at the [Site Name] [wellsite/compressor station/facility] at surface location [LSD] (the site). The purpose of the assessment was to investigate each area of potential environmental concern (APEC) for the appropriate contaminants of potential concern (CoPCs) and to confirm the presence or absence of contamination.

**Non-OWA project:**
> [Client full name] ([Client short name]) retained EBM Geoscience Inc. (EBM) to complete a Phase 2 Environmental Site Assessment (ESA) at the [Site Name] [wellsite/compressor station/facility] at surface location [LSD] (the site). The purpose of the assessment was to investigate each area of potential environmental concern (APEC) for the appropriate contaminants of potential concern (CoPC) and to confirm the presence or absence of contamination.

Examples:
> The CLIENT NAME (CLIENT ACRONYM) retained EBM Geoscience Inc. (EBM) to complete a Phase 2 Environmental Site Assessment (ESA) at the Questfire F30335 compressor station at surface location 15-14-014-04 W4M (the site). The purpose of the assessment was to investigate each area of potential environmental concern (APEC) for the appropriate contaminants of potential concern (CoPCs) and to confirm the presence or absence of contamination.

> Canlin Energy Corporation (Canlin) retained EBM Geoscience Inc. (EBM) to complete a Phase 2 Environmental Site Assessment (ESA) at the Canlin MEDHAT 9-2-14-3 wellsite at surface location 100/09-02-014-03W4M (the site). The purpose of the assessment was to investigate each area of potential environmental concern (APEC) for the appropriate contaminants of potential concern (CoPC) and to confirm the presence or absence of contamination.

*(This section's logic is unchanged from before — only regrouped under this
section name. The OWA variant is retained for OWA-sponsored projects even
though the latest examples supplied were both non-OWA; flag if OWA framing
should be dropped entirely.)*

---

## Section 2 — History + Purpose (include only if previous assessments exist)

> Previous assessments included [list assessments, e.g., a Phase 1 ESA, a geophysical investigation, and a soil investigation]. The identified APECs included [list APECs, e.g., the well centre, the drilling waste disposal area (DWDA), and an electromagnetic (EM) anomaly]. The CoPCs included [list CoPCs, e.g., chloride-related salinity impact, petroleum hydrocarbons (PHCs), polycyclic aromatic hydrocarbons (PAHs), glycols, and metals].

**APECs and CoPCs here are a mechanical pool, not a fresh read.** They come
from `site_facts.json`'s `phase1_esa.apecs` / `.copcs` plus every
`other_previous_assessments[].apecs` / `.copcs` — combine all of them and
de-duplicate into one list each for the paragraph. These were already written
as an authored, normalized summary during the unified extraction pass (Step
1c, see `prompts/site_facts_cache.md`'s "Findings summary and APEC/CoPC
extraction") — do not re-open the source PDFs or re-derive this list here.

- **List one assessment per source document**, in this order: the Phase 1 ESA
  first (if `phase1_esa.provided` is `true`), then each
  `other_previous_assessments[]` entry.
  - For the Phase 1 ESA, name the company that completed it if the
    assessment-list phrasing calls for it: "a Phase 1 ESA completed by
    {phase1_esa.company_name} ({year from phase1_esa.phase1_completed_date})".
    This is the same `company_name` and year fields Section 5.1
    (`s5_1_phase1.md`) cites — use them verbatim, do not substitute a
    person's name. (The latest example omits the company/year and simply
    says "a Phase 1 ESA" — both forms are acceptable; prefer including the
    company/year when it reads naturally alongside the other list items.)
  - For each other entry, name it by its `document_type` and, where it reads
    naturally, `year` (e.g. "a geophysical investigation", "a soil
    investigation", or "a Phase 2 ESA (2022)").
- **Then list the combined, deduplicated APECs and CoPCs** pooled from all
  entries as described above. APECs are not limited to "well centre"/"DWDA"
  here — an EM anomaly or any other named area from the previous assessments
  belongs in this list too.
- If no previous assessments exist at all (`phase1_esa.provided` is `false`
  and `other_previous_assessments` is empty), omit this paragraph entirely.

---

## Section 3 — Recent Investigation Summary + Chloride Delineation (always present)

This section merges what used to be the investigation/delineation sentence
and the separate background-chloride paragraph into one continuous block,
built from two independent choices: **(A)** how the investigation-dates
sentence is phrased, and **(B)** which delineation-outcome variant follows
it. Background chloride is one of the Section 3(B) delineation variants, not
a separate paragraph anymore.

### 3A — Investigation sentence (always first)

- **"recent" qualifier**: include the word "recent" before "soil
  investigation(s)" only if this is **not** the site's first soil
  investigation (i.e. a prior soil investigation or Phase 2 ESA already
  happened at this site). Omit "recent" when this is the first investigation
  on-site. **Auto-derived, not asked (formerly Q2b):** true "not first
  investigation" whenever `phase1_esa.provided` is `true` with a
  `document_type`/description indicating a prior soil investigation or Phase
  2 ESA (not just a Phase 1 ESA), OR any `other_previous_assessments[]`
  entry's `document_type` is "soil investigation" or "Phase 2 ESA" — the
  same pooled list Q2's auto-derivation already reads. A Phase 1 ESA alone
  does not count as a prior soil investigation (it's a desktop/records
  review, not drilling) — only entries that are themselves an on-site
  investigation trigger "recent". If the pooled list is empty, this is the
  first investigation — omit "recent".
- **Singular vs. plural**: group the borehole logs' `DRILL DATE` values into
  distinct **drilling events** — a drilling event is one date, or a
  contiguous run of dates (e.g. "November 22–23, 2024" is one event; "April
  18–19, 2025" is one event; if the program also included November 22, 2024
  separately, that is a second, non-contiguous event).
  - **One event**: singular — "The \[recent \]soil investigation was
    conducted on/from [date or date range]."
  - **Two or more events**: plural — "The \[recent \]soil investigations
    were conducted on/from [event 1] and [event 2]\[, and [event 3]\]." Join
    multiple events the same way multiple dates were joined before: commas
    between events, "and" before the last.
  - Render a single-day event as "on [Month Day, Year]" and a multi-day
    contiguous event as "from [Month Day–Day, Year]" (or "from [Month Day,
    Year] to [Month Day, Year]" if the event spans a month/year boundary).
- **Borehole count**: "[N] boreholes were advanced to a maximum depth of
  [X.X] m." **N is always a numeral**, regardless of size (e.g. "8
  boreholes", "11 boreholes", "20 boreholes") — there is no spell-out
  threshold anymore.

Examples:
> The soil investigation was conducted from November 22–23, 2024. Eight boreholes were advanced to a maximum depth of 9.0 m.

*(Per the numeral rule above, author this as "8 boreholes", not "Eight
boreholes" — the pasted example spells it out, but the confirmed rule is
always-numeral.)*

> The recent soil investigation was conducted on November 22, 2024. Eight boreholes were advanced to a maximum depth of 9.0 m.

> The recent soil investigations were conducted on November 22, 2024 and from April 18–19, 2025. 20 boreholes were advanced to a maximum depth of 15.0 m.

### 3B — Delineation-outcome variant (always one of the following, right after 3A)

**3B is two independent clauses, not a single four-way choice.** Background
chloride and incomplete standard delineation can — and, in real data, do —
occur at the same site at the same time (e.g. a well centre/DWDA that isn't
fully delineated *and* a separate set of background boreholes running hot).
Evaluate each clause on its own evidence and emit whichever apply, in order:

**3B-i — Standard chloride delineation status.** Both halves are now
auto-derived from `excel_data.json`'s `chloride_delineation_data` key (the
same computation `s4_3_chloride.md`/Section 4.3 uses — see
`compute_chloride_delineation_data()` in `scripts/generate_ebm_report.py`).
This used to require an intake question (formerly Q3) because the Excel
had no lateral/directional column at all; it now does, computed from
borehole UTM coordinates (centroid + 8-point bearing bucket) rather than
asked — reuse the exact same `chloride_delineation_data` this run already
produced for Section 4.3, don't recompute it separately or ask fresh.

- **Vertical**: `vertical_status` — treat `achieved` and
  `achieved_with_override` as "achieved" for this sentence (the override
  already resolved the shallow failure; don't narrate the override
  mechanics here, that belongs to Section 4.3 only). `not_achieved` ->
  name the `vertical_unresolved` boreholes.
- **Lateral**: from `lateral_status`, ignore any `no_coverage` direction
  entirely (no evidence either way, never claim achieved or not there). If
  every direction with coverage is `achieved` -> lateral achieved in all
  directions. If any direction is `not_achieved` -> name those specific
  direction(s) for the "except for lateral delineation to the [direction]"
  clause below.
- If `chloride_delineation_data` is `null` (no `EC & SAR Rating Categories`/
  `Borehole_Characteristics` sheet at all), this is a genuine gap — flag it
  rather than falling back to asking the user, since asking now papers
  over a data problem the report should surface instead.

Emit whichever one variant fits, combining the mechanical vertical finding
with the practitioner's lateral answer:

- **Achieved (no exceptions):**
  > Vertical and lateral delineation to the Tier 1 standard of 100 mg/L chloride was achieved.
- **Achieved except one (or more) lateral direction(s):**
  > Vertical and lateral delineation to the Tier 1 standard of 100 mg/L chloride was achieved, except for lateral delineation to the {not_achieved direction(s), joined with "and"}. However, lateral delineation was inferred based on the decreasing concentrations and the EM survey.

  The "inferred based on decreasing concentrations and the EM survey"
  clause is not itself derivable (whether an EM survey exists and whether
  concentrations were actually decreasing toward that direction is a
  practitioner judgment on the specific readings) — keep this clause as
  the practitioner's call, informed by the actual `lateral_status` values
  for the failing direction(s), rather than asking a separate open
  question for it.
- **Not achieved:**
  > Vertical delineation to the Tier 1 standard of 100 mg/L chloride was not achieved at various locations, and lateral delineation was not achieved to the [direction(s)].
- Omit 3B-i entirely if no chloride delineation applies to this site at all
  (no named APEC had chloride sampled against the Tier 1 standard).

**3B-ii — Background chloride** (append after 3B-i, as additional
sentences, whenever the `Borehole_Characteristics` sheet shows background
boreholes (`Ref_A = 'Background'`) with `Chloride (mg/L) > 100` in the
`Tier 1 Exceedances` sheet — regardless of what 3B-i concluded):

> Elevated background chloride was identified at [N] location(s), with a maximum concentration of [value] mg/L. Vertical and lateral chloride delineation to the Tier 1 standard of 100 mg/L or to background levels was achieved. Section 5 provides a site-specific evaluation and justification of the background chloride.

- `N` follows the same always-numeral rule as the borehole count.
- The middle sentence's delineation clause describes the *background*
  boreholes' own delineation outcome specifically (to Tier 1 or to
  background levels) — independently of whatever 3B-i concluded about the
  named APECs. Adapt it the same way as 3B-i if background delineation
  itself was not achieved (e.g. "...was not achieved" / "...was achieved
  except for [detail]") rather than defaulting to "was achieved."
- Omit 3B-ii entirely if no background chloride was identified.

If both 3B-i and 3B-ii apply, the result is one continuous run of sentences:
3B-i's clause, then 3B-ii's three sentences.

Full worked example (3A + 3B-ii only, no named-APEC delineation issue):
> The soil investigation was conducted on November 17, 2025. 11 boreholes were advanced to a maximum depth of 6.0 m. Elevated background chloride was identified at 2 locations, with a maximum concentration of 150 mg/L. Vertical and lateral chloride delineation to the Tier 1 standard of 100 mg/L or to background levels was achieved. Section 5 provides a site-specific evaluation and justification of the background chloride.

Full worked example (3B-i "not achieved" + 3B-ii together):
> Vertical delineation to the Tier 1 standard of 100 mg/L chloride was not achieved at various locations within the well centre and DWDA. Elevated background chloride was identified at 5 locations, with a maximum concentration of 170 mg/L. Vertical and lateral chloride delineation to the Tier 1 standard of 100 mg/L or to background levels was achieved. Section 5 provides a site-specific evaluation and justification of the background chloride.

---

## Section 4 — Exceedance Summary + Conclusion (always present)

This replaces the old fixed "well centre / DWDA only" logic entirely.
**The set of named areas is fully data-driven** — read it from the `APEC`
column of the `Tier 1 Exceedances` sheet for this run, whatever it contains
(e.g. well centre, DWDA, EM anomaly for a wellsite; riser system, heater
tank, separator, flare stack, former infrastructure area, compressor
building for a facility). Do not assume any fixed pair or fixed list — the
areas differ by site type and by what was actually investigated this run.

### Step 1: Resolve the named areas

- Take the distinct `APEC` values from `Tier 1 Exceedances` for this run,
  excluding rows where `APEC` is `-` or `Background` (background chloride is
  already covered in Section 3B and never repeated here).
- **Match variant spellings tolerantly** the same way the previous version
  of this prompt did for "Well centre"/"DWDA" — normalize case and known
  synonyms (e.g. "Well Center"/"Well Centre Area"/"Wellhead" → "well
  centre"; "Drilling Waste Disposal Area (DWDA)"/"Drill Mud Disposal Area" →
  "DWDA") — and apply the same tolerant-matching approach to whatever other
  area names appear for this site. If a value doesn't clearly resolve to a
  sensible area name, don't silently guess — ask the user.

### Step 2: Classify each area

**Exclude `Chemical Group = 'Chloride'` rows entirely from this step.**
Chloride is a delineation story, not a per-area justification story — it is
already fully handled by Section 3B (Tier 1 chloride delineation and the
background chloride variant). Real Excel data shows chloride rows with a
blank `Justified` value even at named areas like the well centre or DWDA;
that blank does not mean "unresolved exceedance" in the Section 4 sense — it
means the row belongs to Section 3B's delineation narrative, not to Section
4's remediation/justification narrative. Mixing the two produces a false
"unresolved exceedance" reading. Only `Salinity` (EC/SAR/pH), `PHC`, `PAH`,
and `Metals` chemical groups are classified here.

For each resolved area, check its non-chloride rows in `Tier 1 Exceedances`:

- **No non-chloride rows at all, or all rows show no exceedance** — clean.
- **Has non-chloride exceedance rows** — group by `Chemical Group` (salinity,
  PHC, PAH, metals, etc.) and check `Justified (yes/No)`:
  - All rows `Yes` with the **same** `Justification` — justified; state the
    single reason in normalized prose (e.g. "assumed to be naturally
    occurring", "low risk", "marginal and isolated").
  - All rows `Yes` but with **different** `Justification` values (e.g. some
    rows "Naturally Occuring", others "Low Risk" within the same chemical
    group at the same area — this happens in real data, seen at 08-13's well
    centre) — still justified overall; combine the distinct reasons with
    "and"/"or" rather than picking one arbitrarily (e.g. "assumed to be
    naturally occurring and low risk"). Don't drop a reason just because
    another row in the group has a different one.
  - Any row blank/`No` — that chemical group is **not** justified at that
    area, even if other rows for the same area/group happened to be
    justified — state that the exceedance was identified and is
    unresolved/not justified.

### Step 3: Compose the sentence(s)

Combine areas that share the same status into one clause rather than
repeating a sentence per area; describe areas with different outcomes in
separate clauses/sentences. Attach a volume clause where a volume estimate
exists — either inline on the specific area's sentence (when there's a
single clearly-responsible area) or as its own standalone sentence
immediately after the area descriptions (when volume covers the run as a
whole). Both forms are acceptable; pick whichever reads more naturally for
the number of areas involved.

**Clean area: name it explicitly, or fold it into a generic phrase?**
- If **every** resolved area has an exceedance, there is no specific area to
  call "clean" — close with the generic "...while the remaining soil
  concentrations and salinity parameters complied with the applicable Tier 1
  guidelines" clause (or omit it if that reads redundantly).
- If **some but not all** resolved areas are clean, name the clean area(s)
  explicitly ("No exceedances were identified at [area]," or "...at [area A]
  or [area B]" when grouping more than one clean area) — don't fold a
  specific named area into the generic phrase.

Examples (patterns to follow, not exhaustive — construct the right
combination for whatever the data actually shows):

> Soil concentrations and salinity parameters at all sampled locations were below the applicable Tier 1 guidelines.

> Salinity exceedances were identified at the well centre and EM anomaly, while the remaining soil concentrations and salinity parameters complied with the applicable Tier 1 guidelines.

> Salinity exceedances were identified at the well centre area, while salinity, hydrocarbon, and metal exceedances were identified at the DWDA. No exceedances were identified at the EM anomaly.

> Salinity and metal exceedances were identified in the DWDA. The salinity exceedances are associated with high sulphate and low chloride concentrations and were assumed to be naturally occurring. The metal exceedance is marginal, isolated, and assumed to be naturally occurring and of low risk.

> Soil exceedances were not identified at the well centre or EM anomaly. However, salinity and hydrocarbon exceedances were identified at the DWDA. The estimated impact volume is 400 m³ (720 tonnes).

> No soil exceedances were identified at the riser system, heater tank, separator, or flare stack. At the former infrastructure area, a marginal exceedance justification was applied to a salinity exceedance. At the compressor building, salinity and PHC exceedances were identified, with an estimated volume of 345 m³ (621 tonnes).

### Step 4: Conclusion sentence (always the final sentence, "Based on these results, ...")

**Decision rule — two independent checks, combined.** Don't let the
non-chloride exceedance status alone decide the conclusion — Section 3B's
chloride-delineation outcome (3A/3B-i, `not achieved` vs `achieved`) is a
second, independent axis that can leave outstanding work even when every
named-area exceedance is fully justified. (This is exactly what happens at
08-13: well centre's salinity exceedances are all justified, but standard
chloride delineation at the well centre/DWDA was separately *not achieved*
— the conclusion has to carry both facts, not drop one.)

**Step A — base action, from Step 2's non-chloride classification alone:**

1. If **any** resolved area has an unresolved non-chloride exceedance
   (blank/`No` in `Justified`) → **Required**.
2. Else, if non-chloride exceedances existed anywhere but **all** of them
   were justified → **Not recommended**.
3. Else (no non-chloride exceedances at any resolved area) → **Not
   required**, pending Step B.

**Step B — delineation caveat.** Check Section 3B-i's outcome independently
of Step A:

- If Step A landed on **Required**, no caveat is needed — "further
  remediation action is required" already covers any open delineation work
  at that point; don't append anything more.
- If Step A landed on **Not recommended** or **Not required**, and 3B-i's
  chloride delineation was **not** fully achieved, append a delineation
  caveat clause rather than letting the base sentence imply the site is
  fully closed out.

Sentence for each resulting combination:

- **Required** (Step A only):
  > Based on these results, further remediation action is required.
- **Not recommended, delineation achieved:**
  > Based on these results, no further remedial action is recommended.
- **Not recommended, delineation NOT achieved** (justified exceedances, but
  chloride delineation is still outstanding — the 08-13 case):
  > Based on these results, no further remedial action is recommended for the justified exceedances; however, further investigation is warranted to complete the chloride delineation.
- **Not required, delineation achieved:**
  > Based on these results, no further remedial action is required.
- **Not required, delineation NOT achieved** (no exceedances at all, but
  chloride delineation is still outstanding):
  > Based on these results, further investigation may be warranted to complete the chloride delineation.

**Note on wording:** the examples consistently pair "remedial action" with
*not required* / *not recommended*, and "remediation action" with
*required*. This is preserved exactly as given, per your call to keep the
switch as-is rather than standardizing on one spelling — flag if you'd
rather this always read "remedial action."

---

## Output

Produce one `replace_between` operation with all paragraphs/sentences from
Sections 1–4, in order, as `body` blocks.

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_EXEC_SUMMARY_START>",
  "end_placeholder":   "<INSERT_EXEC_SUMMARY_END>",
  "blocks": [
    {"style": "body", "text": "Section 1 — Facility paragraph..."},
    {"style": "body", "text": "Section 2 — History + Purpose paragraph... (omit if no previous assessments)"},
    {"style": "body", "text": "Section 3 — Recent Investigation Summary + Chloride Delineation (3A + 3B combined; may be one paragraph or split into two body blocks)..."},
    {"style": "body", "text": "Section 4 — Exceedance Summary + Conclusion (area classification sentences + final 'Based on these results...' sentence)..."}
  ]
}
```
