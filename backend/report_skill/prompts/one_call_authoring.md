# One-call authoring (Step 3): all Claude-written content in a single pass

After the generator has run (Step 2), Claude writes **one** file, `authored.json`, in **one pass**
(not one call per section). Python does everything else: it wraps the content in operations
(`scripts/assemble_operations.py`), applies them, and writes the Practitioner Information file.
Do **not** write operations, marker names or operation JSON yourself.

## Inputs (read once, up front)

- `excel_data.json` (from the generator): `ec_sar_data`, `dwda_data`, `chloride_delineation_data`,
  `section1_opening_sentence`, `section5_data`, `section5_present`, and the other computed payloads
- `site_facts.json`
- the intake answers (Q6 volume, Q14 background chloride, Q21 report type, Q22 DWDA/EM answers, etc.)
- the generator log (`SECTION5_PRESENT`, `DWDA_*` lines, ⚠ warnings)
- the figure images: the CL_DELINEATION figures (for 4.3) and, only when Section 5 is present,
  the BG_CHLORIDE figures (for 5.3)

## Output: `authored.json`

```json
{
  "exec_summary":   [blocks],
  "s4_3_chloride":  [blocks],
  "s5_1_phase1":    [blocks] | null,
  "s5_2_transport": [blocks] | null,
  "s5_3_footprint": [blocks] | null,
  "s8_summary":     [blocks],
  "practitioner_information": {
    "site": "...", "report": "<final .docx file name>",
    "check": ["..."], "uncertain": ["..."], "not_found": ["..."], "incomplete": ["..."]
  }
}
```

A block is `{"style": "heading3"|"body"|"bullet"|"smalltitle", "text": "..."}`, or
`{"style": "bullet", "runs": [{"text": "...", "bold": true}, {"text": "..."}]}` for bold runs.

## Wording rules: one prompt file per key (use them as written, but return blocks only)

| Key | Rules in | Notes |
|---|---|---|
| `exec_summary` | `exec_summary.md` | Copy `section1_opening_sentence` verbatim as instructed there |
| `s4_3_chloride` | `s4_3_chloride.md` | The figure grid is Python; write the text only; view the CL_DELINEATION figures first |
| `s5_1_phase1` | `s5_1_phase1.md` | `null` if `phase1_esa.provided` is false |
| `s5_2_transport` | `s5_2_transport.md` | |
| `s5_3_footprint` | `s5_3_footprint.md` | View the BG figures first; text only (figures and stale template text are handled in Python) |
| `s8_summary` | `s8_summary.md` | |
| `practitioner_information` | `practitioner_information.md` | Written last, after the sections above, from what you actually wrote |

Those prompt files also describe operation JSON (`replace_between`, `insert_blocks`,
`delete_paragraph`, ...). **Ignore every operation/marker instruction in them**; they only tell you
what the section should say. Return the blocks.

## Where the workbook-derived facts are (never open the workbook)

`excel_data.json` → `authoring_facts` holds everything the prompts used to read from Excel sheets:

| Need | Key |
|---|---|
| Borehole count (from the borehole logs), borehole IDs, max depth, workbook-only boreholes with no log | `authoring_facts.boreholes` (`count`, `ids`, `max_depth_mbgs`, `workbook_only_ids_no_log`) |
| Background EC / SAR categories, background chloride range (mg/kg and mg/L), sample/borehole counts | `authoring_facts.background` |
| Impact-area chloride: max (mg/kg), elevated depth range, elevated areas | `authoring_facts.impact_chloride` |
| Background chloride exceedances: boreholes, mg/kg range, max mg/L, depth range, compass direction of each from the impact centroid, boreholes with no coordinates | `authoring_facts.background_chloride_exceedances` |
| Per-APEC chemical groups exceeded and justification counts/reasons | `authoring_facts.per_apec_exceedances` |
| Delineation outcome | `chloride_delineation_data` |
| Borehole-log facts (mottling, water table, coordinates, depths) | `site_facts.json` → `borehole_logs` |

| Borehole Rationale rows (area label, its boreholes, analyzed panel) | `authoring_facts.areas` |
| Unassigned boreholes: max chloride (mg/L, mg/kg) and its depth | `authoring_facts.unassigned_boreholes` |
| Exceeding background boreholes' own vertical closure, deepest sample/chloride | `authoring_facts.background_chloride_exceedances.per_borehole_detail` |
| Distance of each exceeding background borehole from the impact centroid (m) | `authoring_facts.background_chloride_exceedances.distance_from_impact_centroid_m` |
| Figure numbers and captions as placed in the document | `figures_in_document` |
| Worst-case on-site chloride (mg/L, borehole, depth), vertical/lateral status | `chloride_delineation_data` |

Rules for what is not in the data:
- **APEC names:** use the workbook's APEC names exactly as written (`authoring_facts.areas`, `ec_sar_data[].area`). Any area names in the prompts' wording or examples (well centre, DWDA, etc.) are examples only. Never rename, merge or map workbook names, and never compare them with the Phase 1 ESA's APEC names.
- **Field screening results** are not extracted. Do not assert what field screening showed; write a bracketed practitioner placeholder.
- **Placeholders left in the finished report** are scanned by Python and appended to the Practitioner Information file automatically; you do not need to list them.

If a prompt asks for something that is in none of these, write a bracketed practitioner placeholder.

## Section 5 gate (do this first)

If `section5_present` is false (log: `SECTION5_PRESENT: no`): set `s5_1_phase1`, `s5_2_transport`
and `s5_3_footprint` to `null`, do not read those three prompt files, do not view the 5.3 figures, and
write no reference to Section 5 anywhere. The generator has already removed Section 5, so later
headings move up one number: Section 8's compliance sentence must say "Section 6" instead of
"Section 7" (see `s8_summary.md`). Only Section 5 keys may be null; every other key is required.

## After writing `authored.json`

```bash
python3 scripts/assemble_operations.py authored.json <partial_docx> excel_data.json operations.json
python3 scripts/apply_operations.py <partial_docx> operations.json <output_docx>
python3 scripts/write_practitioner_info.py practitioner_info.json <output_folder> <output_docx>
```

`assemble_operations.py` validates `authored.json` (wrong style, empty block, a non-null Section 5 key
when Section 5 is absent, a missing required key) and stops with a message; fix the JSON and re-run it.
It also writes `practitioner_info.json` next to `operations.json`.
