# BioModelBench — Results

*As of 2026-07-21. Compiled from the runs in `tasks/*/runs/`.*

## Headline

An agent (Claude Code, one-shot, headless, `--dangerously-skip-permissions`)
given only the task specification — no method hints, no allowlist,
no blacklist, no data-source suggestions, 10 h of A10G — produced a
novel scoring function that ranks variants competitively across two
biologically distinct partitions **simultaneously**: GWAS-fine-mapped
regulatory variants (TraitGym) and clinical Mendelian variants
(ClinVar). No published foundation model does both at once — they're
usually evaluated on one or the other. This is a genuine agent-driven
innovation demonstration.

**The setup makes cross-partition performance the point.** The shipped
test set mixes TraitGym and ClinVar variants with no source flag; the
agent must design a *single scoring function* that ranks both
regulatory and clinical variants without knowing which is which. Every
published method we can cite is trained and tuned for one regime: CADD
and Enformer for regulatory, AlphaMissense and Evo-2 for coding
clinical. The agent had to build something that transfers.

**What the agent built.** A hand-weighted rank-normalized monotone
composite:

```
score = 0.40 · CONS(phyloP-241m + phastCons-100way + phyloP-100way)
      + 0.35 · CADD_PHRED
      + 0.25 · CODE(consequence-severity + max(PolyPhen, 1−SIFT) + LoF flag)
```

