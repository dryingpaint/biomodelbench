# Leakage audit — TraitGym Mendelian top runs (vep_multieval)

Audit performed 2026-07-23 across the 9 graded runs on the `vep_multieval`
task. Runs sorted by TraitGym Mendelian AUPRC (top-4 shown here; all 9
were spot-checked).

| Rank | Run | Agent | Mendelian AUPRC | Complex AUPRC | ClinVar AUPRC |
|---:|---|---|---:|---:|---:|
| 1 | `20260722T211109-claude-oauth-v4` | claude Max, OAuth | **0.7701** | 0.239 | 0.994 |
| 2 | `20260722T074538-claude-oauth`   | claude Max, OAuth | 0.7539 | 0.282 | 0.997 |
| 3 | `20260722T065453-codex-low`      | codex, reasoning=low | 0.7291 | 0.348 | 0.992 |
| 3 | `20260722T205103-codex-high-v2`  | codex, reasoning=high | 0.7291 | 0.348 | 0.981 |

Reference SOTA on TraitGym Mendelian:
`CADD trained LR alone = 0.875` (Benegas et al. 2025 leaderboard, chromosome-weighted AUPRC).

## Per-run leakage findings

### 1. `20260722T211109-claude-oauth-v4` — Mendelian AUPRC 0.7701

**Leakage discipline: CLEAN.** From `method.md`:

> All 44,706 test `(chrom,pos,ref,alt)` tuples were collected up front; every candidate training variant is filtered against them. **ClinVar VCF (GRCh38)**: SNVs, `CLNSIG`→binary (P/LP=1, B/LB=0; VUS/conflicting dropped), `CLNREVSTAT`→ stars. 1,449,939 labeled SNVs remain after test dedup; sampled to 342,225 (155,557 pos / 186,668 neg) — all ≥1-star pathogenic + a consequence-stratified ≥1-star benign sample.
>
> Complex/Mendelian GWAS positives could not be trained on: the only public fine-mapped sets (TraitGym UKB-nc, OMIM) lie entirely inside the test set, so those partitions are reached purely by feature transfer.

- **Explicit test-tuple exclusion**: 1.45M ClinVar SNVs kept after dedup against 44,706 test tuples.
- **TraitGym labels NEVER touched** — the agent recognised the 100% test overlap and used TraitGym only as a coordinate registry, not a label source.
- Features (CADD, phyloP100/470, phastCons100/470, AlphaMissense, GPN-MSA LLR, GPN-Star M447) are all model-inference outputs at test coordinates — those are legitimate features, not labels.
- Model: single monotone-constrained LightGBM (5-seed ensemble), trained on ClinVar labels only, applied to all 3 partitions via feature transfer.
- Missing `training_manifest.json`, but `method.md` is thorough and consistent with the observed behavior.

**Verdict: no test-label leakage.**

### 2. `20260722T074538-claude-oauth` — Mendelian AUPRC 0.7539

**Leakage discipline: CLEAN.** From `method.md`:

> **100% of TraitGym causal variants coincide with test rows**, so TraitGym is used only for precomputed features and held-out diagnostics — never training. Sole label source: **ClinVar** (variant_summary, GRCh38 criteria-provided SNVs), deduped against test by exact tuple (30,657 test removed; balanced 50k, 25k path / 25k benign).

- Explicit test-tuple dedup: 30,657 ClinVar rows removed for tuple collision → balanced 50k train.
- TraitGym membership used ONLY as a feature-gate signal (label-free) — the ClinVar-trained model receives features from any TraitGym precomputed source (Borzoi_L2, Enformer_L2, phyloP-241m, GPN-MSA_absLLR, etc.), all of which are model outputs at the coordinates.
- Feature-gated MoE architecture: ClinVar LightGBM branch for clinical variants; rank-ensemble branch for regulatory variants.
- `training_manifest.json` present and describes the leakage policy in prose; every source has a `role` field distinguishing "feature" from "label" use.

**Verdict: no test-label leakage.** Explicit + auditable.

### 3. `20260722T065453-codex-low` — Mendelian AUPRC 0.7291

**Leakage discipline: CLEAN (zero-shot).** From `method.md`:

> No labeled training set was compiled, and no test labels were used.
>
> For tuples in TraitGym matched sets, I used its released chromosome-held-out CADD + GPN-MSA + Borzoi logistic-ensemble prediction. Because TraitGym fit logistic regression with balanced class weights while `matched_9` contains one positive per nine controls, I applied a prior-odds correction from 1:1 to 1:9; this preserves rankings.

- **No labels touched at all** — pure feature-inference approach.
- TraitGym's *released* chromosome-held-out predictions are model outputs — legitimate features, not labels.
- Ensembl VEP parser "intentionally discarded colocated ClinVar significance and all other label fields."
- The 0.729 Mendelian score is achieved entirely by consuming TraitGym's own held-out CADD+GPN-MSA+Borzoi predictions and applying a base-rate correction.

**Verdict: no test-label leakage.** Zero-shot design; no ability to leak by construction.

### 4. `20260722T205103-codex-high-v2` — Mendelian AUPRC 0.7291

**Leakage discipline: CLEAN.** From `method.md`:

> I built the exact test-tuple set before accessing any training label...
>
> For the 11,400 complex-trait and 3,380 Mendelian TraitGym matches, I used the released chromosome-held-out CADD+GPN-MSA+Borzoi logistic predictions. Because those models used balanced class weights, I analytically corrected their odds to the benchmark's 1:9 prevalence...I never read TraitGym labels or PIP.
>
> Training used HuggingFaceBio ClinVar-VEP. I removed exact test tuples before exposing labels: coding 39,473 → 37,442 (2,031 removed); noncoding 15,258 → 14,112 (1,146 removed).

- Exact test-tuple set materialised before touching any label source.
- TraitGym: only released predictions (features), never labels/PIP.
- ClinVar: coding + noncoding partitions deduped; 3,177 total test-tuple leaks removed.
- EVEE ClinVar predictions: "column-projected from Zenodo without reading significance/label fields."
- `training_manifest.json` present, explicit per-source `labels_read` boolean.

**Verdict: no test-label leakage.**

## Summary

**All top-4 Mendelian runs are clean.** Common patterns:

1. Every run explicitly builds the `(chrom, pos, ref, alt)` test tuple set before touching a label source.
2. TraitGym's causal positives are 100% test — every agent that engaged with TraitGym did so as a feature source (via released model predictions) or as a coordinate registry, never as a label source.
3. ClinVar is the actual training label source in all label-training runs. Between 1,146 and 30,657 exact test-tuple leaks were removed depending on how each agent pulled ClinVar (the range reflects how much of ClinVar overlaps our 30k test subsample).
4. All 4 top runs explicitly declare their leakage policy in `method.md` and (where present) `training_manifest.json`.

**The 0.77 Mendelian AUPRC achievement (claude-oauth-v4) is legitimate.** It falls short of the published SOTA (CADD trained LR at 0.875) but that's because CADD's supervised training set for TraitGym could not be replicated by an agent constrained to avoid test-tuple leakage (TraitGym labels ARE test labels — 100% overlap). The agent's approach — train a probe on ClinVar's label distribution, apply to Mendelian via feature transfer — is the correct constrained-setting response.

## Plot

See `RESULTS_vep_agent_vs_sota.png`: 5-panel bar chart, per-partition, showing all 9 agent runs' AUPRC/AUROC alongside published SOTA reference lines and the zero-shot cluster.
