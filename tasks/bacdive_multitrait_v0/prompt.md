# BioModelBench — Bacterial multi-phenotype profile (bacdive_multitrait_v0)

## Task

For each row in `test.parquet`, predict a joint phenotypic profile for
that strain across 18 targets covering growth conditions, cell
properties, and metabolic pathways. Test strains are drawn from
bacterial families disjoint from the training set. You get the NCBI
assembly accession + phylum for each strain — no genus, species,
family, strain name, or organism name.

## What's shipped

### `train.parquet`

Columns:
- `assembly_accession` (string, e.g. `GCF_000005845.2`)
- `phylum` (string, coarse taxonomy)
- 18 label columns (below). **Some cells will be NaN** — not every
  training species has every phenotype characterized. Handle
  missing-target training gracefully.

### `test.parquet`

Columns: `assembly_accession`, `phylum`. No labels.

## `answer.parquet` schema — 19 columns

| column | type | notes |
|---|---|---|
| `assembly_accession` | string | one row per test strain |
| `gram_positive_prob` | float ∈ [0,1] | probability strain is Gram-positive |
| `oxygen_tolerance` | string label | one of: `aerobic`, `anaerobic`, `facultative`, `microaerophilic` |
| `optimum_temperature_c` | float | °C, growth optimum |
| `optimum_ph` | float | pH units |
| `temperature_range` | string label | one of: `psychrophilic`, `mesophilic`, `thermophilic`, `extreme_thermophilic` |
| `sporulation_prob` | float ∈ [0,1] | probability strain forms endospores |
| `motility_prob` | float ∈ [0,1] | probability strain is motile |
| `cell_shape` | string label | one of: `bacillus`, `coccus`, `spiral`, `coccobacillus`, `vibrio`, `filament`, `other` |
| `pathway_nitrogen_fixation_prob` | float ∈ [0,1] | encodes N₂ fixation machinery |
| `pathway_nitrate_reduction_prob` | float ∈ [0,1] | reduces NO₃⁻ (assimilatory or dissimilatory) |
| `pathway_denitrification_prob` | float ∈ [0,1] | full denitrification pathway |
| `pathway_sulfate_reduction_prob` | float ∈ [0,1] | dissimilatory sulfate reduction |
| `pathway_fermentation_prob` | float ∈ [0,1] | fermentative metabolism |
| `pathway_cellulose_degradation_prob` | float ∈ [0,1] | cellulolytic |
| `pathway_xylan_degradation_prob` | float ∈ [0,1] | xylanolytic |
| `pathway_chitin_degradation_prob` | float ∈ [0,1] | chitinolytic |
| `pathway_fumarate_reduction_prob` | float ∈ [0,1] | fumarate as terminal electron acceptor |
| `pathway_iron_reduction_prob` | float ∈ [0,1] | dissimilatory Fe(III) reduction |

Every column must be present. Use NaN if you decline to predict a
value — the grader will count that as coverage loss.

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

- `answer.parquet` — 19 columns as above, one row per test strain.
- `method.md` (< 500 words).
- `training_manifest.json` — every URL / API / dataset touched.

## What the grader does

Joins your `answer.parquet` against the hidden per-target labels on
`assembly_accession`. For each target independently, computes the
per-target metric on the subset of test strains where the ground-truth
label is not NaN. Reports:

- Per-target: primary metric + coverage + baseline gap
- Per-tier: normalized composite (Tier 1 growth, Tier 2 morphology, Tier 3 metabolism)
- Overall: weighted composite

Metrics by target type:
- Binary probability targets → **AUPRC + AUROC + Brier**
- Multiclass label targets → **macro-F1 + balanced accuracy**
- Continuous float targets → **Spearman ρ + MAE**
- Pathway probability targets → **AUPRC + AUROC**

## Reference bars (family-holdout, from literature)

Tier 1 (growth & culturability, weight 0.40):

| Target | Metric | Ref baseline |
|---|---|---:|
| `oxygen_tolerance` | macro-F1 | 0.70 |
| `optimum_temperature_c` | Spearman ρ | 0.70 |
| `optimum_ph` | Spearman ρ | 0.35 |
| `temperature_range` | macro-F1 | 0.60 |

Tier 2 (morphology & dispersal, weight 0.30):

| Target | Metric | Ref baseline |
|---|---|---:|
| `gram_positive_prob` | AUROC | 0.95 |
| `sporulation_prob` | AUROC | 0.90 |
| `motility_prob` | AUROC | 0.85 |
| `cell_shape` | macro-F1 | 0.55 |

Tier 3 (metabolic pathways, weight 0.30, averaged macro-AUPRC ≈ 0.72):

| Pathway | AUPRC ref |
|---|---:|
| `nitrogen_fixation` | 0.90 |
| `sulfate_reduction` | 0.80 |
| `nitrate_reduction` | 0.75 |
| `denitrification` | 0.75 |
| `cellulose_degradation` | 0.75 |
| `xylan_degradation` | 0.70 |
| `chitin_degradation` | 0.70 |
| `fermentation` | 0.65 |
| `iron_reduction` | 0.60 |
| `fumarate_reduction` | 0.55 |

Base rates on the test partition and per-target coverage are reported
in `hidden/build_stats.json` post-build.
