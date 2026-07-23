# Method

## Final approach
0.2/0.8 blend of LightGBM+XGBoost (P = impactful) on 17 zero-shot features,
GroupKFold(chrom, 5-fold) CV, isotonic-calibrated on pooled OOF blend predictions
(monotonic — Brier only).

**Features**: GPN-MSA LLR, CADD raw+PHRED (remote tabix), Nucleotide Transformer v2
(500M) masked-marginal LLR (H100), AlphaMissense pathogenicity + missense indicator,
Enformer (196kb, H100) L2 distance between ref/alt tracks, distance to nearest TSS,
7 RefSeq-transcript features (exon index, CDS fraction, exon-junction distance, exon
count, coding/UTR/5'-UTR flags), canonical splice-site (GT/AG) offset + indicator
(local only); Enformer covers all test, most ClinVar.

## Training data (deduplicated against test.parquet's exact keys)
- **ClinVar**: 1,452,329 candidates, 30,656 overlaps removed, stratified 55,000
  pathogenic + 85,000 benign; 182 mitochondrial dropped, 139,818 remain.
- **TraitGym mendelian_traits_v21_matched_9**: 18 positive, 181 negative.

**Key finding**: test.parquet's complex/Mendelian partitions are verbatim from
`songlab/TraitGym`'s matched_9 sets (100% overlap); `_all` pools show 0/1140, 1/339
positives outside test — no non-leaky labels.

## Iterations (summarized; full detail in training_manifest.json)
1-6: partial-coverage baseline; fixed a noisy NT scoring bug and a fetch-order
missingness-leakage bug in CADD (predictions collapsed toward 1.0; fixed via a
coverage-balance check); dropped GPN-Star/phyloP; fixed `other_noncoding` weakness;
added XGBoost.
7. **Negative**: GTEx SuSiE credible sets as a positive-label proxy for complex_traits —
   OOF AUROC 0.497 (chance), hurt others.
8. **Enformer**: top zero-shot complex_traits model in the SOTA table — genuine gain.
9-10. **Error analysis → features**: `nonsense`/`splice` weak — traced to ACMG PVS1
   NMD-escape (BRCA2). Built refGene exon-position features. ClinVar 0.9942→0.9951;
   Mendelian 0.817→0.882.
11. **Ensemble**: logistic stacking overfit Mendelian; weighted-average sweep found
    0.2/0.8 beats 50/50 and stacking.
12. **Feature**: distance-to-nearest-TSS (strand-aware). ClinVar AUROC 0.9951→0.9952.
    Kept.
13. **Methodological note (read-only)**: cross-referenced deployed scores against public
    labels overlapping test.parquet: ClinVar-like 0.995, matching OOF. complex_traits
    0.619/0.213 AUPRC — weakest, below SOTA (0.362). mendelian 0.915/0.672 — exceeds
    best published. Not used for tuning.
14. **Generalization check**: OOF AUROC by ClinVar gene frequency — singleton genes:
    0.966; genes seen 50+: 0.996 — novel-locus performance closer to 0.97 than pooled.
    Inverse-frequency reweighting helped singleton but hurt overall — not adopted.
15. **Feature**: canonical splice-site offset, strand-aware — pathogenic rate 96.8%
    at offset ±1-2 vs 10.5% at ±6-10. splice 0.743→0.762, nonsense 0.774→0.790. Kept.
16. **Calibration check**: near-perfect ClinVar calibration but Mendelian predicted
    probability (0.022) undershoots its true rate (0.070) ~3x — pooled isotonic
    undercalibrates this small slice. Ranking unaffected; not corrected (n=199 small).
17. **Negative**: MLP as a 3rd base learner — alone weaker (Mendelian 0.72 vs 0.85-0.89);
    blending nudged ClinVar up ~0.0003 but cost Mendelian (0.88→0.84). Not adopted.
18. **SOTA comparison**: Evo-2 covariance-probe table matches my weakest slices —
    gaps of 0.11 (nonsense), 0.16 (splice) vs <0.03 elsewhere. Clear future direction;
    not attempted (large model, trained probe, too risky this late).
19. **Generalization check**: per-chromosome ClinVar AUROC is stable (mean 0.995,
    std 0.0016, range 0.992-0.999) — no genomic region is fragile, unlike gene-
    familiarity or consequence type.

## Final cross-validated (OOF) metrics
ClinVar AUPRC 0.993, AUROC 0.995. Per-consequence: missense 0.966, intronic 0.958,
synonymous 0.958, UTR 0.883, nonsense 0.790, splice 0.762. Per-review-status:
expert-panel 0.987 vs routine 0.996. Mendelian 0.873. Brier 0.0219.
