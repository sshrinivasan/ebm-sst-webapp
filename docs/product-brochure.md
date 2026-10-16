# EBM Soil / SST — Analytical Workspace

**One upload. Every soil and site-specific workflow. AI-assisted reporting.**

The EBM Soil / SST webapp turns a single soil analytical workbook into the full
suite of EBM routine and site-specific (SST) deliverables — tables, charts, and
a complete Phase 2 ESA report — in one guided workspace.

---

## 1. Intake — one file, everything derived

Upload the soil analytical workbook (`.xlsm`) once. The app parses it and
derives every option list, subarea, and guideline reference automatically —
no re-uploading, no re-keying.

- **Shared inputs** — sheet name, chloride guideline, topsoil depths, water
  table depth, and the SST toggle apply to every workflow.
- **File-derived selectors** — boreholes, subareas, background samples, and
  guideline tables are populated from the workbook the moment it loads.
- **Subarea assigner** — assign boreholes to subareas for the 95th-percentile
  analysis with a visual editor.
- **SST mode** — a site-specific analysis toggle that switches the chloride
  exceedance units and adds the SST workflows.

## 2. Workflows supported

| Workflow | Output |
|---|---|
| **EC / SAR Rating** | Rating categories per sample |
| **SCARG Guidelines** | Background guideline summary (editable table) |
| **Borehole Characteristics** | Per-borehole stats and characteristics |
| **Tier 1 Exceedances** | Exceedance tables vs. Tier 1 guidelines |
| **Site-Specific (SST) Exceedances** | Exceedances vs. site-specific criteria |
| **Tier 1 Charts** | Standard profile + variable graphs |
| **BG Chloride** | Background chloride scatter plots |
| **Chloride Delineation** | Chloride profile figures per borehole batch |
| **Texture** | Depth tables + saturation profile |
| **95th Percentile** | Subarea data, stats, outliers, chloride profiles |
| **TDS** | Groundwater trend graphs (Mann-Kendall) |
| **NPP** | Near-APEC background screening |

Every workflow runs against the same parsed workbook, so results stay
consistent across tabs. Tables and charts are rendered in a schema-driven UI —
no per-workflow frontend code.

## 3. AI Reporting — from files to a finished report

The **AI Report** tab runs the EBM routine-report skill as a guided wizard:

1. **Files** — upload the analytical workbook plus the source documents
   (ABAData, Phaseview, Phase 1 ESA, borehole logs) and the figures zip.
2. **Extract & Review** — the LLM reads the source documents once and extracts
   the site facts (2–5 minutes). Review the reconciled identity fields
   (LSD, UWI, client, site type), correct anything, and inspect the raw
   extracted data per source file. Cached facts can be downloaded and
   re-uploaded to skip extraction entirely.
3. **Intake** — a dashboard of only the questions that apply (report type,
   EM survey, exploratory boreholes with custom APECs, impact volume).
4. **Generate** — one action runs the hands-off pipeline: regenerate the
   report with your answers, author every section in a single LLM call, apply
   the operations, and build the practitioner hand-off.
5. **Done** — download the final DOCX and the practitioner information file.

The report follows the EBM routine Phase 2 ESA template — cover page, site
characterization, EC/SAR and chloride delineation, DWDA evaluation, background
chloride, and the APEC review — with practitioner placeholders flagged for
review.

---

## Why it works

- **One source of truth** — the workbook is parsed once; every workflow and the
  report read the same data.
- **Hands-off generation** — no mid-pipeline questions; the report is produced
  as a single background job with visible progress.
- **Reusable** — site facts are cached and portable, so re-running a site
  skips the slow extraction.
- **Consistent with EBM practice** — the report mirrors the existing routine
  report template and the practitioner hand-off keeps human review in the loop.