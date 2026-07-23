# BioModelBench — Bacterial Gram-staining (bacdive_gram)

## Task

For each row in `test.parquet`, predict `gram_prob ∈ [0, 1]`: the
probability the strain is Gram-positive. The label is binary
(Gram-positive = 1, Gram-negative = 0).

Test strains are drawn from bacterial families not present in the
training set. You have the assembly accession + phylum for each strain
— that's it. No genus, no species, no strain name.

## What's shipped

### `train.parquet`

Columns:
- `assembly_accession` (string, e.g. `GCF_000005845.2` or `GCA_…`) —
  NCBI assembly accession.
- `phylum` (string) — coarse taxonomy.
- `label` (int, 0/1) — 1 = Gram-positive, 0 = Gram-negative.

### `test.parquet`

Columns: `assembly_accession`, `phylum`. No label.

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

- `answer.parquet` — columns `assembly_accession, gram_prob`, one row
  per test strain, `gram_prob ∈ [0, 1]`.
- `method.md` (< 500 words).
- `training_manifest.json` — every URL / API / dataset touched.

## What the grader does

Reads your `answer.parquet`, joins on `assembly_accession` against the
hidden Gram-staining labels, computes AUPRC / AUROC / Brier / coverage.

## Reference bar

Test-set base rate: ~0.34 Gram-positive. Published Gram predictors on
family-holdout land around AUPRC 0.7–0.9. Exact reference-baseline bar
will be baked into `grade.py` before this task is treated as production.