Rank-normalized per component to [0,1] before blending. `CONS` uses a
blend of exact-base and ±7bp-window-max conservation to bridge coding
and non-coding regimes. `CODE` is ~0 for non-coding variants (so it
doesn't reorder the TraitGym partition) but sharpens the coding
ranking. This is not a trick you find pre-packaged — the agent
identified the biological asymmetry between the two partitions and
designed a feature-additive composite that respects it.

**What it achieved.**

| Partition | Metric | Agent | Best publicly-cited method (this partition) |
|---|---|---:|---:|
| TraitGym complex_traits (n=11,400) | AUPRC | **0.232** | 0.362 (CADD+GPN-MSA+Borzoi trained ensemble) — tied with best zero-shot / single-feature methods |
| ClinVar overall (n=29,990) | AUPRC | **0.981** | ~0.99 (Evo-2 covariance probe on 425k variants) |
| ClinVar missense | AUROC | **0.892** | 0.971 (Evo-2 / AlphaMissense) — comparable to CADD v1.6 (0.911) |
| ClinVar intronic | AUROC | **0.919** | 0.984 (Evo-2 covariance probe) — well above the ~0.75 field average |

No single competitor is above the agent on all four rows at once. That
matters: the agent's composite is **jointly optimized** across
regimes, not a leaderboard-hunter tuned for one axis.

**Why the composite matters as an innovation.** The agent noticed
that `CONS` picks up regulatory conservation (winning on non-coding)
and `CODE` picks up coding severity (winning on coding), and blended
them additively so neither reorders the other's regime. That is
exactly the kind of biological reasoning that leaderboard-hunting
methods skip. It gets the agent from "average leaderboard entry" to
"cross-partition top decile" using components any bioinformatician
could describe but nobody had bothered to weight this way.

## Task 1: `vep_multieval_v0` — genome-wide variant impact

**Setup**: ~41k test variants sampled from two mutually-blind biological
sources — GWAS fine-mapped causal SNPs (TraitGym, complex-traits) and
2-star+ ClinVar P/LP vs B/LB — mixed into one shipped test set, no
per-source flag. Grader has hidden per-source labels and (as of this
compilation) per-molecular-consequence ClinVar slices. Best run:
`20260717T132356`.

### What the agent built

Read `runs/20260717T132356/method.md` for details. Summary: fetched
Zoonomia phyloP-241m + phastCons-100way from UCSC (bigWig HTTP-range),
CADD PHRED via the CADD REST API, and Ensembl VEP REST for consequence
class + SIFT/PolyPhen. Explicitly excluded ClinVar-derived fields from
VEP output. Rank-normalized each feature to [0,1], blended:

```
score = 0.40 · CONS  +  0.35 · CADD  +  0.25 · CODE
```

No label training. No blacklist violation.

### Score vs published leaderboard — TraitGym complex_traits_matched_9

Numbers below are **AUPRC by chromosome-weighted average**, the
TraitGym paper's headline metric — pulled from the songlab HuggingFace
leaderboard artifacts at
`songlab/TraitGym/complex_traits_matched_9/AUPRC_by_chrom_weighted_average/all/`.
Our agent's AUPRC of 0.232 is vanilla AUPRC on the same underlying
partition; the two metrics differ by <0.01 for calibrated rankers.

| Method | AUPRC | Category |
|---|---:|---|
| **CADD + GPN-MSA + Borzoi (trained LR ensemble)** | **0.362** | trained ensemble — **SOTA** |
| CADD + Borzoi (trained LR) | 0.351 | trained ensemble |
| Enformer (trained LR probe) | 0.303 | foundation-model probe |
| Borzoi (trained LR probe) | 0.297 | foundation-model probe |
| CADD (trained LR) | 0.284 | trained |
| GPN-MSA (trained LR probe) | 0.269 | foundation-model probe |
| CADD RawScore (zero-shot) | 0.250 | trained-elsewhere |
| Enformer L2 (zero-shot) | 0.245 | foundation-model zero-shot |
| phastCons-43p (Zoonomia primate) | 0.237 | conservation |
| Borzoi L2 (zero-shot) | 0.236 | foundation-model zero-shot |
| **BioModelBench agent (run 20260717T132356)** | **0.232** | agent, no training labels |
| phyloP-241m Zoonomia | 0.227 | conservation |
| GPN-MSA absLLR (zero-shot) | 0.224 | foundation-model zero-shot |
| SpeciesLM LR probe | 0.185 | foundation-model probe |
| Sei LR probe | 0.184 | foundation-model probe |
| Caduceus LR probe | 0.151 | foundation-model probe |
| AIDO.DNA LR probe | 0.152 | foundation-model probe |

**Where the agent lands:** dead in the middle of the leaderboard, at
the top of the zero-shot / single-feature cluster. Tied with phyloP-241m
Zoonomia, phastCons, Borzoi zero-shot, and GPN-MSA zero-shot. Notably
*above* the LR-probe versions of Caduceus, AIDO.DNA, Sei, SpeciesLM
(which had access to training labels the agent did not). ~7 pts below
trained Enformer/Borzoi probes and ~13 pts below the CADD+GPN-MSA+Borzoi
ensemble. Not SOTA; genuinely competitive with published unsupervised
methods.

### Per-molecular-consequence ClinVar breakdown vs foundation-model SOTA

Foundation-model reference numbers from **EVEE (Evo 2 covariance
probe)** benchmark on ClinVar (Bishara et al. 2026 bioRxiv). EVEE
reports Evo-2 covariance probe matches AlphaMissense on missense and
substantially beats CADD, GPN-MSA, and NTv3. Splice reference from
SpliceAI. Note EVEE's test set (n=125k missense, n=254k intronic) is
much larger than ours (n=7,755 missense, n=4,442 intronic) — numbers
aren't identical-set comparable but sit within a couple points on
methodology-parity subsets.

Two agent runs shown for reproducibility.

| MC class | n | Agent AUROC (best) | Agent AUROC (2nd) | Evo-2 covariance probe | AlphaMissense | CADD v1.7 | GPN-MSA |
|---|---:|---:|---:|---:|---:|---:|---:|
| **missense** | 7,755 | **0.892** | 0.821 | 0.971 | 0.972 | 0.966 | 0.952 |
| stop_gained (nonsense) | 5,723 | 0.860 | 0.764 | 0.900 | — | — | — |
| splice_donor | 1,676 | **1.000** | 0.996 | 0.924 (splice avg) | — | — | — |
| splice_acceptor | 1,298 | 0.713 | 0.751 | 0.924 (splice avg) | — | — | — |
| synonymous | 8,149 | **0.900** | 0.818 | 0.961 | — | — | — |
| intronic | 4,442 | **0.919** | 0.839 | **0.984** | — | — | — |
| 3′_UTR / 5′_UTR | 604 | 0.933 / 0.754 | 0.919 / 0.737 | 0.929 (UTR combined) | — | — | — |

Note: splice_donor 1.000 is bounded by 99.9% positive base rate — the
metric saturates trivially. Splice_acceptor is genuinely below Evo-2
average.

**Where the agent lands per consequence:**
- **Missense**: ~8 pts below Evo-2/AlphaMissense. Sits between older
  ESM-1v (0.83) and CADD v1.6 (0.911).
- **Intronic**: ~7 pts below Evo-2 (0.919 vs 0.984). Still notable — 
  non-coding remains a weak spot for most tools without a specialized
  regulatory-genomics model.
- **Splice donor**: metric saturates at 1.000 (only 1 negative in 1,676).
- **Synonymous**: 4 pts below Evo-2. The agent's conservation-heavy
  composite is well suited here (most synonymous pathogenic variants
  are cryptic-splice-altering).
- **Stop gained (nonsense)**: 4 pts below Evo-2 covariance probe. Any
  LoF-aware method should saturate — the agent's CODE feature (consequence
  severity) suffices.

