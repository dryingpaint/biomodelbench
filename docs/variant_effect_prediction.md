# BioModelBench — Variant-Effect Prediction

**Status:** draft v0
**Tier:** T0 (zero-shot FM scoring) → T2 (post-training / de novo model)
**Modality:** DNA + protein sequence, with optional structure/conservation side-inputs
**Owner:** [GAP — assign]

Any value below marked `[GAP]` must be filled from a real source before the
task ships. Nothing invented.

> **What's currently shipped:** VEP-C (complex-trait causal SNP prediction)
> in the "OT transfer, open-ended features, blind eval" configuration
> described in §2 → §7. The agent gets only variant IDs + training labels;
> feature extraction is on the agent; test labels never enter the container.
> Task packet: `evals/benchmarks/biomodelbench-vep/tasks/vep_c_ot_transfer_v2/`.
> VEP-M (missense) and VEP-N (noncoding regulatory) are described below but
> not yet shipped as task packets.

---

## 1. Motivation

Variant-effect prediction (VEP) is the most clinically actionable genomics
task: given a substitution, insertion, deletion, or structural change in a
genome, predict its functional and/or phenotypic consequence. It sits under
every ACMG classification, every fine-mapping call, and every rare-disease
diagnostic. Two properties make it a good BioModelBench task:

1. **Multi-tier compute headroom.** Missense pathogenicity can be zero-shot
   scored by protein language models (T0); noncoding and complex-trait causal
   variants remain open, and are the natural target for pretraining or
   post-training (T1–T2).
2. **Sharp leakage risk.** The reference genome, ClinVar, and much of
   ProteinGym are in the pretraining mix of every current genomic/protein FM,
   and ClinVar itself is partly circular because ACMG classification pipelines
   consume in-silico predictors as evidence. The task is only informative if
   the split is designed to defeat both.

## 2. Core question

Given a variant specification (locus, ref, alt, transcript/protein context),
predict its effect on:

- **VEP-M (missense clinical).** Pathogenic vs. benign for coding missense
  variants, plus continuous functional impact.
- **VEP-N (noncoding regulatory).** Effect direction and magnitude on
  expression / chromatin / splicing tracks, and pathogenicity for regulatory
  variants where labels exist.
- **VEP-C (complex-trait causal).** Given a fine-mapped credible set, identify
  the causal variant and predict effect size.

The three sub-tasks are scored independently. An agent may submit predictions
for any subset; the leaderboard reports per-sub-task and a composite.

## 3. Existing SOTA and baselines the agent must beat

Baseline predictions are pre-computed and shipped with the task so the agent
does not spend compute regenerating them.

| Sub-task | Baseline family | Specific baselines |
|---|---|---|
| VEP-M | classic in-silico | CADD (Rentzsch et al., NAR 2019), REVEL (Ioannidis et al., AJHG 2016), PolyPhen-2, SIFT |
| VEP-M | protein LM zero-shot | ESM-1v / ESM-2 (Lin et al., Science 2023), ESM3 [GAP — confirm inclusion] |
| VEP-M | per-family generative | EVE (Frazer et al., Nature 2021) |
| VEP-M | supervised transformer | AlphaMissense (Cheng et al., Science 2023) |
| VEP-N | regulatory CNN | Enformer (Avsec et al., Nat Methods 2021), Borzoi (Linder et al., 2023) |
| VEP-N | genomic LM | Nucleotide Transformer (Dalla-Torre et al., Nat Methods 2024), Caduceus (Schiff et al., ICML 2024), Evo 2 (Nguyen et al., 2024) |
| VEP-N | ensemble | CADD, LINSIGHT [GAP — confirm license] |
| VEP-C | linear | LDpred2, SBayesR, PGS-Catalog frozen scores |
| VEP-C | genomic LM probes | Enformer/Borzoi/AlphaGenome track deltas as features on TraitGym |
| VEP-C | post-trained | GLM-Missense / EVEE (per the source proposal) — [GAP — confirm published bar to beat, or drop] |

The agent is not privileged toward any of these; a hybrid or a well-tuned
mechanistic model may win.

## 4. Committed datasets (v0)

All splits are frozen and shipped as static parquet + fasta bundles.

### 4.1 VEP-M — missense

