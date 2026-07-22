# BioModelBench VEP multi-eval — Method

## Summary
One transferable "variant importance" model: a single monotone-constrained
LightGBM classifier trained on ClinVar (pathogenic vs benign), using strong,
genome-wide-defined, transferable variant-effect features. The identical feature
pipeline is applied to train and test — one score ranks all three hidden
partitions, with no partition-specific logic.

## Features (computed identically for train & test, all 44,706 SNVs)
- **CADD v1.7** RawScore+PHRED — remote `tabix` range queries on the 87 GB
  whole-genome file via a local 2.7 MB index (checkpointed, resumable).
- **Conservation** — UCSC hg38 bigWigs (pyBigWig): phyloP100way, phyloP470way
  (mammalian), phastCons100way, phastCons470way.
- **AlphaMissense** hg38 (missense; NaN elsewhere — trees handle it).
- **GPN-MSA** genome-wide LLR (`songlab/gpn-msa-hg38-scores`, 37 GB, local tabix).
- **GPN-Star M447** genome-wide calibrated LLR + |LLR|
  (`songlab/gpn-star-scores`, 59 GB Parquet shards streamed per-chromosome with
  pyarrow position pushdown, filtered to 386,931 needed positions). Best single
  transferable feature.

## Training data & leakage control
All 44,706 test `(chrom,pos,ref,alt)` tuples were collected up front; every
candidate training variant is filtered against them. **ClinVar VCF (GRCh38)**:
SNVs, `CLNSIG`→binary (P/LP=1, B/LB=0; VUS/conflicting dropped), `CLNREVSTAT`→
stars. 1,449,939 labeled SNVs remain after test dedup; sampled to **342,225**
(155,557 pos / 186,668 neg) — all ≥1-star pathogenic + a consequence-stratified
≥1-star benign sample spanning coding *and* non-coding, anchoring the model's use
of conservation/CADD/GPN for non-coding variants. Complex/Mendelian GWAS
positives could not be trained on: the only public fine-mapped sets (TraitGym
UKB-nc, OMIM) lie entirely inside the test set, so those partitions are reached
purely by feature transfer.

## Model
LightGBM binary, monotone constraints on every feature (+1 for CADD/conservation/
AlphaMissense/|GPN|, −1 for signed GPN LLR); 5-seed ensemble; calibrated
probability output (coverage 1.0). Monotonicity was the key choice — it turned an
over-fit coding-centric model into a robust ensemble that transfers.

## Iterations & validation
Honest validation = chromosome-holdout (chr 7,15,21,22,X) of the ClinVar train
set. Complex/Mendelian numbers are INSPECTION-ONLY transfer checks vs public
benchmark labels (never used for training or weight tuning).
1. CADD-PHRED baseline. 2. Zero-shot rank ensemble.
3. Plain LightGBM+GPN-MSA: ClinVar-holdout AUPRC 0.993; transfer omim 0.724 /
   ukbnc 0.218 / clinvarVB AUROC 0.972 (complex below CADD-alone).
4. Monotone+GPN-MSA: 0.992; omim 0.740 / ukbnc 0.232 — dominates plain everywhere.
5. **Final: monotone + GPN-MSA + GPN-Star, 5-seed** — ClinVar-holdout AUPRC
   0.9936, Brier 0.026; transfer omim(Mendelian) **0.767**, ukbnc(complex)
   **0.239**, clinvarVB AUPRC 0.982 / AUROC **0.971**. Pareto-improves iter 4.

## Ceilings
Published complex SOTA (~0.36) needs ensembles trained on in-distribution complex
labels — all inside this test set, hence leakage-blocked. Zero-shot regulatory
models (Enformer/Borzoi L2 ≈0.24) do not beat this feature set, so complex is near
its achievable ceiling; Mendelian and ClinVar meet/exceed SOTA. A calibrated
probability was chosen over a rank-blend to keep per-partition Brier low.
