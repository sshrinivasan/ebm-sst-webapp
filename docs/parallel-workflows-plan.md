is # Future-proofing the pipeline for parallel workflows

**Status:** design reference — nothing implemented yet. Migrate toward this when
we're ready to run multiple workflows concurrently.

**Current entry point:** `pipeline.run(excel_path, params) -> Context` — a flat,
sequential list of `step(ctx) -> ctx` functions sharing one mutable `Context`.
This is the right design for a linear notebook port, but it will not support
running workflows in parallel.

---

## Why the current design blocks parallelism

1. **In-place mutation of shared frames.**
   `compute_ec_sar_ratings` copies `soil_data_filtered`, adds
   `ec_category`/`sar_category`, then *writes it back* to the same key. If two
   workflows read that key concurrently, what they see depends on timing.
   → This write-back is the single biggest blocker.

2. **One flat `ctx.frames` bag.**
   Every step reads/writes the same dict. No namespace isolation → key
   collisions and racy reads/writes across workflows.

3. **`run()` is a flat list, not a dependency graph.**
   Nothing declares what *can* run concurrently vs. what must be sequenced.

4. **Python reality:** pandas is CPU-bound and mostly holds the GIL, so threads
   won't give true parallelism. Real parallelism = processes or separate jobs.

---

## Target model: trunk + branches

The pipeline is really two phases:

- **Trunk (shared prep — runs once, sequential):**
  `load → read_sst_guidelines → drop_duplicate_rows → convert_units → average_duplicates`
  Produces the canonical cleaned frames.

- **Branches (workflows — independently parallelizable):**
  EC/SAR rating, SCARG background, TDS, Tier-1 exceedances, site-specific,
  surfer. Each *reads* the prepped frames and produces *its own* outputs.

### Three disciplines that make branches safe to parallelize

1. **Prepped base frames are read-only.** Branches `.copy()` before adding
   columns and **never write back** to a shared key.
2. **Per-workflow output namespace.** Each workflow returns its own result
   object (`results["ec_sar"]`, `results["scarg"]`, …); merge only at
   serialization time.
3. **Workflows are pure functions of `(base_frames, params)`.** No workflow
   depends on another's side effects → order stops mattering → safe to run
   concurrently and safe to cache/memoize per workflow.

That's the whole fix — mostly a *contract* change (immutability + namespacing),
not a rewrite.

---

## Where parallelism lives in the webapp

Don't use Python threads — use parallel jobs/requests (also matches the
Oceantier / Cloudflare Workers direction: stateless, no long-lived shared
mutable memory).

- **Prepare once, cache by upload token.** On upload, run the trunk and cache
  the cleaned frames (parquet/Arrow) keyed by token. Each workflow becomes a
  stateless endpoint/job that loads the cached prep and runs independently.
- **Fan out workflows as separate requests or a job queue.** The frontend (or an
  orchestrator) fires N workflow calls in parallel; each reads the same
  immutable prepared dataset.
- **In-process option** (CLI/tests): `ProcessPoolExecutor` over the pure
  workflow functions — but only once base frames are immutable and serializable.

---

## Migration plan (priority order)

Steps 1–3 are the real future-proofing and are backward-compatible with
everything today. The golden-CSV regression tests will catch any regression.

- [ ] **1. Split `run()` into `prepare()` + `workflows`.**
  Draw the trunk/branch line. Highest leverage, lowest risk.
  `prepare(excel_path, params) -> base_frames` (immutable), then
  `workflow(base_frames, params) -> WorkflowResult`.

- [ ] **2. Kill in-place write-backs to shared keys.**
  Fix `ec_sar_rating` first: read the base frame, `.copy()`, write derived
  columns/frames under the workflow's *own* keys — never back to
  `soil_data_filtered`. This makes concurrency *correct*, not just possible.

- [ ] **3. Give each workflow its own result namespace.**
  Replace the single flat `ctx.frames` bag for workflow outputs with
  per-workflow containers; merge at serialize time.

- [ ] **4. Declare each workflow's inputs.**
  Even as a plain dict: which base frames it needs. Lets a scheduler/DAG fan
  out later and documents the currently-implicit ordering.

- [ ] **5. Web layer: cache-prep-by-token + parallel job execution.**
  Run the trunk once on upload, cache cleaned frames by token; expose each
  workflow as its own stateless endpoint/job the frontend can call in parallel.

---

## What NOT to change

- Don't type `params` into a rigid model — the schema-driven `params.py` +
  `defaults()` merge is enough and keeps the "add a param, read `ctx.params[...]`"
  ergonomics.
- Don't split `Context` into per-workflow contexts for the *trunk* — the shared
  prepped frames are exactly what branches reuse.
- Keep workflow logic as close to the Hex notebook as possible; this plan
  changes *orchestration and data ownership*, not the analysis code.
