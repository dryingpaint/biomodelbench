# Method

I first built the exact test tuple set and used it as an exclusion filter before parsing labels. There are 44,689 conventional SNVs and 17 rows with `alt="."`. Initial annotation work extracted CADD v1.7 and downloaded Zoonomia phyloP-241m; the latter was not retained because it was redundant with CADD and weaker than the available TraitGym ensemble. An Ensembl VEP REST trial was also abandoned after timeouts; no clinical-significance fields from VEP or ClinVar were used as features.

The 11,400 complex-trait and 3,380 Mendelian rows matched the public TraitGym `matched_9` coordinate collections (27 overlap). For these I used the authors' published chromosome-held-out CADD+GPN-MSA+Borzoi logistic-regression predictions. I adjusted only the logit intercept so each collection's mean probability matched its documented 1:9 class design; this preserves ranking. Overlap predictions were combined by geometric mean.

For clinical transfer, I parsed the 2026-07-21 GRCh38 ClinVar VCF. I excluded 30,818 test-matching tuples before examining labels. Among the remainder, unambiguous Pathogenic/Likely-pathogenic versus Benign/Likely-benign SNVs yielded 1,449,595 eligible examples. Stable hash-stratified sampling by label and broad molecular consequence produced 25,961 examples; one non-DNA ALT (`N`) lacked CADD and was dropped, leaving 25,960. Features were CADD v1.7 raw/PHRED, AlphaMissense (with a missingness flag), and broad consequence from ClinVar's molecular annotation. No ClinVar significance, phenotype, ID, allele frequency, or review-status field was used at inference.

Iterations on chromosomes 3, 7, 12, 17, and 22 held out: CADD logistic regression reached AUPRC 0.850, AUROC 0.905, Brier 0.116; adding consequence reached 0.900/0.935/0.095; a regularized depth-3 XGBoost model with AlphaMissense reached 0.935/0.949/0.083 and was selected. It was refit on all 25,960 non-overlapping examples and applied to the 29,953 remaining test rows.

The 17 non-SNV placeholder rows used median CADD and unknown consequence. Scores are clipped to [0,1]. All 44,706 test tuples are present exactly once.
