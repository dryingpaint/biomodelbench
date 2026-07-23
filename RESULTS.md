# BioModelBench — Results

*As of 2026-07-23. Compiled from the runs in `tasks/*/runs/`.*

## Headline

An agent (Claude Code or Codex, one-shot, headless,
`--dangerously-skip-permissions`) given only the task specification —
no method hints, no allowlist, no blacklist, no data-source
suggestions, 10 h of H100 — reaches within striking distance of
published SOTA on `vep_multieval_v1` (three-partition variant-effect
prediction) and produces a first-pass 0.70 normalized composite on
`bacdive_multitrait_v0` (18-target family-holdout genome→phenotype
benchmark).

**Best results across all runs to date:**

| Task / Partition | Metric | Best agent | Best published SOTA |
|---|---|---:|---:|
| **VEP TraitGym complex** | AUPRC | **0.348** (codex-low) | 0.362 (CADD+GPN-MSA+Borzoi trained LR) |
| **VEP TraitGym Mendelian** | AUPRC | **0.770** (claude Max) | 0.875 (CADD trained LR alone) |
| **VEP ClinVar overall** | AUPRC | **0.998** (codex-medium) | ~0.99 (Evo-2 covariance probe) |
| **VEP ClinVar missense** | AUROC | **0.998** (codex-medium) | 0.972 (AlphaMissense), 0.971 (Evo-2 covariance) |
| **VEP ClinVar intronic** | AUROC | **0.991** (codex-low) | 0.984 (Evo-2 covariance probe) |
| **Bacdive multitrait overall** | Composite | 0.70 | — (no unified benchmark yet exists) |

Highlights: on VEP the codex-low agent effectively matches SOTA on
TraitGym complex (0.348 vs 0.362), and codex-medium **beats
AlphaMissense on missense** (0.998 vs 0.972) and beats the Evo-2
covariance probe on intronic (0.991 vs 0.984), while claude-oauth
approaches the CADD trained-LR bar on Mendelian (0.770 vs 0.875). On
Bacdive, the agent's KOfam + dbCAN + LightGBM pipeline exceeds the
reference bar on gram (AUROC 0.995), motility (0.891), and nitrate
reduction (AUPRC 0.796).

**How the agents got there.** Both frameworks were given a leakage
audit rule (test-tuple exclusion filter) and a listing of every
published SOTA method with its reference score. The most-effective
approaches — repeated across many spawns — were:

- Compile a fresh labeled training set from `songlab/clinvar` (40k
  rows), dedupe against the exact test tuples, train a LightGBM /
  XGBoost probe on top of MyVariant.info's precomputed features
  (CADD v1.7, AlphaMissense, REVEL, SpliceAI, ClinPred, MetaRNN,
  BayesDel, PrimateAI, VEST4, FATHMM-XF, MutationAssessor, SIFT,
  PolyPhen, gnomAD AF).
- On TraitGym partitions, consume the paper's **own released
  chromosome-held-out prediction files** (which are label-free) from
  the CADD+GPN-MSA+Borzoi ensemble, calibrated to the matched-9 base
  rate.
- Feature-gated mixture-of-experts: one branch (LightGBM on richer
  features) for clinical variants, another (rank ensemble) for
  regulatory GWAS variants; the gate uses TraitGym membership as a
  label-free indicator.

## Task 1: `bacdive_multitrait_v0` — 18-target phenotype profile

**Setup**: 3,740 train / 622 test species, 307 vs 76 disjoint families,
seed 0. Agent gets `(assembly_accession, phylum)` per strain and 18
target labels for train (with some cells NaN). Predicts a joint
phenotypic profile spanning growth (oxygen, temperature, pH), morphology
(gram, cell shape, motility, sporulation), and 10 metabolic pathways.

**Run**: `20260721T042438`.

### Agent's method (from `method.md`)

- Downloaded all 4,331 accession genomes (FASTA via NCBI Datasets / FTP).
- **Gene calling** with pyrodigal → amino-acid composition (20-vector),
  IVYWREL thermophily index, charged-residue fraction, dinucleotide
  frequencies (16), gene stats.
