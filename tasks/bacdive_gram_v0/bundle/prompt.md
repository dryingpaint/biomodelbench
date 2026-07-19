# BioModelBench — Bacterial Gram-staining (bacdive_gram_v0)

## Task

For each row in `test.parquet`, predict `gram_prob ∈ [0, 1]`: the
probability the strain is **Gram-positive**. The label is binary
(Gram-positive = 1, Gram-negative = 0).

Test strains are drawn from bacterial families **not present** in the
training set, so genus/family memorization won't work. You have the
assembly accession + phylum for each strain — that's it. No genus, no
species, no strain name.

Your job is to fetch the genome sequence for each accession and extract
whatever features you think predict Gram staining, then train a model
on the shipped training set and score the test strains.

Test labels are hidden. You cannot evaluate against them.

## What's shipped

### `train.parquet`

Columns:
- `assembly_accession` (string, e.g. `GCF_000005845.2` or `GCA_…`) —
  NCBI assembly accession. Fetch the actual genome from NCBI
  (RefSeq/GenBank) using this.
- `phylum` (string) — coarse taxonomy. Kept in case you want it as a
  feature.
- `label` (int, 0/1) — 1 = Gram-positive, 0 = Gram-negative.

### `test.parquet`

Columns: `assembly_accession`, `phylum`. **No `label`.**

Same shape as train, minus the label. The rows come from families
disjoint from the training set.

## Compute

Modal container: A10G GPU (24 GB VRAM), 8 CPUs, 96 GB RAM. Python 3.11
with `torch / transformers / peft / xgboost / lightgbm / scikit-learn /
pandas / pyarrow / numpy / pyBigWig / pysam / biopython / requests`
pre-installed. `pip install <x>` works.

**Budget: ~10 hours of GPU compute.** Use it. Even after you produce a
valid `answer.parquet`, keep iterating until the budget is genuinely
exhausted. The runner will relaunch your session with a continuation
prompt if you exit early — don't finalize prematurely.

You have unrestricted outbound internet (subject to the leak-prevention
list below). What resources, tools, models, or approaches you use is
entirely your call. Log every URL / API you touch to
`training_manifest.json` for audit.

## Leak prevention — DO NOT FETCH

These would trivially leak the label:

- **BacDive** — any bulk export, API endpoint, or scraped page that
  returns per-strain Gram staining. Includes `bacdive.dsmz.de/*` and any
  Zenodo / GitHub mirror.
- **Madin et al. 2020 phenotypic trait tables** — figshare 13089049 and
  its Zenodo / GitHub mirrors. This is the paper the training labels
  were derived from and its published tables list Gram staining
  per-strain.
- **PATRIC / BV-BRC per-strain phenotype pages.**
- **NCBI Assembly / BioSample / Taxonomy web pages that expose the
  organism species name for the shipped test accessions.** Fetching
  the assembly FASTA is fine; fetching the human-readable species /
  strain name for a test accession is not (it lets you look up the
  answer by species).
- Any general-purpose LLM search that would return the species name
  for a shipped test accession.

Assembly FASTA / GFF3 / protein-FAA files are fair game — those are
sequence data, not label data.

### Anti-leak protocol

1. When you fetch assembly data, request FASTA / annotation only.
   Do NOT parse the organism-name field back into a species lookup for
   test strains.
2. If you build a supervised model, train only on the strains in
   `train.parquet`. Don't augment the training set with per-strain
   phenotype tables from BacDive / Madin / etc.
3. Report your anti-leak stance in `method.md`.

## Deliverables

- `answer.parquet` — columns `assembly_accession, gram_prob`, one row
  per test strain, `gram_prob ∈ [0, 1]`.
- `method.md` (< 500 words) — genomes-fetched count, feature extraction
  pipeline, model, validation strategy (must sit within
  `train.parquet`), anti-leak notes.
- `training_manifest.json` — every URL / API / dataset touched.

## Reference bar

Test-set base rate: ~0.34 Gram-positive. The exact reference-baseline
AUPRC on this specific family-holdout split will be computed and baked
into `grade.py` before this task is treated as production. As a rough
ballpark, published Gram predictors on family-holdout land around
AUPRC 0.7–0.9.

## Rules recap

- No test labels visible. No self-evaluation against test.
- Assembly sequence + coarse taxonomy is what you have. No species /
  strain / genus lookup for shipped test accessions.
- No fetching from the leak-prevention list above.
- Whatever validation strategy you use, it must sit inside
  `train.parquet`.
