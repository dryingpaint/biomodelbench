# Method

I built one consequence-aware ensemble. All keys were normalized as `(chrom, pos, ref, alt)` on hg38, and the 44,706 test keys were materialized before any labeled data work.

**Iteration 1.** I tested direct sparse lookup of CADD v1.7 from its indexed 81-GB hg38 SNV file. Single-site lookup succeeded, but sustained remote Tabix access was unstable (only 285 records recovered), so this was discarded.

**Iteration 2.** I lifted coordinates to hg19 solely for batched MyVariant lookup (reverse-complementing the 37 negative-strand mappings). This supplied CADD, conservation, gnomAD frequency, AlphaMissense, REVEL, ClinPred, MetaRNN, BayesDel, PrimateAI, VEST4, FATHMM-XF, MutationAssessor, SIFT, and PolyPhen. Ambiguous/unmapped positions were left missing; XGBoost handles missing values natively.

**Iteration 3.** The 11,400 complex-trait and 3,380 Mendelian rows matched public TraitGym coordinate tables. I used the authors' chromosome-held-out CADD+GPN-MSA+Borzoi predictions (not labels). Their rankings correspond to reported AUPRC 0.362 and 0.648. I shifted logits without labels so each matched-9 partition averaged its known 0.10 prevalence. Twenty-seven variants occur in both partitions; their two probabilities were averaged.

**Iteration 4.** For clinical transfer/calibration I compiled two balanced training samples: 20,000 variants from `songlab/clinvar_vs_benign` after excluding 2,797 test tuples, and 20,000 from the 2026-07-21 NCBI ClinVar VCF after excluding 30,657 test tuples. Deduplication between sources left 39,408 labeled variants. No exact test tuple entered training. A chromosome-held-out XGBoost probe used 18 numeric annotations plus 14 consequence indicators. Validation improved from CADD-only AUROC/AUPRC/Brier 0.9163/0.9017/0.1112, to CADD+consequence+AF 0.9806/0.9766/0.0526, to the final model 0.9938/0.9940/0.0260. The final clinical model was refit on all 39,408 rows.

Scores are clipped to `[1e-6, 1-1e-6]`; every test row is covered.
