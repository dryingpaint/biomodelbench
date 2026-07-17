# `vep_multieval_v0` — one submission, two hidden evaluations

## Task

Same agent contract as `vep_c_open_v0` — only variant IDs are shipped, no
labels, no features. The difference: the test file is the union of **two
hidden test partitions**, and the grader reports AUPRC / AUROC separately
for each.

The two partitions:

- **TraitGym `complex_traits_matched_9`** — 11,400 variants asking "is this
  SNP a GWAS-fine-mapped causal variant for a common complex trait?" Base
  rate ~10%.
- **NCBI ClinVar 2-star+** — ~30,000 variants asking "is this variant a
  Mendelian-disease pathogenic (P/LP) or benign (B/LB) variant?" Base
  rate ~50%.

The agent submits **one score per variant**, not two. It does not know
which variant is from which source. The grader has the per-source labels
and slices its own metrics.

## What this measures that the single-source tasks don't

- **Domain-specific vs. transferable signal.** A model that scores well
  on TraitGym but poorly on ClinVar has learned complex-trait-specific
  features; one that scores modestly on both has captured a more
  transferable "variant importance" signal. Both findings are useful.
- **Cross-domain sanity check.** If a supposedly-general "variant
  effect" model can't do anything on ClinVar, the "general" framing is
  wrong.

## Regenerate the bundle

```bash
python tasks/vep_multieval_v0/build.py
```

Fetches:
- TraitGym `complex_traits_matched_9/test.parquet` from HuggingFace.
- NCBI ClinVar VCF from `ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/`.

Filters ClinVar to 2-star+ review status (`criteria_provided,_multiple_submitters,_no_conflicts`
or better) and P/LP vs. B/LB significance. Subsamples to 30k rows with a
balanced (~50/50) class split. Writes `bundle/test.parquet` (shuffled,
source not visible) plus two hidden answer files. ~1-2 min end-to-end.

## Run one agent attempt

```bash
uv run modal run harness/modal_runner.py::volume_upload --task vep_multieval_v0
uv run modal run --detach harness/modal_runner.py::launch --task vep_multieval_v0
```

## Grader output

`grade.json` reports per-source AUPRC / AUROC / Brier / coverage plus a
"generalization gap" summary. Reference baselines are baked in for the
TraitGym partition (phyloP-241m, phastCons-43p, GPN-MSA_absLLR). ClinVar
reference bars are trickier because the field-standard predictors
(AlphaMissense, REVEL, ClinPred) were trained on ClinVar itself — they
score >0.9 AUPRC on P/LP vs. B/LB but that's near-circular, so we don't
treat them as a bar.

## Future expansions

We could plug more hidden test partitions into this same one-submission
shape without changing the task contract. Candidates that would fit:

- **FinnGen fine-mapping** — same question as TraitGym (complex-trait
  causal SNP) but a different cohort (Finnish, high-drift population).
  Would test cohort transfer within the complex-trait domain. Needs a
  per-phenotype credible-set build step — ~4-6 hours of data plumbing.
- **ProteinGym clinical substitutions** — a curated ClinVar missense
  subset, per-protein. Overlaps our ClinVar partition semantically but
  is packaged cleaner. Could replace the raw ClinVar slice or sit
  alongside as a "clean missense" comparator.
- **AlphaMissense held-out** — Cheng et al.'s genome-wide missense
  predictions, useful as a comparison-of-rankings task rather than as
  ground truth.
- **CausalDB non-UKBB** — mixed-cohort fine-mapping, weaker overlap
  with TraitGym.
- **ProteinGym DMS** — continuous fitness scores from deep mutational
  scanning. Different metric (Spearman ρ) rather than AUPRC — grader
  would need per-partition metric dispatching.
- **Cancer somatic variants (COSMIC / TCGA)** — different label
  semantic again (driver vs. passenger), same variant-ID input schema.

Adding another partition = an additional `hidden/<name>_answer.parquet`
and a per-source-slice call in `grade.py`. The agent-facing prompt only
needs to add the new source's name to the blacklist so the agent doesn't
fetch its labels directly.

## Design constraints

- **No source flag shipped.** The agent can guess from variant patterns
  (e.g., ClinVar variants cluster in coding regions) but can't cheaply
  reverse-engineer which is which.
- **Anti-leak is broader.** The prompt blacklists both TraitGym-derivative
  sources AND raw ClinVar releases + AlphaMissense (which was trained on
  ClinVar).
- **One model, one submission.** The agent shouldn't fork the pipeline
  by-source — the interesting question is whether a single-ranking model
  transfers.