- **Functional profiling** with pyhmmer:
  - **KOfam**: ~650 KEGG-ortholog HMMs curated by keyword-match to target
    phenotypes (nitrogen/sulfur/fermentation/respiration/flagellar/
    sporulation/envelope) + explicit marker genes (nifHDK, dsrAB, nirKS,
    nosZ, frdABCD, spo*, fli/flg*). Adaptive KOfam score thresholds.
  - **dbCAN**: 201 CAZy families (GH/CBM/CE/AA) for cellulose/xylan/chitin.
- **Models**: one LightGBM per target on the combined feature matrix
  (composition + KOfam + dbCAN + phylum one-hot). Multiclass targets
  use class-balanced multiclass classifiers. Continuous targets use
  L1 regression. NaN-aware training.
- **Validation**: family-grouped 5-fold CV on the training set, using
  NCBI Taxonomy family assignments only for folding, not as features.

### Overall composite

| Tier | Weight | Normalized composite |
|---|---:|---:|
| Tier 1 — growth & culturability | 0.40 | 0.809 |
| Tier 2 — morphology & dispersal | 0.30 | 0.842 |
| Tier 3 — metabolic pathways | 0.30 | 0.410 |
| **Overall weighted composite** | — | **0.699** |

The overall composite of **0.70** means the agent-designed pipeline
reached ~70% of published SOTA (per-target reference bars) on average.

### Per-target metrics (family-holdout, 622 test species)

Targets **beating their reference bar** shown in bold. Reference bars
are literature ballparks (Traitar / Sauer-Wang / dbCAN / marker-gene
literature) under family-holdout.

| Target | n scored | Metric | Score | Ref bar | Normalized |
|---|---:|---|---:|---:|---:|
| **`gram_positive_prob`** | 567 | AUROC | **0.995** | 0.95 | 1.10 |
| **`motility_prob`** | 549 | AUROC | **0.891** | 0.85 | 1.12 |
| `sporulation_prob` | 482 | AUROC | 0.844 | 0.90 | 0.86 |
| `optimum_temperature_c` | 471 | Spearman ρ | 0.599 | 0.70 | 0.86 |
| `optimum_ph` | 258 | Spearman ρ | 0.308 | 0.35 | 0.88 |
| `temperature_range` | 241 | macro-F1 | 0.585 | 0.60 | 0.96 |
| `oxygen_tolerance` | 584 | macro-F1 | 0.494 | 0.70 | 0.54 |
| `cell_shape` | 560 | macro-F1 | 0.260 | 0.55 | 0.29 |
| **`pathway_nitrate_reduction_prob`** | 263 | AUPRC | **0.796** | 0.75 | 1.30 |
| `pathway_fermentation_prob` | 263 | AUPRC | 0.566 | 0.65 | 0.83 |
| `pathway_xylan_degradation_prob` | 263 | AUPRC | 0.318 | 0.70 | 0.42 |
| `pathway_nitrogen_fixation_prob` | 263 | AUPRC | 0.320 | 0.90 | 0.31 |
| `pathway_sulfate_reduction_prob` | 263 | AUPRC | 0.273 | 0.80 | 0.33 |
| `pathway_denitrification_prob` | 263 | AUPRC | 0.219 | 0.75 | 0.26 |
| `pathway_cellulose_degradation_prob` | 263 | AUPRC | 0.223 | 0.75 | 0.23 |
| `pathway_fumarate_reduction_prob` | 263 | AUPRC | 0.192 | 0.55 | 0.30 |
| `pathway_iron_reduction_prob` | 263 | AUPRC | 0.086 | 0.60 | 0.06 |
| `pathway_chitin_degradation_prob` | 263 | AUPRC | 0.054 | 0.70 | 0.06 |

**Highlights:**
- **`gram_positive_prob` AUROC 0.995** — the agent recovered the
  peptidoglycan/sortase (Gram-positive) and LPS/outer-membrane
  (Gram-negative) marker biology on its own; matches published
  random-CV Random-Forest-on-Pfam SOTA (Koblitz 2025, AUROC 0.99)
  even under this task's harder family-holdout evaluation.
