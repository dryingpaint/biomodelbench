# BioModelBench — VEP multi-eval v1

## Task

Predict a single `score` in [0, 1] for each variant in `test.parquet`.
Higher = more likely to be a **functionally impactful variant**.

`test.parquet` is a mixed test set drawn from multiple biological
questions (GWAS-fine-mapped causal SNPs for complex traits;
GWAS-fine-mapped causal SNPs for Mendelian rare traits; clinical
pathogenic vs. benign classification). You are not told which variant
is from which source. The grader has per-source labels and reports
AUPRC / AUROC / Brier / coverage separately for each hidden partition.
For ClinVar the grader additionally reports per-molecular-consequence,
per-review-status, and per-significance-pair slices.

Build one model whose ranking is good across all partitions — a model
of "variant importance" that transfers.

## What's shipped

### `test.parquet` — ~42,500 rows

Columns: `chrom` (string, 1-22), `pos` (int, hg38 1-based), `ref`, `alt`.
No label. No features. No source flag.

## Training

You may compile your own labeled training set from public sources.
Variant-effect databases, GWAS credible-set catalogues, ClinVar / HGMD
/ DoCM, mutation-effect measurement panels, and existing benchmark
train partitions are all fair game. You may run foundation-model
inference locally and train probes on the resulting embeddings.

Data-leakage prevention is your responsibility. The grader does not
detect leakage. Any training variant that shares an exact
`(chrom, pos, ref, alt)` tuple with a row in `test.parquet` is leakage.
Recommended: build the tuple set from `test.parquet` up front and use
it as an exclusion filter when constructing any labeled train set. If
you use a source that reports variants under a different reference
build or coordinate system, LiftOver to hg38 first, *then* dedup.

## Compute

Modal container: **H100 GPU (80 GB VRAM), 8 CPUs, 96 GB RAM**.
Python 3.11 with `torch / transformers / peft / xgboost / lightgbm /
scikit-learn / pandas / pyarrow / numpy / pyBigWig / pysam / biopython
/ requests` pre-installed. `pip install <x>` works.

Budget: 10 hours of GPU compute. The runner will relaunch your session
with a continuation prompt if it exits before the wall clock is
exhausted.

## Deliverables

- `answer.parquet` — columns `chrom, pos, ref, alt, score`, one row
  per test variant, `score ∈ [0, 1]`.
- `method.md` (< 500 words). Describe your final approach and every
  intermediate iteration. If you compiled labeled training data,
  describe the source(s), the dedup step against test, and the
  resulting train-set size.
- `training_manifest.json` — every URL / API / dataset touched, with
  dedup counts where applicable, and one row per iteration with the
  per-iteration validation score if you produced one.

## What the grader does

Each hidden partition has its own labels. Grading joins your
`answer.parquet` against each partition's labels on
`(chrom, pos, ref, alt)`, computes per-partition AUPRC / AUROC /
Brier / coverage, and reports each. For ClinVar it additionally
reports per-molecular-consequence, per-review-status, and
per-significance-pair slices.

## Published SOTA — TraitGym complex_traits

AUPRC by chromosome-weighted average (Benegas et al. 2025).

| Method | AUPRC |
|---|---:|
| CADD + GPN-MSA + Borzoi (trained LR ensemble) | 0.362 |
| CADD + Borzoi (trained LR ensemble) | 0.351 |
| Enformer (trained LR probe) | 0.303 |
| Borzoi (trained LR probe) | 0.297 |
| CADD v1.7 (trained LR) | 0.284 |
| GPN-MSA (trained LR probe) | 0.269 |
| CADD v1.7 RawScore (zero-shot) | 0.250 |
| Enformer L2 (zero-shot) | 0.245 |
| phastCons-43p Zoonomia primate | 0.237 |
| Borzoi L2 (zero-shot) | 0.236 |
| phyloP-241m Zoonomia | 0.227 |
| GPN-MSA absLLR (zero-shot) | 0.224 |
| SpeciesLM LR probe | 0.185 |
| Sei LR probe | 0.184 |
| phyloP-100way | 0.184 |
| AIDO.DNA LR probe | 0.152 |
| Caduceus LR probe | 0.151 |

## Published SOTA — TraitGym Mendelian traits

AUPRC by chromosome-weighted average (Benegas et al. 2025). Different
biology (rare Mendelian) than complex_traits but same task shape.

| Method | AUPRC |
|---|---:|
| CADD + GPN-MSA + Borzoi (trained LR ensemble) | 0.648 |
| GPN-MSA (trained LR probe) | 0.584 |
| CADD v1.7 (trained LR) | 0.549 |
| Enformer (trained LR probe) | 0.501 |
| Borzoi (trained LR probe) | 0.487 |
| phyloP-241m Zoonomia | 0.462 |
| Enformer L2 (zero-shot) | 0.350 |
| Borzoi L2 (zero-shot) | 0.339 |

## Published SOTA — ClinVar missense (AUROC)

| Method | AUROC |
|---|---:|
| AlphaMissense (Cheng et al. 2023) | 0.972 |
| Evo-2 covariance probe (EVEE 2026) | 0.971 |
| CADD v1.7 (Rentzsch et al. 2021) | 0.966 |
| GPN-MSA (Benegas et al. 2023) | 0.952 |
| Evo-2 loss-based (Nguyen et al. 2025) | 0.932 |
| REVEL (Ioannidis et al. 2016) | 0.930 |
| CADD v1.6 (Rentzsch et al. 2021) | 0.911 |
| ESM-1v (Meier et al. 2021) | 0.83 |
| NTv3 (Dalla-Torre et al. 2024) | 0.586 |

## Published SOTA — ClinVar per-consequence (AUROC; Evo-2 covariance probe, EVEE 2026)

| Consequence | Evo-2 covariance probe |
|---|---:|
| missense | 0.971 |
| synonymous | 0.961 |
| nonsense (stop_gained) | 0.900 |
| splice donor/acceptor | 0.924 |
| UTR (5′/3′) | 0.929 |
| intronic | 0.984 |
| other non-coding | 0.969 |
