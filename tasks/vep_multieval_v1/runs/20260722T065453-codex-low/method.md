# Method

I first checked normalization and uniqueness: the file contains 44,706 unique hg38 SNVs (22 autosomes plus X; no indels or duplicate tuples). No labeled training set was compiled, and no test labels were used.

Iterations were: (1) MyVariant batch lookup, rejected because CADD/dbNSFP coverage was poor; (2) sparse remote-tabix CADD v1.7 retrieval, confirmed exact allele scoring but rejected for full use because request latency was high; (3) exact joins to TraitGym's public matched and all-candidate files, extracting only coordinates, published predictions, CADD, and GPN-MSA columns; (4) sparse extraction of EVEE ClinVar predictions, rejected for the final model because its supervised ClinVar probe could overlap test variants; and (5) final Ensembl VEP batch annotation with CADD v1.7, AlphaMissense, SpliceAI, SIFT, PolyPhen, and consequence. The VEP parser intentionally discarded colocated ClinVar significance and all other label fields.

For tuples in TraitGym matched sets, I used its released chromosome-held-out CADD + GPN-MSA + Borzoi logistic-ensemble prediction. The 27 tuples shared by complex and Mendelian sets were averaged. Because TraitGym fit logistic regression with balanced class weights while `matched_9` contains one positive per nine controls, I applied a prior-odds correction from 1:1 to 1:9; this preserves rankings.

All remaining rows received a consequence-aware clinical score. CADD PHRED was transformed by a fixed sigmoid centered at 15. Missense scores blend calibrated AlphaMissense (70%), CADD (20%), and available SIFT/PolyPhen (5% each). Core splice variants blend SpliceAI (65%) and CADD (35%); synonymous/intronic/splice-region variants take the stronger splice-aware signal. UTR variants use 80% CADD and 20% SpliceAI; other consequences use transformed CADD. Missing optional annotations are reweighted rather than imputed from labels. Scores are clipped to [0,1].

Validation selection used the published TraitGym chromosome-weighted AUPRCs supplied with the task (0.362 complex; 0.648 Mendelian); no local label-based validation was performed.
