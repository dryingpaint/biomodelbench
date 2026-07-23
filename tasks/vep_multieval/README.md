# `vep_multieval` — VEP across 3 partitions, self-compiled training allowed

## Task

Predict a single functional-impact score in [0, 1] for each variant in
a mixed test set drawn from **three** biological questions:
1. **TraitGym complex_traits** — GWAS-fine-mapped causal SNPs for common
   polygenic traits (~11,400 rows, ~10% positive, PIP > 0.9 vs matched
   PIP < 0.01 controls at 9:1).
2. **TraitGym Mendelian traits** — GWAS-fine-mapped causal SNPs for
   rare Mendelian traits (~1,140 rows, same matching scheme).
3. **ClinVar 2-star+** — clinical pathogenic vs. benign SNVs
   (subsampled to ~30k rows, balanced 50/50).

Agent gets only `(chrom, pos, ref, alt)` per variant — no source flag,
no label. Grader has per-source hidden labels and reports AUPRC /
AUROC per partition, plus per-molecular-consequence, per-review-status,
and per-significance-pair ClinVar slices.

## Why this shape

- **Cross-partition transfer is the point.** Zero-shot conservation
  models (phyloP, phastCons) rank TraitGym complex-traits well.
  ClinVar-trained tools (AlphaMissense, REVEL) rank ClinVar missense
  well. TraitGym Mendelian sits in between: rare pathogenic non-coding.
  One score must handle all three regimes.
- **The agent may compile its own training data.** No `train.parquet`
  ships; the agent is expected to find labeled sources on its own and
  use the shipped test set as a deduplication filter.
- **SOTA is named.** The prompt lists specific models and their
  published scores across all three partitions, so the agent has an
  explicit leaderboard to beat rather than a vague "reference bar".

## Regenerate the bundle

```bash
python tasks/vep_multieval/build.py
python tasks/vep_multieval/scripts/annotate_clinvar_mc.py
```

Downloads:
- TraitGym `complex_traits_matched_9/test.parquet` from HuggingFace
- TraitGym `mendelian_traits_matched_9/test.parquet` from HuggingFace
- NCBI ClinVar GRCh38 VCF (~180 MB)

Then filters ClinVar to 2-star+ P/LP/B/LB, subsamples to 30k with a
balanced 50/50 pos/neg split, dedupes against both TraitGym partitions,
shuffles, and writes:

```
bundle/test.parquet                                  — ~42,500 rows
hidden/traitgym_complex_answer.parquet               — ~11,400 rows
hidden/traitgym_mendelian_answer.parquet             — ~1,140 rows
hidden/clinvar_answer.parquet                        — ~30,000 rows (annotated with mc_class, review_status, significance_tier)
hidden/build_stats.json
```

## Run

```bash
uv run modal run harness/modal_runner.py::volume_upload --task vep_multieval
uv run modal run --detach harness/modal_runner.py::launch --task vep_multieval
```

The runner uses **H100 (80 GB VRAM)** and a 10-hour wall-clock budget.
Sessions that exit early are automatically relaunched with a
continuation prompt until the wall clock is nearly exhausted.

## Grade

```bash
python tasks/vep_multieval/grade.py \
    --submission tasks/vep_multieval/runs/<run_id>/answer.parquet \
    --out        tasks/vep_multieval/runs/<run_id>/grade.json
```

Deterministic. Reports per-partition AUPRC / AUROC / Brier / coverage,
plus per-molecular-consequence / per-review-status /
per-significance-pair ClinVar slices, plus baked-in reference
baselines with named models across zero-shot, trained-probe, and
trained-ensemble categories.

## Future partitions (v2 candidates)

The interface (SNV tuples + hidden per-partition labels) supports any
additional variant-level benchmark that reports (chrom, pos, ref, alt).
High-value additions:

- **MPRA panels** — Kircher et al. 2019 K562 MPRA (~30k SNVs with
  measured regulatory activity) or Findlay et al. 2018 BRCA1
  saturation genome editing (~4k SNVs with functional scores). Adds
  "true functional activity" as an evaluation axis distinct from GWAS
  colocalization or clinical curation.
- **ProteinGym** — requires protein-level (not genomic) coordinates,
  so a schema change; probably its own task shape.
- **CAGI clinical challenges** — real-world diagnostic setting, small
  test sets, high signal for genuinely-hard variants.
