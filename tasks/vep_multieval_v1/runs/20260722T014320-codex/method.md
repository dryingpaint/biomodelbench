# Method

I normalized chromosome strings and built a set of all 44,706 exact hg38 `(chrom,pos,ref,alt)` test tuples before inspecting labeled data. There were 44,689 allele-defined SNVs and 17 missing-alt (`.`) sentinels, so no LiftOver or indel normalization was needed; sentinels received the maximum position-level substitution effect.

Annotations were CADD v1.7 raw/PHRED and GPN-MSA allele scores (remote tabix lookup), AlphaMissense v2 (maximum score across matching transcripts), and released label-free AlphaGenome/Borzoi/CADD/GPN-MSA TraitGym prediction vectors. Ensembl VEP supplied consequence and population-frequency annotations; clinical-significance fields returned by VEP were explicitly discarded.

The only labeled training source was `songlab/clinvar` (40,976 rows). Exact filtering removed 2,037 test tuples, leaving 38,939 training variants. Public UKBB complex-trait (11,400 rows), OMIM Mendelian (3,380), and duplicate Bolinas splits were audited: every labeled row matched the test, so all their labels were excluded and none became training data.

Iterations were: (1) a standardized logistic probe using signed/absolute CADD and GPN-MSA plus AlphaMissense and missingness; (2) a histogram gradient-boosted probe on the same inputs; and (3) a logistic probe adding released phyloP/phastCons/ESM features where available. On a chromosome holdout (12,582 rows), AUPRC/AUROC/Brier were respectively 0.9873/0.9848/0.0449, 0.9874/0.9852/0.0447, and 0.9881/0.9857/0.0436. I retained logistic probes for transfer and calibration, refitting on all allowed rows. A small log-odds adjustment was applied to canonical loss-of-function consequences; common gnomAD alleles were conservatively capped.

For regulatory TraitGym variants, I averaged within-source percentile ranks of CADD, absolute GPN-MSA, Borzoi, and AlphaGenome effect magnitudes. The rank was calibrated to the matched-control design (separately for complex and Mendelian tasks). All other rows used the clinical probe; rows with richer released conservation features used iteration 3. Scores were clipped to `[0,1]` and emitted in original test order.
