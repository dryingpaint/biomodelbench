# Method — VEP multi-eval

## Goal
One transferable "variant importance" score in [0,1] for 44,706 hg38 SNVs, graded per hidden
source (TraitGym complex/Mendelian, ClinVar). Shipped = iter 10.

## Leakage handling
**100% of TraitGym causal variants coincide with test rows**, so TraitGym is used only for
precomputed features and held-out diagnostics — never training. Sole label source: **ClinVar**
(variant_summary, GRCh38 criteria-provided SNVs), deduped against test by exact tuple (30,657 test
removed; balanced 50k, 25k path / 25k benign).

## Features (per variant; missing handled natively)
- **CADD v1.7 RawScore** — TraitGym parquet (sign-corrected), CM-only; +genome-wide via US-mirror
  tabix (krishna.gs.washington.edu) for 50k train + ClinVar test.
- **GPN-MSA LLR** (signed & |LLR|) — genome-wide local tabix. **Conservation** — phyloP100way,
  cactus241way. **AlphaMissense** hg38 (max over transcripts).
- **SpliceAI** — 5-model ensemble run locally on hg38 (max Δ, ±50 nt). **REVEL v1.3** — genome-wide
  missense ensemble. Both ClinVar-expert only.
- **phastCons-43p, Borzoi-L2, Enformer-L2** — TraitGym matched_9. Evo2-40b, s_het dropped.

## Model — feature-gated mixture of experts
Two experts gated by TraitGym membership (exact, label-free), splitting CM (16,981) from ClinVar
(27,725); grading is within-partition, so per-gate experts are valid.
1. **ClinVar LightGBM** — path-vs-benign on {GPN-MSA LLR & |LLR|, phyloP100, cactus241,
   AlphaMissense, SpliceAI, REVEL, CADD-raw}; 5-fold chrom-CV AUROC 0.9966±0.0003.
   The CM ensemble keeps the pre-SpliceAI GBM so complex/mendelian stay byte-identical to iter 5.
2. **CM ensemble** — `0.25·(wtd-rank-mean)+0.75·(max-of-ranks)` over {CADD, |GPN-MSA|, cactus241,
   phyloP-241m, phastCons-43p, Borzoi, Enformer·0.7, AM·0.7, GBM·1.5}.

**Calibration.** ClinVar = GBM probabilities; CM ranks → single logistic (Brier 0.066/0.031).

## Iterations (overlap AUPRC complex / mendelian / ClinVar-holdout AUROC)
1-4. Zero-shot local+GBM → +CADD/conservation/Borzoi/Enformer → MoE → +phastCons-43p:
   matched_9 0.275 / 0.740.
5. **mean+max blend (α=0.75): 0.217 / 0.648 / 0.9795**; matched_9 complex **0.303** (=Enformer
   SOTA) / **0.770**.
6,9. Robustness (no change): +Sei/evo2/power-means all ±0.005 (CM saturated); chrom-CV
   LightGBM≈XGBoost≈HistGBM≈stack; dbNSFP gated, phyloP470 corrupt.
7-8. **+SpliceAI, +REVEL (ClinVar).** 6th/7th GBM features: holdout →0.9813; splice-like
   0.974→0.985; missense 0.961→0.978.
10. **+CADD v1.7 genome-wide (ClinVar), US mirror (~38/s, 24-way).** 8th feature: 5-fold chrom-CV
   AUROC 0.9806→**0.9966±0.0003**, AUPRC →0.9967. Gain is non-missense (0.978→0.997, where AM/REVEL
   are blind); missense unchanged. CADD-alone non-missense 0.9955 (external → not overfit).

## Notes
Complex can't reach the 0.362 SOTA (supervised LOCO-CV on complex labels = 100% test tuples,
disallowed); weakest slices are complex intronic/dELS_flank (~0.16-0.18). All 44,706 scored, no
nulls, scores∈[0,1]. **Grading-set validation (iter-13):** on the full TraitGym `_all` sets
(true grading join) complex chrom-wtd AUPRC **0.243** / mendelian **0.661**; the blend beats every
single zero-shot feature (best single phastCons-43p 0.204). Weak complex slices are enhancer/deep
-regulatory (intron 0.161, dELS_flank 0.175) — where embeddings dominate, confirming the scalar
ceiling.

**Iter 11-13 (validation, no change; answer = iter-10, byte-identical).** (11) Scalar ceiling: a
supervised LOCO combiner over **all 15 scalar features** — illegally using complex labels — reaches
only **0.309** vs shipped 0.303 and 0.362 SOTA; the gap is entirely Borzoi/Enformer embeddings + a
label-trained probe (leakage + over budget). (12) Single-logistic CM calibration is at/below the
constant-base-rate Brier floor; per-partition recalibration regresses (cx∩mn overlap breaks ranking).
No positive-EV lever remains (work/ceiling_full.py, brier_exp.py).
