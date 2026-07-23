# `bacdive_gram` — bacterial Gram-staining from genome, family-holdout blind

## Task

Predict Gram-staining status from bacterial genome assemblies. Test
strains are drawn from **families disjoint from the training set** so
species / genus / family memorization doesn't work. The agent gets an
NCBI assembly accession + phylum for each strain — nothing more
granular — and must fetch the actual genome, extract features, train a
model on the labeled training strains, and score the test strains.

## Why this shape

- **Genotype → phenotype is the point.** Shipping only accessions + a
  coarse taxonomy rank forces the agent to look at the genome sequence,
  not a species name.
- **Family holdout is where the interesting comparison lives.** Species
  holdout on Gram staining is easy — closely related strains almost
  always agree. Family holdout tests whether the agent has learned
  something mechanistic (peptidoglycan / LPS / teichoic-acid pathway
  content) rather than a bag of family-marker features.

## Regenerate the bundle

```bash
python tasks/bacdive_gram/build.py
```

Downloads:
- **Madin et al. 2020** `condensed_traits_NCBI.csv` (~44 MB, CC-BY) from
  the figshare collection 4843290 — 170k prokaryote strain records with
  Gram staining and NCBI tax_id.

Then for each labeled bacterial species with a Gram call:
1. De-duplicate by `species_tax_id`, keeping only species where all
   source records agree on Gram.
2. 80/20 family-level holdout (seed 0).
3. Query NCBI Datasets Rest API v2 for the best RefSeq reference
   assembly per species. Skip species without one.
4. Cap to 3,000 train + 500 test strains.
5. Ship `assembly_accession` + `phylum` for both sides, plus `label`
   for train only.
6. Hidden ground-truth answer file per test row.

## Run

```bash
uv run modal run harness/modal_runner.py::volume_upload --task bacdive_gram
uv run modal run --detach harness/modal_runner.py::launch --task bacdive_gram
```

## Grade

```bash
python tasks/bacdive_gram/grade.py \
    --submission tasks/bacdive_gram/runs/<run_id>/answer.parquet \
    --out       tasks/bacdive_gram/runs/<run_id>/grade.json
```

Deterministic. Joins on `assembly_accession`, reports AUPRC / AUROC /
Brier / coverage.

## Design constraints

- **Only assembly accession + phylum ship.** Genus / family / species /
  strain name are withheld from the shipped test partition so the agent
  can't Google the label.
- **Family-holdout at build time.** Test families are disjoint from
  training families.
- **Blacklist** in `prompt.md`: BacDive per-strain exports, Madin
  et al. phenotypic-trait tables, PATRIC / BV-BRC per-strain pages, and
  any NCBI page that exposes the organism species name for a shipped
  test accession. Fetching the assembly FASTA / annotation / protein
  set for that accession is fine — that's sequence data.

## Baseline calibration to run before we treat this task as production

- **Codon usage + tetranucleotide frequency + logistic regression** —
  the classic Gram predictor from genome content. Compute on train only,
  score on test. Should land ~0.85 AUROC on family-holdout.
- **LPS / peptidoglycan biosynthesis pathway hits** — search for KEGG
  KO ids specific to Gram-negative outer membrane biogenesis. Should
  land somewhere around AUPRC 0.75–0.85 alone.

Once those are computed on the exact test split we ship, bake them
into `grade.py`'s `REFERENCE_BASELINES` in place of the current
placeholder bars.

## Future expansions (v1+)

The Madin table has multiple binary/ordinal phenotypes; each is a
plausible sibling task with the same family-holdout shape:

- Oxygen requirement (aerobic vs. anaerobic vs. facultative)
- Sporulation (yes/no)
- Motility (yes/no)
- Cell shape (rod/coccus/spiral)
- Salinity tolerance (halotolerant vs. not)
- Temperature range (mesophile vs. thermophile vs. psychrophile)

Adding any one is a copy-of-this-task-dir + change of `label` column
extraction in `build.py`. The prompt / grader are otherwise
task-agnostic.