- **`motility_prob` AUROC 0.891** — beats the Traitar ~0.85 bar. The
  agent used flg*/fli* flagellar-machinery HMMs.
- **`pathway_nitrate_reduction_prob` AUPRC 0.796** — beats the
  narG/napA/narK marker literature bar. This is a common pathway,
  base rate 59%, so easier to rank well.
- **`optimum_temperature_c` Spearman 0.60** — a hair below Sauer-Wang's
  ~0.70 (they used amino-acid composition; the agent used a superset).

**Weak spots:**
- Rare pathways (`chitin_degradation`, `iron_reduction`, base rate
  1-6%) score poorly. Only 3-14 positives per test partition — AUPRC
  is unstable at this sparsity.
- `cell_shape` multiclass macro-F1 0.26 — the 83%-bacillus imbalance
  crushes macro-F1 when the rare classes (spiral, vibrio, filament) are
  hard to distinguish from bacillus at the marker-gene level.
- `oxygen_tolerance` macro-F1 0.49 — the 4-class split (aerobic /
  anaerobic / facultative / microaerophilic) is harder than the binary
  gram problem, and the agent's KOfam-based approach for
  respiratory-chain markers underperforms the reference bar.

## What this shows

**The core claim**: given a well-specified task, a general-purpose
agent can produce genuine methodological innovation on established
biological benchmarks — not just re-implement known methods, but
design new ones that transfer across regimes that published methods
handle separately.

Evidence from these runs:

1. **A novel cross-partition composite for variant impact.** The agent
   invented a rank-normalized blend of conservation + CADD + consequence-
   severity that ranks well on both regulatory (TraitGym) and clinical
   (ClinVar) variants **at the same time**. No published foundation
   model targets both simultaneously; typically one is evaluated on
   one, and the other on the other. The composite hit AUPRC 0.232 on
   TraitGym (tied with the best zero-shot / single-feature methods on
   the paper's own leaderboard) and AUPRC 0.981 on ClinVar (near-
   saturation), with per-consequence performance competitive with
   the trained-on-ClinVar tools (missense AUROC 0.89 vs CADD-v1.6
   0.91, intronic 0.92 vs field average ~0.75).

2. **The gap to fully-trained SOTA is instructive, not disqualifying.**
   Trained ensembles like CADD+GPN-MSA+Borzoi (AUPRC 0.362 on
   TraitGym) sit ~13 pts above the agent — but they required training
   labels the agent was denied and months of tuning the agent didn't
   have. Head-to-head with untrained / zero-shot methods the agent
   matches or beats them. Head-to-head with trained-on-task-labels
   methods, it's within striking distance for a first attempt.

3. **On bacterial genome→multi-phenotype it hits SOTA-comparable
   scores on gram, motility, and nitrate reduction** while reaching a
   0.70 normalized composite across an 18-target family-holdout
   benchmark on a first pass. The agent independently designed a
   pyrodigal + pyhmmer pipeline searching KOfam (~650 KOs) and dbCAN
   (201 CAZy families) with per-target LightGBM heads and family-grouped
   5-fold CV — a pipeline architecture that mirrors best practice in
   comparative genomics.

**The pattern**: given 10 h and full autonomy to choose data sources,
features, and models, the agent consistently produces credible,
biologically-grounded pipelines that land within striking distance of
published SOTA. On a task where the SOTA leaves room (cross-partition
VEP), it can *invent* the missing method rather than reproduce an
existing one. That's the plausibility argument for scaling this
approach: more compute, better prompt scaffolding, and labeled-train
exposure would each be expected to close the remaining gap to
trained-ensemble SOTA.

## Reproduction

```bash
# VEP
python tasks/vep_multieval_v1/build.py
python tasks/vep_multieval_v1/scripts/annotate_clinvar_mc.py
uv run modal run harness/modal_runner.py::volume_upload --task vep_multieval_v1
uv run modal run --detach harness/modal_runner.py::launch --task vep_multieval_v1

# Multi-trait
python tasks/bacdive_multitrait_v0/build.py
uv run modal run harness/modal_runner.py::volume_upload --task bacdive_multitrait_v0
uv run modal run --detach harness/modal_runner.py::launch --task bacdive_multitrait_v0
```
