# Section 5.3 — Chemistry Footprint

## Placeholder

`<INSERT_5_3_START>` / `<INSERT_5_3_END>` — Op type: `replace_between`.

**This section only exists when background chloride exceedances are present** — same condition as
`s5_intro.md`, `s5_1_phase1.md`, and `s5_2_transport.md`. If no Tier 1 exceedances with
APEC = "Background" and Chemical Group = "Chloride" exist, skip this section entirely and emit
no operation for it.

The chemistry footprint figures themselves are placed in the document by Python between
`<INSERT_5_3_FIGURES_START>` and `<INSERT_5_3_FIGURES_END>` (reading PNGs from the
`BG_CHLORIDE/` folder in the figures zip). This is a range replacement — everything between
the two markers is deleted first, so any stale placeholder content sitting between them (e.g.
leftover template example figures) is removed too, before the real figures are inserted. The
older single-marker form `<INSERT_5_3_FIGURES>` (point-replacement, nothing deleted around it)
still works as a fallback if a template hasn't been updated to the START/END pair.
**This prompt only covers the narrative text** written at `<INSERT_5_3_START>`/`<INSERT_5_3_END>`,
which appears before the figures.

---

## This is a vision task, not a data task

The chemistry footprint charts are pre-made images — built outside this pipeline — not derived
from the Excel data. To write Paragraphs 2 and 3, **Claude must actually view the figure
images** (read them from the `BG_CHLORIDE/` folder in the figures zip before writing) and
describe what is visually apparent in each chart. Do not invent plausible-sounding cluster
language without having viewed the actual images.

---

## The parameter pairing is not fixed

The figures can compare **any two parameters** (Na, K, Mg, Ca, SO₄, HCO₃, ratios, sums, or
any other combination). Do not assume a specific pairing from a prior worked example.

**Read the actual figure caption already placed below each image** (or the filename in the
`BG_CHLORIDE/` folder) to determine which parameters this site's figures compare. Parse
filenames generically: `x_y` → "X vs. Y"; `x-y_z` → "X/Y Ratio vs. Z";
`x_y+z` → "X vs. Y + Z". Write all text to match the actual parameters shown.

---

## What to write

### Paragraph 1 — methodology (mostly fixed, one variable)

State the comparison method, name the actual parameters compared (per figure caption check
above), and explain why each is chemically relevant to distinguishing naturally occurring
chloride from an anthropogenic source. Sulphate is commonly naturally occurring in the region;
a second parameter such as sodium or potassium is commonly a drilling-mud or produced-water
indicator — but confirm this reasoning applies to whatever parameters this site's figures
actually show, and adjust if a different parameter is used for a different reason. Cite the
Phase 1 ESA if it identifies the source (use the same citation format as Section 5.1).

> "A simple comparison of the source and background areas was conducted by evaluating the
> ratios of chloride to [parameter A] and of [parameter B]. [Parameter A] is a naturally
> occurring salt that is prevalent in the region, and [parameter B] is a common
> [produced-water/drilling mud] additive, as identified in the Phase 1 ESA ([citation]). For
> a more representative comparison, the units for each comparison are in [units]."

### Paragraphs 2 and 3 — one per figure, from actually viewing the images

For each chemistry footprint figure, view the image and describe:

- What the axes compare
- Where impact-area samples fall relative to background samples
- Whether the pattern is "as expected" (impact area elevated in both dimensions, background
  low) or shows a different relationship — describe what is actually visible, do not force the
  "as expected" framing if the image does not support it

Reference each figure by its actual number in the document (read the `FigureTitle` caption
already placed below the image — do not assume a fixed figure number).

If the figures use a colour legend, reference the actual colours/legend shown in this site's
images.

**Worked example** (tone and shape only — parameters, values, and figure numbers will differ):

> "Figure 9 shows the relationship between potassium and chloride. As expected, samples from
> the impact area contain elevated levels of potassium and chloride. In contrast, the
> background samples contain equally low levels of potassium, regardless of the elevated
> chloride levels."

> "Figure 10 shows a striking contrast between the impact area and the background samples.
> The background locations with elevated chloride (yellow) are grouped vertically with the
> background samples, whereas those from the impact area (red) are grouped separately."

---

## Output

**Do NOT use a single `replace_between` spanning `<INSERT_5_3_START>` through
`<INSERT_5_3_END>`.** By the time this text is authored, the mechanical
pipeline has already run `generate_section5_3_figures()`, which consumes
`<INSERT_5_3_FIGURES_START>`/`_END` and inserts the real figure table
*between* the outer START and END markers. A `replace_between` across the
full outer range deletes that already-inserted figure table along with the
stale template text -- silently discarding the real images (this happened
once; don't repeat it). The figures must survive untouched; only the stale
narrative text around them gets replaced.

Use this three-part approach instead:

1. `insert_blocks` at `<INSERT_5_3_START>` with your methodology + per-figure
   paragraphs -- this both removes the START marker and inserts your new text
   at that exact position (right after the "Chemistry Footprint" heading,
   before the stale example text).
2. `delete_paragraph` for each stale template paragraph that follows (the
   template's own worked-example text -- read the live document first to get
   each one's exact current text, don't assume it matches an older version of
   this file). Bound each with `"after": "Chemistry Footprint"` and
   `"before": "<INSERT_5_3_END>"` since the stale sentences aren't unique
   enough in the whole document otherwise.
3. `delete_paragraph` for the literal `<INSERT_5_3_END>` marker paragraph
   itself (no bounds needed, it's already unique).

```json
[
  {
    "op": "insert_blocks",
    "placeholder": "<INSERT_5_3_START>",
    "blocks": [
      {"style": "body", "text": "Methodology paragraph..."},
      {"style": "body", "text": "Figure N interpretation..."},
      {"style": "body", "text": "Figure N+1 interpretation..."}
    ]
  },
  {"op": "delete_paragraph", "text": "[exact stale paragraph 1 text]", "exact": true, "after": "Chemistry Footprint", "before": "<INSERT_5_3_END>"},
  {"op": "delete_paragraph", "text": "[exact stale paragraph 2 text]", "exact": true, "after": "Chemistry Footprint", "before": "<INSERT_5_3_END>"},
  {"op": "delete_paragraph", "text": "[exact stale paragraph 3 text]", "exact": true, "after": "Chemistry Footprint", "before": "<INSERT_5_3_END>"},
  {"op": "delete_paragraph", "text": "<INSERT_5_3_END>", "exact": true}
]
```

If a `delete_paragraph` reports "no paragraph matching" despite the text
looking identical, it's almost always a hidden whitespace/run-split
mismatch -- pull the paragraph's exact text via `python-docx` (`repr()` it)
rather than re-typing it by eye, or fall back to a direct one-off
python-docx removal of that specific paragraph element.
