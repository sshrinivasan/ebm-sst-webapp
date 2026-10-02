# Section 4.3 — Tier 1 Chloride Delineation

## Placeholders

Three markers, all inside the "Tier 1 Chloride Delineation" `Heading 2` —
this replaces the old single `<INSERT_4_3_HERE>`/`insert_blocks` design,
which no longer matches the live template
(`Automation Template_20260924.docx`):

- `<INSERT_43_START>` / `<INSERT_43_END>` — `replace_between`. Brackets the
  raw example paragraphs currently sitting in the template; replace with
  the selected variant's real prose (see Step 4).
- `<INSERT_43_NA_PROFILE_START>` / `<INSERT_43_NA_PROFILE_END>` —
  `replace_between` range, right after the "Figure 1. Soil Chloride
  Profile" caption, wrapping the template's own static placeholder figure.
  This one is **not** a Claude-authored operation — it's handled entirely,
  mechanically, by `generate_section4_3_na_profile()` in
  `generate_ebm_report.py` during the same pipeline run that produces
  `excel_data.json`. Deletes everything from START through END inclusive
  (which removes the template's placeholder figure along with the markers,
  regardless of what's sitting between them), then inserts the real
  CL_DELINEATION/*.png figure(s) from the session's figures zip as a
  borderless grid (2 columns max). If the zip has no CL_DELINEATION
  figures, inserts "Not applicable — no vertical chloride profile figures
  were provided for this site." instead. Claude does not touch this
  marker pair directly; it's already resolved by the time excel_data.json
  and the partial docx exist.
  (This used to be a single standalone `<INSERT_43_NA_PROFILE>` marker
  resolved via `op_replace_text` — changed to a START/END range because a
  single-point marker can't safely remove the template's own placeholder
  figure sitting next to it; a range deletes everything between the pair
  regardless of what's there. If the template is ever rebuilt from scratch
  and only the single-point form exists, the script falls through to
  "not found — skipping" and the placeholder figure will need a human to
  remove it once from the template.)

## Data source

Read `excel_data.json`'s `chloride_delineation_data` key — computed by
`compute_chloride_delineation_data()` in `scripts/generate_ebm_report.py`,
per the methodology below (Hex's notes, reduced to a deterministic
algorithm — see NOTES.md for the original notes this was built from).
`None` if the workbook has neither an `EC & SAR Rating Categories` nor a
`Borehole_Characteristics` sheet — treat that as "can't compute this
section at all," not as NIL; flag it rather than guessing a NIL variant.

```json
{
  "samples_collected": true,
  "all_below_100": false,
  "max_cl_mg_l": 3000.0, "max_cl_borehole": "BH24-2", "max_cl_depth_m": 1.2,
  "vertical_status": "not_achieved",
  "vertical_overrides": [
    {"failing_borehole": "BH24-10", "failing_depth_m": 4.5, "failing_cl_mg_l": 200.0,
     "comparison_borehole": "BH24-1", "comparison_cl_mg_l": 510.0, "distance_m": 14.5}
  ],
  "vertical_unresolved": ["BH24-5"],
  "lateral_status": {
    "north": {"status": "achieved", "borehole": "BH24-9", "cl_mg_l": 19.0, "depth_m": 2.0},
    "east": {"status": "no_coverage", "borehole": null, "cl_mg_l": null, "depth_m": null}
  },
  "background_elevated": true
}
```

### Field reference

- `samples_collected` — `false` only when there are literally zero
  non-Background/non-Unassigned boreholes at all (the whole site has
  nothing to delineate for chloride, distinct from "sampled but clean").
  Drives the `NIL_NO_SAMPLES` variant.
- `all_below_100` — `true` when the worst-case chloride across every
  impacted borehole/depth never reaches 100 mg/L. Drives `NIL_BELOW_100`.
- `max_cl_mg_l` / `max_cl_borehole` / `max_cl_depth_m` — the site's
  worst-case chloride reading among impacted (non-Background,
  non-Unassigned) boreholes. This is the "worst-case chloride
  concentrations were observed..." sentence's source.
- `vertical_status` — one of `achieved` / `achieved_with_override` /
  `not_achieved` / `no_data` (`no_data` only when `samples_collected` is
  `false`). See "Vertical delineation" below for how this was computed —
  in particular, `achieved_with_override` boreholes are **not** a
  delineation failure worth mentioning in the prose; treat them the same
  as `achieved` in the sentence, since the override already resolved them.
- `vertical_overrides` — the specific borehole pairs where a shallow
  closure failure was excused by a nearer, comparable-or-higher-chloride
  borehole. Available for context/footnoting, but the summary sentence
  doesn't need to spell out the override mechanics — just state vertical
  delineation was achieved.
- `vertical_unresolved` — boreholes where vertical delineation genuinely
  was **not** achieved (failed closure, no override found). Name these
  explicitly in the `not_achieved` variant.
- `lateral_status` — one entry per compass direction (8-point: north,
  northeast, east, southeast, south, southwest, west, northwest), each
  `achieved` / `not_achieved` / `no_coverage`. `no_coverage` means no
  Background borehole exists in that direction at all — **do not** claim
  delineation was achieved there; name it as a direction with no data if
  the prose needs to mention it, but the standard example wording only
  ever names directions where delineation genuinely was or wasn't
  achieved, so `no_coverage` directions are usually just omitted rather
  than narrated.
- `background_elevated` — `true` if any direction's Background borehole
  itself exceeds 100 mg/L at a comparable depth. This is what triggers the
  `NOT_ACHIEVED_BACKGROUND` variant and the Q14 threshold ask (see below) —
  distinct from a *named-area* exceedance, which is Section 4.2's story,
  not this one.

## Methodology (how Python computes the above)

**Delineation standard**: Tier 1 chloride screening value of 100 mg/L,
always, for every site this computes — a site-specific background
threshold (Q14) only ever *supplements* this in prose, it never changes
what the Python math itself checks against. If a future site needs a
different standard checked mechanically, that's a real feature request,
not a guess to make here.

**Vertical delineation** — per Hex's notes, reduced to code:
1. A borehole is closed if `Borehole_Characteristics`'s `Deep Vertical
   Closure` is `Yes`.
2. For every non-closed ("failing") impacted borehole, find the single
   *nearest* other impacted borehole (by UTM easting/northing distance —
   coordinates from `site_facts.json`'s `borehole_logs.boreholes[]`) that
   is itself closed (or never impacted at all). Compare chloride at a
   depth within **±1.0 m** of the failing borehole's `Bottom of Impact`.
   If the comparison borehole's chloride at that depth is equal or higher,
   the failure is excused (an override) — this never asks a human to
   confirm; there is no separate proximity distance cutoff, "nearest
   impacted borehole" always stands in for "close enough" per standing
   decision. If the nearest borehole's chloride there is lower, or no
   comparable-depth reading exists for it, the failure stands.
3. Aggregate: no failing boreholes -> `achieved`. All failures overridden
   -> `achieved_with_override`. Any failure not overridden ->
   `not_achieved`.

**Lateral delineation** — per Hex's notes:
1. Compute the centroid (mean easting/northing) of all impacted boreholes.
2. Bucket every Background borehole into one of 8 compass directions from
   that centroid (`_bearing_to_compass8()` — same centroid+bearing math as
   `prompts/s5_2_transport.md`'s Step 3, just an 8-point bucket instead of
   16-point, matching this template's example wording).
3. For each direction with at least one Background borehole, compare its
   chloride at a depth within ±1.0 m of the site's worst-case impacted
   depth (`max_cl_depth_m`) against 100 mg/L. Below -> `achieved` in that
   direction; at/above -> `not_achieved` (this is what `background_elevated`
   flags).
4. A direction with **no** Background borehole at all is `no_coverage` —
   there is no spatial evidence either way, so never claim delineation
   there.

## Step 3 — Site-specific background threshold (intake Q14, conditional)

**Only if** `background_elevated` is `true` **and** you're writing the
`NOT_ACHIEVED_BACKGROUND` variant below. Ask: *"What is the site-specific
chloride threshold used for delineation (mg/kg and/or mg/L)?"* — this
value comes from the background statistics (Appendix E) and cannot be
computed from the current Excel output (no column carries it yet — see
NOTES.md's Excel-enhancement todo). Not needed for any other variant.

## Step 4 — Select and populate the paragraph(s)

Pick based on `samples_collected` / `all_below_100` / `vertical_status` /
`lateral_status` / `background_elevated`, in this order:

### `samples_collected = false` -> NIL_NO_SAMPLES
> No indications of soil disturbance, drilling waste, or contaminant impacts were identified in any of the exploratory boreholes. As such, samples were not collected or analyzed.

### `all_below_100 = true` -> NIL_BELOW_100
> No indications of soil disturbance, drilling waste, or contaminant impacts were identified in any of the exploratory boreholes, and all samples had chloride concentrations below the Tier 1 chloride delineation screening value of 100 mg/L. The maximum chloride concentration at each borehole location is illustrated in Figure 2.

### Vertical achieved (or achieved_with_override), all lateral directions with coverage `achieved`, `background_elevated = false` -> ACHIEVED_ALL
> Lateral delineation to the Tier 1 standard of 100 mg/L chloride was achieved in all cardinal directions, as illustrated by the 100 mg/L contour in Figure 2. Vertical delineation of chloride impacts is shown in Table 4 and in Figure 1 below, which presents the vertical soil chloride profile.

### Same as above but `background_elevated = true` (achieved relative to background, not Tier 1 itself) -> ACHIEVED_RELATIVE_TO_BACKGROUND
> Lateral delineation was achieved relative to local background conditions; however, concentrations exceeded the Tier 1 standard of 100 mg/L. A comprehensive analysis of the on-site background chloride is provided in Section 5, referencing the naturally occurring chloride, which is prevalent in the {region} region.
>
> For this site, the delineation criteria of {threshold from Q14} was used to define the impact area, illustrated by the {threshold} contour in Figure 2. The vertical delineation of chloride impacts is shown in Table 4 and in Figure 1 below, which presents the vertical soil chloride profile.

`{region}` — use the site's actual region name if established elsewhere in
the document (e.g. Section 2.4's natural subregion); leave as a literal
placeholder if not otherwise available. Never invent a region name.

### Vertical/lateral not achieved, cause is `background_elevated` -> NOT_ACHIEVED_BACKGROUND
> Lateral delineation to the Tier 1 standard of 100 mg/L chloride was not achieved due to the naturally occurring chloride identified at {background borehole(s) from the not_achieved lateral direction(s)} (Section 6). However, vertical delineation was achieved at {an achieved/overridden borehole}, and field screening results from the surrounding boreholes do not indicate any chloride impacts. Additionally, the EM31 survey showed no indication of on-site hotspots.

Only include the EM31 sentence if an EM survey was actually part of this
run's data (see Q22(c)/`s4_2_dwda_nil.md`) — leave it out otherwise rather
than asserting a survey that didn't happen.

### `vertical_status = not_achieved`, lateral achieved in some directions but not others (not a background cause) -> PARTIAL_MIXED
> Lateral chloride delineation to the Tier 1 standard of 100 mg/L chloride was achieved to the {achieved directions}, although not at equivalent depths to the worst-case impacts. Lateral delineation was not achieved to the {not_achieved directions} (Figure 5), and vertical delineation was not achieved at {vertical_unresolved boreholes, named by area if the area names are known}.
>
> The worst-case chloride concentrations were observed {location description} at {max_cl_borehole}, where concentrations as high as {max_cl_mg_l} mg/L were measured at {max_cl_depth_m} mbgs.

List achieved/not-achieved directions from `lateral_status`; omit any
`no_coverage` direction from both lists rather than guessing which side it
belongs on.

### Genuine data-coverage gap (a resolved vertical/lateral failure with no comparison data available at all — `vertical_unresolved` boreholes with no override candidate found, or a lateral direction that's `no_coverage` right where the worst-case impact is) -> NOT_ACHIEVED_INSUFFICIENT
> Lateral delineation to the Tier 1 standard of 100 mg/L chloride was not achieved due to {reason — insufficient background borehole coverage in the relevant direction(s), or no comparable-depth sample at the failing borehole}. However, vertical delineation was achieved at {borehole(s)}, and field screening results from the surrounding boreholes do not indicate any chloride impacts.

Only use this variant when the shortfall is genuinely a data gap, not a
real elevated reading — don't reach for this as a catch-all just because
the outcome is complex; prefer `PARTIAL_MIXED` or `ACHIEVED_ALL` when the
data actually supports one of those.

---

## Output

```json
{
  "op": "replace_between",
  "start_placeholder": "<INSERT_43_START>",
  "end_placeholder": "<INSERT_43_END>",
  "blocks": [
    {"style": "body", "text": "[selected paragraph text — one or more body blocks]"}
  ]
}
```

That's the only operation Claude submits for this section. The
`<INSERT_43_NA_PROFILE_START>`/`_END` figure grid is not a Claude
operation at all — it's already resolved mechanically by
`generate_section4_3_na_profile()` before excel_data.json exists (see
"Placeholders" above).

---

## Step 5 — View the CL_DELINEATION figures and cross-check the text (always)

The figures are inserted mechanically, but the prose above is written by
Claude, so before finishing this section view every `CL_DELINEATION/*.png`
in the figures zip and check that the wording agrees with what they show:

- Boreholes the text calls "vertical delineation not achieved" should visibly
  stay above 100 mg/L at their deepest sample; boreholes called "achieved"
  should visibly close below it.
- The "worst-case" borehole/concentration quoted should be the highest point
  visible. The Python computation excludes unassigned boreholes (APEC blank or
  "-"), so a figure can show a higher value than the quoted worst case (08-13:
  BH23-01 at ~5800 mg/L vs. BH24-2 at 3000 mg/L). Keep the wording
  "among the boreholes assigned to an APEC" in that case and list it in the
  Practitioner Information hand-off.
- All CL_DELINEATION images sit under the template's single static
  "Figure 1" caption. That is the accepted behaviour (decision 2026-09-30) —
  do not add per-image captions.