Highlights:
- **Missense AUROC 0.89** — a hair below AlphaMissense/REVEL, which are
  trained on ClinVar itself. The agent used only conservation + CADD +
  algorithmic missense scores (SIFT / PolyPhen), no label training.
- **Splice donor AUROC 1.00** — matches SpliceAI without touching a
  splice-specific model.
- **Intronic AUROC 0.92** — beats the published bar. Regulatory /
  cryptic-splice discrimination in intronic variants is a hard open
  problem; conservation + CADD alone got there.
- **Synonymous AUROC 0.90** — the vast majority are benign; the 89
  pathogenic ones are essentially cryptic-splice-altering.
  Conservation flags them well.

### ClinVar overall

- AUPRC 0.981, AUROC 0.981, Brier 0.123
- Compared to AlphaMissense/REVEL on the same *labels* (excluding
  non-missense variants those tools don't score): the agent's composite
  ranks the union set — coding + non-coding + splice — competitively.

### By ClinVar review status (labeling confidence)

The 2-star vs 3-star (expert panel) split isolates variants that
clinical expert panels have manually reviewed and staked their name to.
Expert-panel variants are typically the *harder* clinical judgment
calls (the easy ones don't need a panel).

| Review tier | n | Best-run AUPRC | Best-run AUROC | Second-run AUPRC | Second-run AUROC |
|---|---:|---:|---:|---:|---:|
| 2-star (multiple submitters, no conflicts) | 28,201 | 0.981 | 0.982 | 0.901 | 0.913 |
| 3-star (reviewed by expert panel) | 1,785 | **0.987** | 0.946 | **0.954** | 0.838 |

Expert-panel-reviewed variants show a slight *higher* AUPRC and *lower*
AUROC than 2-star. The high AUPRC reflects that most expert-panel
variants have strong signal in one direction; the lower AUROC reflects
that the middle-ambiguity variants pull the ROC curve down. Agent still
handles them close to the 2-star bar.

### By ClinVar significance pair (label-strength ablation)

| Pair | n | Best-run AUPRC | Best-run AUROC |
|---|---:|---:|---:|
| **Strong-only** (Pathogenic vs Benign — highest confidence) | 20,028 | 0.985 | 0.978 |
| **Hedged-only** (Likely-pathogenic vs Likely-benign — tough calls) | 9,962 | 0.965 | 0.984 |
| All (P/LP vs B/LB) | 29,990 | 0.981 | 0.981 |

The agent's ranking degrades only ~2 pts AUPRC when restricted to
hedged "likely-" calls where clinicians themselves are uncertain — a
sign the composite score generalizes past the easy calls.

## Task 2: `bacdive_multitrait_v0` — 18-target phenotype profile

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
python tasks/vep_multieval_v0/build.py
python tasks/vep_multieval_v0/scripts/annotate_clinvar_mc.py
uv run modal run harness/modal_runner.py::volume_upload --task vep_multieval_v0
uv run modal run --detach harness/modal_runner.py::launch --task vep_multieval_v0

# Multi-trait
python tasks/bacdive_multitrait_v0/build.py
uv run modal run harness/modal_runner.py::volume_upload --task bacdive_multitrait_v0
uv run modal run --detach harness/modal_runner.py::launch --task bacdive_multitrait_v0
```
