# BioModelBench — VEP multi-eval v0

## Task

Predict a single `score` in [0, 1] for each variant in `test.parquet`.
Higher = more likely to be a **functionally impactful variant**.

`test.parquet` is a mixed test set. Some of the variants are drawn from
one biological question (GWAS-fine-mapped causal SNPs for common
complex traits) and others from a different biological question
(clinical pathogenic vs. benign classification). You are not told which
is which. The grader has the per-source labels and will report AUPRC /
AUROC separately for each hidden partition.

The point of the task is not to reverse-engineer which variant is from
which source. The point is to build one model whose ranking is good
across both questions — a model of "variant importance" that transfers.

## What's shipped

### `test.parquet` — ~41,400 rows

Columns: `chrom` (string, 1-22), `pos` (int, hg38 1-based), `ref`, `alt`.
No label. No features. No source flag.

## Compute

Modal container: A10G GPU (24 GB VRAM), 8 CPUs, 96 GB RAM. Python 3.11
with `torch / transformers / peft / xgboost / lightgbm / scikit-learn /
pandas / pyarrow / numpy / pyBigWig / pysam / biopython / requests`
pre-installed. `pip install <x>` works.

Budget: ~10 hours of GPU compute. Use it. Even after you produce a
valid `answer.parquet`, keep iterating until the budget is exhausted.
The runner will relaunch your session with a continuation prompt if you
exit early — don't finalize prematurely.

## Deliverables

- `answer.parquet` — columns `chrom, pos, ref, alt, score`, one row per
  test variant, `score ∈ [0, 1]`.
- `method.md` (< 500 words).
- `training_manifest.json` — every URL / API / dataset touched.

## What the grader does

Each hidden partition has its own labels. Grading joins your
`answer.parquet` against each partition's labels on
`(chrom, pos, ref, alt)`, computes per-partition AUPRC / AUROC / Brier /
coverage, and reports both.

## Reference bars

| Partition | Base rate | Best published reference (AUPRC) |
|---|---:|---:|
| TraitGym | 0.10 | 0.45 |
| ClinVar  | 0.50 | 0.95 |

Base rates differ across partitions, so absolute AUPRC numbers aren't
directly comparable across partitions — each partition's number vs. its
own base rate is the meaningful read.
