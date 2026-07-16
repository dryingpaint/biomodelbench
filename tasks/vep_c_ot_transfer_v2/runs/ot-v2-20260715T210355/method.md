# Method — VEP-C (OT transfer)

## Framing
Train labels separate OT-Genetics fine-mapped causal SNPs (PIP≥0.9) from
near-zero-PIP variants; 62% of negatives sit within 10 kb of a positive, so
the training signal is essentially *causal vs. LD-neighbour at the same locus*
— a hard, fine-mapping-style discrimination. The test set (TraitGym
`complex_traits_matched_9`) instead contrasts causal variants with MAF/LD/TSS-
matched controls. I therefore deliberately built features that are **functional
and not part of the matching** (conservation, regulatory-element context,
allele-specific regulatory effect) and avoided matched confounders (MAF, raw
TSS distance).

## Features (per variant, hg38)
**Conservation** — six UCSC bigWigs read locally after bulk download:
phyloP & phastCons at 100-way (vertebrate), 470-way (mammalian) and 17-way
(primate). Per track: point value, and max/min/mean over ±25 bp plus mean over
±5 bp (captures nearby constrained elements).
**Regulatory** — ENCODE cell-type-agnostic cCRE bigBed: overlap flag, element
score, type one-hots (PLS/pELS/dELS/CTCF/K4m3/DNase) and log-distance to the
nearest cCRE overall and to the nearest PLS / ELS / CTCF element.
**Sequence context** — GC fraction (±50 bp), CpG-site flag, transition/
transversion (from the hg38 FASTA).
**Allele-specific (Enformer)** — ref and alt 196,608-bp windows scored with
Enformer (5,313 human tracks); from the centre bin I take the L1/L2/max of the
alt−ref delta, a ±4-bin (±512 bp) windowed SAD, and reference activity
(max/mean). Computed for all 11,400 test variants and a balanced 10,000-variant
train subsample (Enformer is compute-bound at ~0.14 s/seq, unbatchable).

## Model
LightGBM (depth 5, 800 trees, lr 0.02, strong L1/L2), validated with
**chromosome-grouped 5-fold CV inside train.parquet only**.
- Model A (conservation + regulatory + context, all 72k train): OOF
  AUROC {A_AUROC} / AUPRC {A_AUPRC}.
- The Enformer axis is folded in by stacking (Model A's out-of-fold prediction
  + Enformer deltas) and by rank-blending; the variant that beats A by >0.002
  AUROC on the held-out subsample is chosen ({WINNER}).
Final probabilities are prior-shifted from the 58% train base rate to the 10%
test base rate (monotonic; preserves ranking, improves calibration).

## Tried / dropped
- Remote bigWig reads (pyBigWig lacks curl; pybigtools works but ~0.4 s/point) —
  replaced by bulk download + local reads (fast).
- Shorter Enformer windows for speed — blocked (model fixed at 1536 bins).
- MAF / raw TSS distance — deliberately excluded (matched in the test set).

Validation numbers: {SUMMARY}