- **Substrate:** ProteinGym DMS assays + ProteinGym clinical substitution set
  (Notin et al., NeurIPS 2023).
- **Held-out clinical:** ClinVar (Landrum et al., NAR) restricted to variants
  first submitted **after** the pretraining cutoff of every foundation model
  in scope. Cutoff table is a versioned artifact in the task bundle.
  - Rationale (from proposal): ClinVar is partly circular because ACMG
    classifications feed in-silico scores back into later submissions;
    temporal split blocks the loop.
- **Additional temporal test:** DMS assays published after [GAP — set cutoff
  date once FM roster is fixed], curated from MaveDB.
- **Split axes:** (a) gene-holdout, (b) family-holdout (Pfam), (c) temporal.

### 4.2 VEP-N — noncoding regulatory

- **Substrate:**
  - MPRA/STARR-seq: [GAP — select from published sets; candidates include
    Sharpr-MPRA (Kalita et al.), MPRA saturation-mutagenesis from Kircher et
    al. 2019; confirm licenses]
  - eQTL fine-mapped credible sets from GTEx v8 (GTEx Consortium, Science 2020).
  - Splice-affecting variants: SpliceAI validation set (Jaganathan et al.,
    Cell 2019) or vexseq [GAP — pick one].
- **Held-out:** chromosome-holdout **and** cell-type-holdout, with a
  divergence-stratified report (see §6).

### 4.3 VEP-C — complex-trait causal

- **Substrate:** TraitGym (Chen et al., 2024) as the headline benchmark; it
  ships fine-mapped credible sets across UK Biobank traits with matched
  controls.
