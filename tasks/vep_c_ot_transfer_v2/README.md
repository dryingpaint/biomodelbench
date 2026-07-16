# `vep_c_ot_transfer_v2` — complex-trait causal SNP prediction, open-ended features, blind eval

## What the task is

Predict which SNPs are GWAS-fine-mapped causal for complex traits. The
agent gets 72,093 Open Targets Genetics variants with fine-mapping labels
for **training**, and 11,400 TraitGym `complex_traits_matched_9` variant
positions for **test**. Feature extraction is on the agent. The test
labels never enter the container.

## Why this shape

Every previous variant on this task either handed the agent pre-computed
features (making it a modeling contest) or let it self-evaluate against
labels it could see (letting it hill-climb). This version isolates the
question we actually want to answer: given only variant IDs + labels and
a container with internet + a GPU, can an agent build a competitive
predictor?

## Numbers from the one shipped run

See [`runs/ot-v2-20260715T210355/grade.json`](runs/ot-v2-20260715T210355/grade.json).

- Agent: **AUPRC 0.2144 / AUROC 0.6176** (coverage 100%).
- Best single-feature baseline on the same test: phyloP-241m (Zoonomia)
  at 0.2352. The agent did not extract this specific track — it used UCSC
  100-way / 470-way / 17-way instead, plus Enformer allele-delta features.
- Result lands above every feature the agent actually extracted, below
  the two feature families it didn't find. Discovery cost, not modeling
  cost.

## Regenerate the bundle

```bash
python tasks/vep_c_ot_transfer_v2/build.py
```

Downloads OT credible sets (40 parts × ~13 MB across the 200-part release)
and TraitGym `complex_traits_matched_9/test.parquet`. Writes:

- `bundle/train.parquet` — 72k rows, `chrom, pos, ref, alt, label, pip_max, n_studies`
- `bundle/test.parquet` — 11.4k rows, `chrom, pos, ref, alt`
- `bundle/prompt.md` — copy of the agent-facing prompt
- `hidden/answer.parquet` — 11.4k rows with the ground-truth `label`
- `hidden/build_stats.json` — build summary

`bundle/prompt.md` gets uploaded to the Modal Volume alongside the parquets
and lands in the container's workdir as the file the agent reads.

## Run one agent attempt on Modal

```bash
# Upload the bundle to the shared volume
uv run modal run harness/modal_runner.py::volume_upload --task vep_c_ot_transfer_v2

# Launch a single attempt (detached — survives your terminal closing)
uv run modal run --detach harness/modal_runner.py::launch --task vep_c_ot_transfer_v2
```

The launcher syncs artifacts back to `tasks/vep_c_ot_transfer_v2/runs/<run_id>/`
and runs `grade.py` locally against the downloaded `answer.parquet`.

## Grade a submission manually

```bash
python tasks/vep_c_ot_transfer_v2/grade.py \
    --submission tasks/vep_c_ot_transfer_v2/runs/<run_id>/answer.parquet \
    --out       tasks/vep_c_ot_transfer_v2/runs/<run_id>/grade.json
```

Grader is deterministic. Reads `hidden/answer.parquet`, joins on
`(chrom, pos, ref, alt)`, and reports:

- **AUPRC** (headline; base rate 10%)
- AUROC
- Brier score
- Coverage (fraction of test rows the submission covered)
- Per-chromosome breakdown (leak sanity — no single chromosome should have
  AUPRC ≈ 1.0 while others sit near 0.2)
- Gap vs. the strongest single-feature baseline

Reference baselines (phyloP-241m, phastCons-43p, GPN-MSA_absLLR, phyloP-100v,
phastCons-100way, evo2_40b_LLR) are baked into `grade.py` from the TraitGym
release so the grader is self-contained.

## Design constraints on this task

- **No pre-extracted features shipped.** Only variant IDs and training labels.
- **Fully blind test.** Labels never enter the container; the agent has no
  self-eval loop against test.
- **Anti-leak.** OT variants that overlap the TraitGym test set (chrom, pos,
  ref, alt exact matches) are dropped from `train.parquet` before shipping.
- **One-shot.** No CV or hyperparameter tuning against the test — any
  validation strategy must sit inside `train.parquet` alone.
