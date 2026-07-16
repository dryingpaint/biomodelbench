# BioModelBench — VEP-C (open data discovery) v0

## Task

Predict, for each variant in `test.parquet`, the probability that it is a
**GWAS-fine-mapped causal SNP for a complex trait** (label 1) vs. a
matched non-causal control (label 0).

**No training data is shipped.** You have only 11,400 test variant IDs
(chrom, pos, ref, alt) — no labels, no features. To build a supervised
model you must find your own labeled training corpus online, from an
allowed source, and construct your own features.

Test labels are hidden. You cannot evaluate against them. Whatever
validation you set up must sit inside the training data you find.

## What's shipped

### `test.parquet` — 11,400 rows

Columns: `chrom` (string, 1-22), `pos` (int, hg38 1-based), `ref`, `alt`.
**No `label`. No features.**

The 11,400 rows are TraitGym `complex_traits_matched_9` variants (10%
positive rate). See the "Do not fetch" list below.

## Where to look for training labels

### Allowed sources (safe to use for training labels + features)

- **Open Targets Genetics** — fine-mapped GWAS credible sets across many
  studies. FTP root:
  `https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/credible_set/`
  Filter to `studyType == "gwas"`, take variants with high posterior
  inclusion probability (`posteriorProbability >= 0.9`) as positives.
  There is genuine overlap with TraitGym's test set (~700 variants) — you
  must drop those before training. Match on the exact
  `(chrom, pos, ref, alt)` tuple.
- **CausalDB** — a smaller curated fine-mapping database.
- **gnomAD** — constraint scores (LOEUF, missense z, s_het), allele
  frequency. Safe as features; can also serve as weak labels for
  functional impact.
- **UCSC bigWig / bigBed hub** — conservation (phyloP, phastCons, GERP,
  Zoonomia phyloP-241m), chromatin state, DNase, ATAC, TF ChIP,
  histone marks. `pyBigWig` supports HTTP range reads.
- **ENCODE** — candidate cis-regulatory elements (cCREs), functional
  genomics tracks. `www.encodeproject.org` or the UCSC mirror.
- **Ensembl VEP REST API** — variant annotation (consequence, TSS
  distance, regulatory feature overlap).
- **CADD API** — `https://cadd.gs.washington.edu/api/v1.7`, POST/GET
  per-variant.
- **HuggingFace model weights** — any model repo is fine (Enformer,
  Borzoi, Nucleotide-Transformer, HyenaDNA, Evo 2, ESM-2, …).
- **hg38 reference FASTA** — `https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz`.

### Blacklisted sources — DO NOT FETCH

Fetching from any of these leaks the test labels or their close relatives:

- `huggingface.co/datasets/songlab/TraitGym/*` — including
  `complex_traits_matched_9/*`, `complex_traits_all/*`,
  `complex_traits_v22_matched_9/*`, `mendelian_traits_*`, and their
  companion `AUPRC/*` prediction tables.
- **Kanai et al. 2022 UKBB fine-mapping** — the source TraitGym positives
  were derived from. Zenodo / Finucane lab distribution.
- **PolyFun / SuSiE published outputs on UK Biobank traits** for any of
  the 62 traits present in TraitGym.
- **HuggingFace `datasets/songlab/*`** — anything under this namespace.
- Any Google Drive / Dropbox / Zenodo mirror of the above.

If you catch yourself about to fetch a URL that looks TraitGym-adjacent,
stop and use an allowed source instead. Log everything you fetch to
`training_manifest.json`.

### Anti-leak protocol (mandatory)

1. Whatever training labels you assemble, **drop every row whose
   `(chrom, pos, ref, alt)` appears in `test.parquet`.**
2. Prefer training sources whose positives were fine-mapped from
   non-UKBB cohorts, or from UKBB traits that are not in TraitGym's
   62-trait list. Both are hard to fully guarantee from raw sources —
   step (1) is the concrete backstop.
3. Report your anti-leak drop count in `method.md`.

## Compute in-container

Modal A10G, 8 CPU, 32 GB RAM, 24 GB VRAM, Python 3.11 with
`torch / transformers / peft / xgboost / lightgbm / scikit-learn /
pandas / pyarrow / numpy / pyBigWig / pysam / biopython / requests`
pre-installed. `pip install <x>` works. Wall clock ~4 hours.

## Deliverables

- `answer.parquet` — columns `chrom, pos, ref, alt, causal_prob`,
  exactly 11,400 rows, `causal_prob ∈ [0, 1]`, joined 1-to-1 with
  `test.parquet` on the natural key.
- `method.md` (< 500 words) — training source you chose and why; anti-
  leak drop count; features extracted from which URLs; model architecture
  and validation strategy (must sit within your training set, since
  test has no labels).
- `training_manifest.json` — every URL / API / dataset you touched.

## Reference bar

Reported single-feature AUPRCs on this same 11,400-variant test set
(TraitGym-derived, computed once and baked in as a rough calibration):

| Baseline | AUPRC | AUROC |
|---|---:|---:|
| phyloP-241m (Zoonomia mammalian) | 0.2352 | 0.6146 |
| phastCons-43p (Zoonomia primate) | 0.2245 | 0.6168 |
| GPN-MSA_absLLR | 0.2081 | 0.6068 |
| phyloP-100v (UCSC vertebrate) | 0.1717 | 0.5833 |
| phastCons-100way (UCSC vertebrate) | 0.1814 | 0.5763 |
| evo2_40b_LLR | 0.1265 | 0.5161 |

Base rate is 10%. Beating any of these means your training data +
features + model are doing real work.

## Rules recap

- No test labels visible. No self-evaluation against test.
- No fetching from blacklisted sources above.
- Anti-leak filter is your responsibility.
- Whatever validation strategy you use, it must sit inside your chosen
  training set.