- **Cross-ancestry stress test:** [GAP — align with the Complex-Trait
  Prediction task's cross-ancestry protocol (AFR, EAS, admixed) once that
  task's cohorts are locked].

## 5. Committed metrics

Reported per-sub-task, per-split, and per-divergence-stratum.

- **VEP-M:** AUROC and AUPRC on pathogenic/benign; Spearman ρ vs. DMS score
  on the continuous side; MCC at the ACMG-relevant operating point.
- **VEP-N:** AUPRC for regulatory-vs-control classification on credible sets;
  Pearson r vs. measured MPRA log-fold-change; effect-direction agreement.
- **VEP-C:** precision@1 and AUPRC on causal-vs-tag SNP within credible sets
  (TraitGym-native metric); calibration of predicted effect size against
  fine-mapped posterior effect.
- **Composite:** rank-aggregate across the three sub-tasks; ties broken by
  the hardest split (family-holdout for M, chrom+cell-type for N, cross-
  ancestry for C).

## 6. Splits, leakage controls, and audit

- **Temporal split** is mandatory for every VEP-M submission. Baseline scores
  are computed on both the pre- and post-cutoff sets; the leaderboard uses
  post-cutoff only.
- **Family/gene/chromosome holdout** applied on top of the temporal split.
- **Divergence-stratified reporting.** Every eval reports performance as a
  function of similarity between test variant context and the nearest
  training/pretraining context (measured by [GAP — pick metric: for protein,
  MMseqs2 sequence identity to nearest train sequence; for DNA, k-mer
  Jaccard over the surrounding window]). This is the same shape as the
  metagenomic-mining task's divergence stratification and prevents the
  headline from being carried by near-duplicates.
- **Leakage audit (from BioModelBench top-level rules):**
  1. Trace inspection: agent may only fetch data from the network allowlist.
  2. Data-integrity check: submitted predictions are recomputed on a random
     10% shuffled subset with the agent's own code; if scores diverge beyond
     noise, run is invalidated.
  3. Retrieval blocking: ClinVar, PGS Catalog, GWAS Catalog, and MaveDB
     endpoints are on the allowlist for **training-time** retrieval only if
     the response is filtered to the pre-cutoff snapshot, served from a
     frozen mirror. Live queries are blocked.

## 7. Environment provided to the agent

Following BioModelBench conventions:

- **Network allowlist:** NCBI, Ensembl, UCSC, UniProt, EBI, PyPI, conda,
  CRAN, Bioconductor, plus the frozen mirrors of ClinVar, MaveDB, GTEx,
  TraitGym, ProteinGym, PGS Catalog. Everything else blocked.
- **Model inference endpoints:** ESM-2 embeddings + zero-shot likelihoods,
  Evo 2 likelihoods, AlphaGenome track deltas, Enformer/Borzoi track deltas.
  Endpoints are rate-limited; per-run quota is a task parameter [GAP — set
  after cost estimate].
- **Frozen datasets:** train/dev/test parquet + fasta bundles for each
  sub-task, baseline prediction files, split definitions, cutoff table.
- **Frozen interfaces:** VEP annotation (Ensembl VEP, frozen release),
  conservation scores (phyloP, phastCons at fixed UCSC release), Pfam family
  assignments, ClinVar-frozen-mirror API.
- **Compute budget:** [GAP — set per tier; T1 target: single-GPU-day,
  T2 target: multi-GPU-week; must match sibling task budgets].

## 8. Deliverables the agent submits

A single directory with:

- `predictions_vep_m.parquet` — one row per test variant with
  `pathogenic_prob` and, where applicable, `functional_score`.
- `predictions_vep_n.parquet` — one row per test variant with per-track
  `effect_size` and `direction`.
- `predictions_vep_c.parquet` — one row per credible-set × candidate with
  `causal_prob` and `effect_size`.
- `method.md` — brief method description (used by the trace auditor, not by
  the grader).
- `training_manifest.json` — every dataset touched during training, for the
  leakage audit.

Missing sub-tasks are allowed; missing rows within a sub-task are scored as
the class-prior baseline for that row.

## 9. Compute tier

- **T0** — zero-shot ESM-2 / Evo 2 / Enformer scoring, ensemble over
  provided baselines.
- **T1** — LoRA / linear probe on frozen embeddings; per-family EVE-style
  VAE. The proposal points at GLM-Missense / EVEE as the reference for this
  tier — treat as illustrative, not a required baseline, until we've confirmed
  a published bar.
- **T2** — pretraining or full-model design.

The leaderboard splits by declared tier; T0 submissions are not compared
head-to-head against T2.

## 10. Open questions before v1

1. **Noncoding label source.** Pick the specific MPRA sets and confirm
   licensing. See §4.2.
2. **FM pretraining cutoff table.** Enumerate the FMs in scope (ESM-2, Evo 2,
   Enformer, Borzoi, Nucleotide Transformer, Caduceus, AlphaGenome,
   AlphaMissense) with their training-data cutoffs so the temporal split is
   defensible. Some cutoffs are not publicly disclosed → mark [GAP].
3. **GLM-Missense / EVEE citation.** From the source proposal. Confirm these
   are published (or preprinted) and have public numbers to beat, otherwise
   drop from the baseline table.
4. **Cross-ancestry cohorts for VEP-C.** Align with the complex-trait task's
   All of Us / FinnGen / gnomAD ancestry protocol before locking splits.
5. **Divergence metric.** Fix the exact similarity metric per sub-task.
6. **Compute quotas.** Set per-tier GPU/wall-clock caps consistent with the
   rest of BioModelBench.

## 11. Sources cited above (verbatim, no invented values)

- Landrum et al., ClinVar — NAR (database ref).
- Notin et al., ProteinGym — NeurIPS 2023.
- Chen et al., TraitGym — 2024 (as cited in source proposal).
- Frazer et al., EVE — Nature 2021.
- Cheng et al., AlphaMissense — Science 2023.
- Lin et al., ESM-2 — Science 2023.
- Avsec et al., Enformer — Nature Methods 2021.
- Linder et al., Borzoi — 2023.
- Dalla-Torre et al., Nucleotide Transformer — Nature Methods 2024.
- Schiff et al., Caduceus — ICML 2024.
- Nguyen et al., Evo 2 — 2024.
- Rentzsch et al., CADD — NAR 2019.
- Ioannidis et al., REVEL — AJHG 2016.
- Jaganathan et al., SpliceAI — Cell 2019.
- Kircher et al. 2019 (MPRA saturation mutagenesis) — [GAP — confirm exact
  citation before ship].
- GTEx Consortium — Science 2020.
- Karczewski et al., gnomAD — Nature 2020.

Everything not on this list, or marked `[GAP]`, must be filled from a real
source before v1.
