# Section 8 — Summary and Conclusions

## Placeholder

`<INSERT_8_START>` / `<INSERT_8_END>` — Op type: `replace_between`. Both markers
exist in `Automation Template_20260924.docx`. Claude-authored (not Python): the
wording needs interpretation of the whole report's results.

The template block lists every possible variant separated by `OR` lines, with
example text from another site (`07-06-020-27 W4M`). **Pick exactly one variant
per sub-heading, write it with this site's facts, and drop every `OR` line, all
unused variants, and the variant labels ("No exceedances, no delineation
issues", etc.).** The replace_between removes the whole template block, so the
blocks submitted are the complete final section.

## Structure (always, in this order)

Sub-headings are bold `body` blocks (`"bold": true`); content lines are `bullet`
blocks except the opening sentence and the closing paragraph (`body`).

1. Opening sentence (`body`)
2. **Background SCARG** + 1 bullet
3. **Background Chloride Summary** + 1 bullet (only if background chloride > 100 mg/L; otherwise omit the heading and bullet)
4. **Tier 1 Exceedances Summary** + bullets
5. **Chloride Delineation** + 1 bullet (omit heading and bullet if no chloride delineation applies)
6. **Compliance statement** + 1 bullet
7. **Concluding statements** (bold `body`) + 1 closing paragraph (`body`)

## Data sources (all already computed — read, don't recompute or ask)

| Data | Source |
|---|---|
| Site identifier | the reconciled `site_lsd` (same as cover page / Section 1) |
| Background EC/SAR categories | `EC & SAR Rating Categories`, APEC = "Background" rows (same as Section 4.2.1) |
| Background chloride | `Tier 1 Exceedances`, APEC = "Background" + Chemical Group = "Chloride" |
| Per-area exceedance classification | `exec_summary.md` Section 4 Step 2 (chloride rows excluded) |
| Delineation outcome | `excel_data.json` → `chloride_delineation_data`, same reading as `exec_summary.md` 3B-i and `s4_3_chloride.md` |
| Remedial-action value | `exec_summary.md` Section 4 Step 4 (Step A + Step B) — reuse, never re-decide |
| Impact volume | intake Q6 |
| Phase 1 ESA provided | `site_facts.json` → `phase1_esa.provided` |

## 1. Opening sentence
> The following summarizes the results of the Phase 2 ESA at the {site_lsd} wellsite.

Use "Supplemental Phase 2 ESA" only if a previous Phase 2 ESA/soil investigation exists (same rule as the Exec Summary's "recent"). Site type = `site_facts.json` `site_type`.

## 2. Background SCARG — pick one
- No background samples collected: "Background samples were not collected, and the Good soil rating category was applied to both EC and SAR."
- Same single category for both: "The background evaluation identified the appropriate soil rating categories as {Cat} for both EC and SAR."
- Otherwise: "The background evaluation identified the appropriate soil rating categories as {EC range} for EC and {SAR range} for SAR." where a range is one category, or "Lowest to Highest" (order Good → Fair → Poor → Very Poor → Unsuitable). Use the same categories Section 4.2.1 reports.

## 3. Background Chloride Summary
> Elevated chloride concentrations were identified in background (maximum {max} mg/L). A site-specific evaluation and justification are provided in Section 5.

Use "Marginally elevated" only when the maximum is within ~1.25× of the 100 mg/L guideline; otherwise "Elevated".

## 4. Tier 1 Exceedances Summary — build from the per-area classification
Use the area names exactly as they appear elsewhere in the report. Non-chloride rows only.
- All areas clean: "No soil exceedances were identified in the {areas} assessments."
- Some areas justified: "Soil exceedances were identified in the {areas} assessments. However, all of the exceedances were assumed to be naturally occurring due to the low chloride concentrations." (use the actual `Justification Reason`, not always "naturally occurring")
- Some areas unjustified: name the chemical groups and areas: "{Salinity (EC and SAR)/hydrocarbon/metal} exceedances were identified in the {areas} assessments and have not been justified." Do **not** say they were justified.
- Clean areas get their own bullet: "No soil exceedances were identified in the {areas} assessments."
- DWDA search with nothing found (`dwda_data` null): "No evidence of impact or soil disturbance was identified in any of the exploratory boreholes. Therefore, samples were not collected or analyzed as part of the DWDA investigation."
- Minor justifications applied: "Minor exceedance justifications were applied to select samples in the {area} due to low chloride concentrations."
- Last bullet, only if any exceedance bullet is present: "All other parameters complied with the applicable Tier 1 guidelines."

## 5. Chloride Delineation — pick the variant that fits `chloride_delineation_data`
- All chloride < 100 mg/L: "Chloride concentrations for all of the characterization samples were less than 100 mg/L and delineation was not required."
- Achieved: "Chloride delineation to the Tier 1 standard of 100 mg/L was achieved."
- Achieved to Tier 1 or background: "Chloride delineation to the Tier 1 standard of 100 mg/L, or background levels, was achieved."
- Mixed: "Vertical delineation to the Tier 1 standard of 100 mg/L was achieved at {locations} but not at {locations}. Lateral delineation was achieved in all directions except {directions}[, which can be inferred from {basis}]." Name the actual boreholes/directions from `vertical_unresolved` and `lateral_status`; omit `no_coverage` directions; add the "inferred from ..." clause only when an EM/geophysical survey actually exists.
- Not achieved: same pattern, stating what was not achieved.
State plainly when background chloride is the reason a direction failed, with a Section 5 reference.

## 6. Compliance statement
- Phase 1 ESA provided: "All known APECs have been adequately characterized for the appropriate CoPCs. A comprehensive compliance review is provided in Section 7."
- **But** if delineation is not fully achieved, or an APEC named in the Phase 1 ESA (e.g. "well centre") does not appear among the Excel APECs, do not assert "adequately characterized": write "All known APECs have been characterized for the appropriate CoPCs; however, {what is incomplete}. A comprehensive compliance review is provided in Section 7." and list the point in the Practitioner Information hand-off.
- No Phase 1 ESA: the same sentence without the Phase 1 reference.

## 7. Concluding statements — one paragraph from the remedial-action value
- `not_required`, nothing found: "The ESA has provided sufficient information to support that there is no reasonable basis to suspect a substance release has occurred at the site that has caused, is causing, or may cause an adverse effect. Therefore, no further remedial actions are required."
- `not_required`/`not_recommended`, minor justified exceedances only: "Minor exceedances were identified and have been justified based on environmental risk. As such, the ESA has provided sufficient information to support that there is no reasonable basis to suspect a substance release has occurred at the site that has caused, is causing, or may cause an adverse effect. Therefore, no further remedial actions are required."
- `required`, volume known (Q6): "The ESA has confirmed that a substance release has occurred at the site, and further assessment, remedial measures, or exposure control measures are required. The impact volume is currently estimated at {m³} m³ ({tonnes} tonnes)."
- `required`, volume unknown: "The ESA has confirmed that a substance release has occurred at the site, and further assessment, remedial measures, or exposure control measures are required."

## Practitioner Information
Every Section 8 statement that rests on interpretation (compliance statement, background chloride qualifier, which variant was chosen and why) goes into the Practitioner Information hand-off (`prompts/practitioner_information.md`).

## Output
```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_8_START>",
  "end_placeholder": "<INSERT_8_END>",
  "blocks": [
    {"style": "body", "text": "Opening sentence..."},
    {"style": "body", "bold": true, "text": "Background SCARG"},
    {"style": "bullet", "text": "..."},
    {"style": "body", "bold": true, "text": "Background Chloride Summary"},
    {"style": "bullet", "text": "..."},
    {"style": "body", "bold": true, "text": "Tier 1 Exceedances Summary"},
    {"style": "bullet", "text": "..."},
    {"style": "body", "bold": true, "text": "Chloride Delineation"},
    {"style": "bullet", "text": "..."},
    {"style": "body", "bold": true, "text": "Compliance statement"},
    {"style": "bullet", "text": "..."},
    {"style": "body", "bold": true, "text": "Concluding statements"},
    {"style": "body", "text": "Closing paragraph..."}
  ]
}
```
