# Intake Quiz — EBM Routine Phase 2 ESA

Ask the user the following questions before running any report generation steps.
Use the answers to determine which operations to include in the final JSON array.

The ABAData Word doc is read once during the unified extraction pass (Step 1c —
see `prompts/site_facts_cache.md`) into `site_facts.json`'s `abadata` block
and top-level `site_type` key. Q1 and Q10 are auto-derived from that cached
data and should not be asked.

---

## Questions

### Q0 — Identity reconciliation: one LLD/LSD, one UWI, one client name (auto-derived — only ask if sources disagree)

This site has up to **four independent sources** that bear on its legal
land description, and **two** for its UWI — and this skill has already hit
real sites where they don't agree (see `prompts/site_facts_cache.md`'s note
on the Phase 1 ESA LLD/UWI mismatch). The goal of Q0 is to end this run with
**exactly one** reconciled `site_lsd` and **exactly one** reconciled `uwi`
in `site_facts.json` — not several different LLDs floating around depending
on which section of the report you're reading. `generate_ebm_report.py`
needs both as explicit arguments (`site_lsd` as CLI arg 4, feeding both the
cover page **and** Section 2.1's Wellsite table — see
`generate_section2_1()`'s `site_lsd` parameter) so nothing downstream reads
a raw per-source field like `abadata.surface_location` directly for
display; everything reads the one reconciled value instead. This is
**never** an intake question the user has to answer up front — only the
mismatch cases below actually stop and ask.

**Note on the ABAData doc's two location-bearing fields:** ABAData has no
"legal land description" field of its own. It has two separate rows —
`abadata.uwi` ("Full UWI") and `abadata.surface_location` ("Surface
Location") — both of which bear on the site's location and both of which
feed into the `site_lsd` reconciliation below (`abadata.uwi` normalized to
the same comparison format first), alongside the borehole logs and
`phase1_esa.lld`. Do not treat `abadata.surface_location` as equivalent to
`legal_land_description` elsewhere in the skill — `legal_land_description`
only exists under `phase1_esa`, not under `abadata`.

#### Site LSD

Sources, gathered from the already-extracted `site_facts.json` (no PDF read
happens at this step — see `prompts/site_facts_cache.md`):

| Source | Field | Format note |
|---|---|---|
| Borehole log header(s) | `borehole_logs.log_sets[].site_location_header` | strip leading `102/` and trailing `M` before comparing (e.g. `102/08-13-016-01 W4M` → `08-13-016-01 W4`) |
| ABAData doc | `abadata.surface_location` | format not guaranteed — may be DLS style or UWI style; strip any `102/`-style prefix and trailing `M` the same way as the other sources before comparing |
| ABAData doc | `abadata.uwi` | UWI-formatted (e.g. `102/08-13-016-01W4/0`) — the LLD is the **middle segment between the first and second `/`** (e.g. `102/08-13-016-01W4/0` → `08-13-016-01W4`); take that segment directly, then apply the same whitespace normalization as the other sources |
| Phase 1 ESA (if provided) | `phase1_esa.lld` | may carry the same `102/`/`M` formatting as the borehole logs — strip the same way |

1. Normalize every available value (strip `102/` prefix, trailing `M`,
   collapse whitespace to the template's expected `08-13-016-01 W4` style —
   space before the meridian letter) before comparing. `abadata.uwi` and
   `abadata.surface_location` are two independent sources from the same
   document — normalize and compare each on its own, don't assume they
   agree with each other just because they came from the same doc.
2. If multiple `borehole_logs.log_sets[]` entries are present (e.g. both a
   2023 and a 2024 set), they count as one source for this comparison — they
   should already agree with each other; if they don't, treat that as a
   disagreement too (see step 4).
3. **If every available normalized value agrees**, use it as `site_lsd`. No
   question.
4. **If any normalized values disagree**, ask the user once, showing every
   disagreeing source and its value: *"The legal land description isn't
   consistent across sources: borehole logs show {value}, ABAData surface
   location shows {value}, ABAData UWI shows {value}, Phase 1 ESA shows
   {value}. Which one should the report use?"* — omit any source that
   wasn't provided this run. Use their answer as the final `site_lsd`.
5. **If no source yields a value at all**, ask the user directly: "What is
   the legal land description for the cover page?" — a rare fallback, not
   the normal path.

#### UWI

Sources — only two, since the borehole log header doesn't carry a UWI:

| Source | Field |
|---|---|
| ABAData doc | `abadata.uwi` |
| Phase 1 ESA (if provided) | `phase1_esa.uwi` |

Same reconciliation pattern as site LSD, at a smaller scale:
1. If both are present and agree (verbatim, or differing only in
   leading-zero/slash formatting — normalize before comparing), use that
   value as the top-level `uwi`. No question.
2. If only one source is present, use it. No question.
3. If both are present and disagree, ask the user once: *"The UWI isn't
   consistent across sources: ABAData shows {abadata.uwi}, Phase 1 ESA shows
   {phase1_esa.uwi}. Which one should the report use?"* Use their answer as
   the final `uwi`.
4. If neither source has a value, leave `uwi` as `null` — don't block the
   run over it; nothing currently reads it downstream (see below).

Store the reconciled value as a new top-level `uwi` key in `site_facts.json`
(alongside `site_lsd` and `client_name`) once resolved. Nothing in
`generate_ebm_report.py` or any section prompt currently displays `uwi`
anywhere in the report — this reconciliation exists so there's one correct,
agreed-upon value on record if/when something downstream needs it, not
because the report shows it today.

#### Client name

Unaffected by the reconciliation above — still just:
1. `borehole_logs.log_sets[].client_name_header`, primary source.
2. If borehole logs weren't provided this run, use `abadata.licensee`
   directly instead.
3. If neither has a value, ask the user directly: "What is the client name
   for the cover page?"

Pass the reconciled `site_lsd` and `client_name` as CLI args 4 and 5 when
invoking the generator (see SKILL.md Step 2) — `site_lsd` now also flows
into Section 2.1's Wellsite table via `generate_section2_1()`'s `site_lsd`
parameter, not just the cover page. The cover page's "Prepared For:"
address block is looked up entirely in Python from `prompts/clients/*.md`
(see SKILL.md's Reference Files table) — this is not an intake question or
a Claude step; if `client_name` doesn't match any file there, the cover
page falls back to printing the bare name with no address block, which is
expected if the client isn't on record yet, not a bug to work around by
asking the user for their mailing address.

---

### Q1 — Site type (auto-derived from ABAData doc)

Auto-derive from the ABAData doc's `license_status` field (free text, e.g.
"Abandoned (status date: January 25, 2021)" — match on the plain-English
status word, not an exact code):
- Contains "Abandoned", "Suspended", "Active", or any other well-status
  wording → **wellsite**
- No ABAData doc provided, or the status indicates a facility asset → ask
  the user

Store this as `site_type` in `site_facts.json` (see
`prompts/site_facts_cache.md`). Section 2.1 (which of the Wellsite/Facility
table blocks to keep, and filling it) is entirely Python-authored —
`generate_section2_1()` in `scripts/generate_ebm_report.py` reads
`site_type` and the cached `abadata` facts directly and needs no Claude
operation at all. There is no `s2_1_facility.md` prompt file for this
reason (see the "Python-authored sections" table in SKILL.md).

---

### Q21 — Report type: Presence/Absence P2 or Standard Tier 1 P1 (always ask — not derivable from any source)

Drives Section 1.1's objective-sentence variant. Section 1.1 is now written by
the generator (`generate_section1_1()`); the answer is passed as the generator's
8th argument `report_type` (`standard` or `presence_absence`). Ask this **before**
running the generator. Nothing in `site_facts.json`, the
Excel workbook, or any source PDF indicates which of these two report types
this run is — always ask, every run:

> "Is this a Presence/Absence Phase 2 assessment, or a Standard Tier 1
> routine report (characterization + delineation + closure evaluation)?"

Two possible answers, each selecting one fixed objective sentence verbatim
(the scope-of-work bullet list after it is identical either way, fixed in
`generate_section1_1()`):
- **Presence/Absence P2** → "The objective of the assessment was to
  investigate each area of potential environmental concern (APEC) for the
  presence or absence of the contaminants of potential concern (CoPCs)."
- **Standard Tier 1 P1** → "The objectives of the assessment were to
  characterize soil quality at the identified areas of potential
  environmental concern (APECs), delineate the extent of impacts for the
  relevant contaminants of potential concern (CoPCs), and evaluate the
  site for closure."

---

### Q22 — DWDA (Section 4.2): now handled by the generator

Sections 4.2's DWDA and DWDA NIL FINDINGS subsections are written by
`generate_section4_2_dwda()` in `generate_ebm_report.py` (the old prompt files
were retired). The DWDA exploratory boreholes and their depth are asked **here
in the intake quiz and nowhere else** (never read from the borehole logs):

- **(a) Exploratory boreholes — from the workbook if possible, otherwise asked.**
  If `Borehole Rationale` has a "DWDA Search" row, its boreholes are used as the
  exploratory boreholes and nothing is asked about IDs. Otherwise, if the first
  run's log says `DWDA_EXPLORATORY_NEEDED`, ask: "Were any exploratory boreholes
  advanced to locate a drilling waste disposal area? If so, which (IDs)?" and
  pass the list as the generator's 10th argument `exploratory_boreholes` (e.g.
  `BH26-25` or `BH26-01,BH26-02`; use `""` for none).
- **(b) Maximum depth — always asked when exploratory boreholes exist** (from
  the "DWDA Search" row or from (a)), i.e. when the log says `DWDA_DEPTH_NEEDED`
  or the subsection is written: "To what maximum depth (mbgs) were the DWDA
  exploratory boreholes advanced?" → 11th argument `exploratory_max_depth_m`
  (e.g. `6.0`). Without it the report shows a bracketed `[X]`.
- **(c-pre) Which subsection — auto-derived.**
  - "DWDA-Char..." / "DWDA-Delin..." rows in `Borehole Rationale` → the "found"
    subsection.
  - No such rows but exploratory boreholes exist (from the "DWDA Search" row or
    the quiz) → the NIL FINDINGS subsection.
  - No DWDA-Char/Delin rows **and** no exploratory boreholes → **neither**
    subsection is written (both headings removed).
  After answering (a)/(b), re-run the generator (under a second).
- **(c) EM survey — asked only when the NIL subsection was written.** Run the generator with the default (`em_survey = none`, Variant
  A). If its log says "NIL variant", ask: "Was a geophysical (EM) survey
  conducted? If so, did it show a response indicative of a drilling waste
  disposal area?" and re-run the generator (under a second) with
  `em_survey` = `none` (no survey, Variant A), `no_anomaly` (Variant B) or
  `anomaly` (anomaly not attributed to a DWDA, Variant C) as argument 9.
  Citation, appendix letter, figure number and region stay literal placeholders.

---

## Running tally of intake questions

| # | Question | Answer drives |
|---|---|---|
| Q0 | ~~Removed — site LSD and client name auto-derived from borehole log PDFs (primary) or ABAData Word doc (fallback); only asked if neither source has it~~ | Cover page title and "Prepared For" block (CLI args 4/5 to `generate_ebm_report.py`) |
| Q1 | ~~Removed — Site type auto-derived from ABAData Word doc `license_status` field~~ | Which Section 2.1 table to keep / delete |
| Q2 | ~~Removed — Previous assessments auto-derived from uploaded Phase 1 ESA and other assessment PDFs provided at the start of each run~~ | Exec summary previous-assessments paragraph |
| Q2b | ~~Removed — derived from whether any `other_previous_assessments[]`/`phase1_esa` entry is itself a prior soil investigation or Phase 2 ESA (same data Q2 already reads); if none is, this is the first investigation~~ | "recent" qualifier + singular/plural phrasing in Section 3 (exec summary) |
| Q3 | ~~Removed — both vertical and lateral chloride delineation status now auto-derived from `chloride_delineation_data` (borehole UTM coordinates + closure flags), the same computation Section 4.3 uses. See `prompts/exec_summary.md` 3B-i and `prompts/s4_3_chloride.md`~~ | Exec summary delineation sentence |
| Q4 | ~~Removed — `exec_summary.md`'s Section 4 Step 2 already classifies every named area's non-chloride exceedances as clean/justified/unresolved from `Tier 1 Exceedances`' `Justified`/`Justification` columns~~ | Exec summary justification sentence |
| Q5 | ~~Removed — `exec_summary.md`'s Section 4 Step 4 decision rule already computes this deterministically from Step 2's classification + Section 3B-i's delineation outcome. `s8_summary.md` must read this same computed value, not ask fresh~~ | Exec summary conclusion sentence |
| Q6 | If required: what is the estimated volume of impact (m³ and tonnes)? | Exec summary volume sentence |
| Q7 | ~~Removed — Location auto-derived from Phaseview PDF (nearest settlement + distance + municipality from Site Reconnaissance Report)~~ | Section 2.3.1 Location cell |
| Q8 | ~~Removed — Land Use auto-derived from AER Phase 1 ESA form (surrounding Land Use checkboxes from Site Visit section)~~ | Section 2.3.1 Land Use cell |
| Q9 | ~~Removed — APECs derived automatically from distinct non-Background APEC values in `EC & SAR Rating Categories` sheet~~ | Section 2.3.1 Areas of Environmental Concern cell |
| Q10 | ~~Removed — Initial COPCs auto-derived from ABAData Word doc production totals (dry gas → Salinity, PHC F1–F2; gas+oil → Salinity, PHC F1–F4, BTEX; etc.)~~ | Section 2.3.1 Initial COPCs cell |
| Q11 | ~~Removed — derived as the chemical group(s) driving exec_summary Step 2's "unresolved" classification (blank/No in `Justified`); "None" if nothing triggers it~~ | Section 2.3.1 Remaining COCs cell |
| Q12 | Is background chloride applicable at this site? (yes/no only — site-specific statement is handled separately after report generation) | **No longer drives Section 2.4** — the new template removed Background Chloride from the Regional Information table entirely (see `generate_section2_4()`, Python). That content now lives in its own "Background Chloride"/"Background Chloride Summary" subsections elsewhere in the document, which don't have `<INSERT_*>` markers yet — Q12 is unused until that section is migrated. |
| Q13 | ~~Removed — fully auto-derived from `chloride_delineation_data` (vertical, lateral, and background all mechanical now — see `prompts/s4_3_chloride.md`)~~ | Section 4.3 paragraph selection |
| Q14 | *(Only if background chloride detected in data AND outcome is NOT_ACHIEVED_BACKGROUND or ACHIEVED_ALL with background)* What is the site-specific chloride threshold used for delineation (mg/kg and/or mg/L)? | Section 4.3 threshold value |
| Q17 | ~~Removed — directions computed from borehole log survey coordinates (EASTING/NORTHING), not asked. See `prompts/s5_2_transport.md` Step 5.~~ | Section 5.2 bullet 5 direction clause |
| Q18 | ~~Removed — the Section 5.2 closing paragraph is authored automatically from the computed depth facts (max investigation depth, depth of impact vs. estimated water table). See `prompts/s5_2_transport.md` Step 4. Never ask the user.~~ | Section 5.2 closing paragraphs |
| Q19 | ~~Removed — Section 5.4 uses a fixed template sentence with the background BH list auto-derived from unique Sample IDs with APEC = 'Background' in the `Tier 1 Exceedances` sheet (sorted, joined with commas and "and"). Never ask the user for this.~~ | Section 5.4 background BH sentence |
| Q20 | *(Reduced — auto-derived for every APEC, no free-form list needed)* `justified`/`anthropogenic`/`comparable_background` come from exec_summary Step 2's per-area classification; `nil_findings` comes from the same "was anything actually sampled" signal as Q22(b) (only applies to search-then-sample APECs like DWDA) — see `prompts/s8_summary.md`. Only ask if a specific APEC's verdict is genuinely ambiguous after auto-derivation. | Section 8 per-APEC bullets |
| Q21 | Is this a Presence/Absence Phase 2 assessment, or a Standard Tier 1 routine report? | Section 1.1 objective-sentence variant |
| Q22 | *(a: exploratory borehole IDs, asked only if there is no DWDA Search row; b: their max depth)* *(c: asked only when the NIL subsection was written)* Was an EM survey done and did it show an anomaly? | Section 4.2's DWDA/DWDA-NIL subsections (which one gets content, and DWDA-NIL's variant) |
