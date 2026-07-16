# BioModelBench — VEP-C (OT transfer, open-ended features) v2

## Task

Build a variant-effect predictor that scores whether each variant in
`test.parquet` is a **GWAS-fine-mapped causal SNP for a complex trait**.
You have a labeled training set of 72,093 Open Targets Genetics
credible-set variants; you must produce a `causal_prob` for each of the
11,400 test variants. The test labels are hidden — you cannot evaluate
against them.

## What's shipped

That's it. No pre-computed features. No embeddings. No conservation
scores. Just variant identities and training labels.

### `train.parquet` — 72,093 rows

Columns:
- `chrom` (string, 1–22), `pos` (int, hg38 1-based), `ref`, `alt` — variant identity
- `label` — 1 if `pip_max >= 0.9` in at least one GWAS credible set (positive), else 0
- `pip_max` — max posterior inclusion probability across all studies where this variant appeared
- `n_studies` — number of studies contributing to `pip_max`

Positive count: 42,093 (58% base rate — deliberately not matched, since you
know how to handle imbalance). Genome-wide coverage across all 22 autosomes.

### `test.parquet` — 11,400 rows

Columns: `chrom`, `pos`, `ref`, `alt`. **No `label`. No features.**

These are TraitGym `complex_traits_matched_9` variants (10% base rate).
Any TraitGym-official file that ships labels for these variants is
off-limits — see rules.

## Feature extraction is on you

You decide what features to compute, from what sources, and how to
encode them. Reasonable resources (network is available from the
container):

- **UCSC bigWig hub** — phyloP (100-way, 30-way, primate), phastCons (100-way,
  primate), GERP, chromatin state calls, DNase, ATAC, histone marks,
  RNA-seq, TF ChIP, etc. `pyBigWig` supports HTTP range reads — no need to
  download whole files.
- **CADD API** — https://cadd.gs.washington.edu/api/v1.7, POST/GET per-variant.
- **gnomAD** — allele frequencies, s_het, constraint (LOEUF, missense z), via
  their API or downloadable VCF tabix files.
- **Ensembl VEP REST API** — variant consequence, distance to nearest TSS,
  regulatory feature overlap, transcript context.
- **ENCODE candidate cis-regulatory elements** (cCREs) — bigBed on hgdownload.
- **Zoonomia** phyloP-241m / phastCons-43p bigWigs (UCSC track hub;
  the specific file paths take a minute to find).
- **DNA foundation models** — you can `pip install` and download weights for
  things like `Nucleotide-Transformer`, `HyenaDNA`, `Enformer`, `Borzoi`,
  `Evo 2` (small variants). You have an A10G GPU (24 GB VRAM). Running Enformer
  on 80K windows is ~1 hour; running Evo 2 on that many is slower. Pick
  what fits your compute budget.
- **Reference genome** — hg38 fasta at `https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz`
  if you want to build ref/alt windows for a DNA-LM inference pass.
- **Protein-language models** — for coding variants, ESM-2 log-likelihoods
  are useful. You can load `facebook/esm2_t33_650M_UR50D` from HuggingFace
  and run inference locally on the container GPU. This test set is mostly
  noncoding though.

You can also install and use anything else you find useful:
`pyBigWig`, `pysam`, `requests`, `bx-python`, `torch`, `transformers`,
`peft`, `xgboost`, `lightgbm`, `scikit-learn`, `pandas`, `pyarrow` are
already installed. `pip install <x>` in the container works.

## Compute + wall clock

Modal A10G container: 8 CPU, 32 GB RAM, 24 GB VRAM, ~4 hours. Feature
extraction over 80K variants can eat most of that if you run a big FM;
budget accordingly.

## Deliverables

- `answer.parquet` — columns `chrom, pos, ref, alt, causal_prob`, exactly
  11,400 rows, `causal_prob ∈ [0, 1]`.
- `method.md` (< 500 words) — what features you extracted, from what
  sources, what model you fit, what you tried, what you dropped.
- `training_manifest.json` — every URL / API / dataset you touched.

## Rules

- **You cannot see the test labels.** No CV on the test set, no metric
  computed against test.
- **No fetching TraitGym-labeled files.** The 11,400 test variants come
  from TraitGym `complex_traits_matched_9`. Do not fetch that HuggingFace
  file (or `test.parquet` from any other TraitGym release, `complex_traits_all`,
  or the paper's `AUPRC/*.csv` prediction tables). Any of those would leak
  labels or baselines.
- **Trained model must fit only on `train.parquet`.** You may use test-set
  variant positions to determine which features to extract for the test
  rows — that's fine, it's what any inference does — but do not use test
  positions to *train*.
- Anti-leak already applied: 697 variants that overlap TraitGym's test set
  were removed from `train.parquet` before you got it.
- **One-shot.** No CV, no hyperparameter tuning against test. Whatever
  validation strategy you build, it must sit inside `train.parquet` alone.
