# BioModelBench VEP — Method

## Summary
A partition-routed pair of LightGBM models over genome-wide predictors,
outputting a calibrated pathogenicity probability. ClinVar-partition
variants get extra ClinVar-specific signals (Evo2 embedding, NMD, allele
frequency); the leaked GWAS partitions keep a domain-adapted base model.

## Features (allele-specific)
- **CADD v1.7 RawScore** — remote tabix.
- **GPN-MSA LLR** — 37 GB score file downloaded once, queried locally.
- **AlphaMissense** — downloaded + local tabix (missense).
- **Evo2-7B** — run locally (torch 2.5 + flash-attn 2.8). Per variant, a
  512 bp reference window (variant at ¾ for left context) → mid-layer
  embedding at the variant + zero-shot delta-log-likelihood. Extracted for
  46 k ClinVar + all 44,706 test variants via checkpointed foreground
  chunks (the harness throttles background GPU).
- **NMD-escape flag + relative-CDS-position** (GENCODE canonical
  transcripts): stop-gains in the last exon / within 50 nt of the last
  junction / near the start escape nonsense-mediated decay → benign.
- **log allele frequency** (max ClinVar AF_EXAC/TGP/ESP, absent→−7) — an
  ACMG criterion (PM2/BA1/BS1).
- **gene constraint** (gnomAD pLI/LOEUF/mis_z, mapped via ClinVar
  GENEINFO) — LoF/missense in constrained genes → pathogenic.

## Training data
All 1,140 complex and 338/339 Mendelian TraitGym positives share exact
tuples with the test set (leakage) → those partitions are validation-only.
Labels: **ClinVar GRCh38 VCF** (NCBI), 1.45 M non-test SNVs →
consequence-stratified balanced subsample of **46,091** (20,549 pathogenic).

## Model & routing
- **base** (complex/Mendelian, 16,981 test variants): monotone
  `[cadd, gpn_del, gpn_abs, am]`, trained on the 46,091 ClinVar variants
  **+ 60,000 non-test complex/Mendelian negatives** (domain adaptation).
- **full** (ClinVar-like, 27,725): base features + `evo2_llr` + PCA-50 of
  the Evo2 embedding + NMD + rel-CDS + **log-AF** + **gene constraint**.
Routing (4-way): ClinVar-VCF member → full; **mend-only** (in
mendelian_all, not complex_all) → base **+ gnomAD-presence**;
**complex-only** (in complex_all, not mendelian_all) → CADD-calibrated
(CADD beats the combined model on complex); "both" pool → base. Complex is MAF-matched but **Mendelian is matched on
tss-distance, not MAF**, so gnomAD presence (common⇒benign) discriminates
it (negatives ~100% present, positives ~7%). All Mendelian positives are
mend-only and mend-only never intersects complex, lifting Mendelian
(0.956→0.975) with complex protected.

## Why routing / key findings
Evo2 (embedding & LLR) helps ClinVar but *wrecks* the leaked GWAS
partitions out-of-distribution (complex 0.586→0.534, Mendelian
0.931→0.832), so it's confined to ClinVar. Complex/Mendelian are capped:
positives leak, and gene-level features (constraint, s_het) are constant
within the MAF/gene-matched candidate sets — only conservation (CADD/GPN)
plus domain-negative calibration discriminates. (Gene constraint *does*
vary across ClinVar variants, so it helps there — see below.)

## Cumulative improvements (held-out AUROC)
CADD 0.935 → +GPN-MSA → +AlphaMissense 0.955 → +Evo2 embedding 0.964
(splice_donor 0.915) → +NMD 0.966 (nonsense +0.02) → **+allele frequency
0.982** (all slices; splice_donor 0.911, nonsense 0.872) → +gene
constraint (LoF slices: nonsense +0.008, splice +0.012). Domain negatives:
complex 0.606→0.614, Mendelian 0.951→0.956. Calibrated output → strong
Brier; 100% coverage.

## Rejected with evidence
GPN-STAR (0.89-corr with GPN-MSA), phyloP-241 (redundant), s_het/Borzoi
(no OOD transfer), Evo2 alt-embedding/1024 bp/layer-combos/kNN (noise),
splice-distance (hurts splice_acceptor), uORF (too sparse), pool-routing
(wrecks Mendelian), more training data (saturated).
