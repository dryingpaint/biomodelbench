# `bacdive_multitrait_v0` — genome-to-phenotype-profile, family-holdout

Predict a **culturability + ecology + metabolism** profile for a
bacterial strain from its genome alone. Test strains are drawn from
bacterial families **disjoint from the training set**, so taxon-name
memorization does not work. The agent gets an NCBI assembly accession
plus a coarse phylum tag — nothing more granular.

## Why this task

Metagenomic and 16S surveys routinely identify novel bacterial lineages
whose **phenotypes are unknown**. Without knowing whether a strain is
aerobic, spore-forming, thermophilic, or capable of nitrogen fixation,
you cannot design an isolation medium, cannot interpret its ecological
role, and cannot predict its response to perturbation. Genome-to-
phenotype prediction is the bridge that turns "who is present" into
"what they do."

Prior work exists but has known gaps:

- **Traitar** (Weimann et al. 2016, mSystems) — 67 traits from Pfam
  patterns; strong within-family, drops sharply on family-holdout.
- **gRodon** (Weissman et al. 2021, PNAS) — doubling time from codon
  usage; species-level R²≈0.7, drops cross-family.
- **Sauer & Wang 2019** — optimum growth temperature from amino acid
  composition; Spearman ~0.75 in seen taxa.
- **CAZy / dbCAN** — carbohydrate-active enzymes → substrate
  utilization; F1 0.65–0.80 depending on substrate.
- **PICRUSt2 / Tax4Fun** — functional prediction from 16S; not per-
  genome, taxonomy-mediated.

None of these evaluate the full trait profile on a **single strict
family-holdout benchmark**. That's what this task is.

## Task shape

- Input: `assembly_accession` (NCBI GCF_/GCA_) + `phylum` per strain.
- Output: 18-column phenotypic profile per test strain.
- Family-level 80/20 holdout at build time (seed 0); test families are
  disjoint from train families.
- Some train labels are NaN (not every species has every phenotype
  characterized); grader masks NaN per-target on the test side too.

## Tiers, targets, and metrics

**Tier 1 — growth & culturability (weight 0.40)**

| target | type | metric | ref bar |
|---|---|---|---:|
| `oxygen_tolerance` | 4-class | macro-F1 | 0.70 |
| `optimum_temperature_c` | continuous | Spearman ρ | 0.70 |
| `optimum_ph` | continuous | Spearman ρ | 0.35 |
| `temperature_range` | 4-class | macro-F1 | 0.60 |

**Tier 2 — morphology & dispersal (weight 0.30)**

| target | type | metric | ref bar |
|---|---|---|---:|
| `gram_positive_prob` | binary | AUROC | 0.95 |
| `sporulation_prob` | binary | AUROC | 0.90 |
| `motility_prob` | binary | AUROC | 0.85 |
| `cell_shape` | 6-class | macro-F1 | 0.55 |

**Tier 3 — metabolic pathways (weight 0.30)**

10 pathway probability columns; primary metric macro-AUPRC averaged
across pathways. Reference: ~0.72. See `prompt.md` for the full list
of per-pathway reference bars.

## Data source

**Madin et al. 2020, Sci Data** — `condensed_traits_NCBI.csv`, 172k
strain records cross-referenced to NCBI Taxonomy, CC-BY. See
[figshare 13557827](https://figshare.com/articles/dataset/13557827).
Contains gram, metabolism, oxygen tolerance, cell shape, motility,
sporulation, optimum temperature, temperature range, optimum pH,
substrates, pathways, and more per bacterial species. This task
consumes a species-level dedupe of that table.

## Regenerate the bundle

```bash
python tasks/bacdive_multitrait_v0/build.py
```

Downloads:
- Madin `condensed_traits_NCBI.csv` (44 MB, CC-BY).

Then:
1. Filter to bacterial species with ≥3 of the 8 primary traits present
   and agreement across multiple source rows.
2. Family-level 80/20 holdout (seed 0).
3. Query NCBI Datasets Rest API v2 for one RefSeq/GenBank assembly per
   species.
4. Cap: 5,000 train / 800 test strains.
5. Ship `assembly_accession` + `phylum` for both; 18 label columns for
   train only (NaN allowed per-cell).
6. Hidden ground-truth per test row with same 18 label columns.

## Run

```bash
uv run modal run harness/modal_runner.py::volume_upload --task bacdive_multitrait_v0
uv run modal run --detach harness/modal_runner.py::launch --task bacdive_multitrait_v0
```

## Grade

```bash
python tasks/bacdive_multitrait_v0/grade.py \
    --submission tasks/bacdive_multitrait_v0/runs/<run_id>/answer.parquet \
    --out       tasks/bacdive_multitrait_v0/runs/<run_id>/grade.json
```

Deterministic. Per-target: primary metric + coverage + baseline gap.
Per-tier: normalized composite. Overall: weighted composite across
tiers.

## Design constraints

- **Only assembly accession + phylum ship.** Genus / family / species /
  strain name are withheld so the agent can't Google the labels.
- **Family-holdout at build time.** Test families are disjoint from
  training families.
- **No blacklist.** The agent is allowed to touch any online source it
  believes will help. Data leakage risk is bounded by the assembly-
  accession-only interface: any resource that maps GCF_ → phenotype
  directly (BacDive per-strain exports, Madin traits table) would give
  it the answer, and the honor system + literature norms are enough
  for now.
