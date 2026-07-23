# BioModelBench VEP multi-eval v1

I used a source-adaptive importance score without reading any shipped labels. All joins used exact hg38 `(chrom,pos,ref,alt)` tuples.

For clinical/general scoring I remotely queried CADD v1.7 RawScore and PHRED for every true substitution and downloaded AlphaMissense v2. AlphaMissense covered 7,693 test variants. Seventeen `ALT="."` no-sequence-alteration records have no meaningful alternate allele and received the score floor.

I downloaded the 2026-07-21 ClinVar GRCh38 VCF and retained only unambiguous P/LP versus B/LB SNVs. Before fitting, I removed every exact test tuple: 1,480,111 eligible allele records, 30,656 exclusions, 1,449,455 retained unique/consistent variants. From these I deterministically sampled 5,000 per class (10,000 total; 6,932 AlphaMissense-covered). Chromosomes divisible by five were held out. Iterations were: AlphaMissense-only missense calibration (AUROC 0.9680); CADD logistic (AUROC/AUPRC/Brier 0.9602/0.9546/0.0825); CADD+AlphaMissense logistic (0.9763/0.9744/0.0549); and nonlinear histogram boosting (0.9791/0.9794/0.0552). I refit the final nonlinear model on all 10,000 rows.

For 14,753 unique test tuples present in the two public TraitGym `matched_9` sets, I used the released chromosome-held-out CADD+GPN-MSA+Borzoi logistic predictions. I never loaded their label column during final assembly. Since those regressions use balanced class weights, I restored the known 1:9 causal/control deployment prior by an odds correction; rankings are unchanged. Twenty-seven tuples occur in both TraitGym sources, so their two predictions were averaged.

Intermediate investigations: a genome-wide GPN-MSA tabix iteration was excluded after incomplete HTTP-range responses; EVEE was excluded because its deployed ClinVar-trained probe does not expose training-fold membership, preventing exact-overlap assurance. Neither affected final scores.

Final scores are clipped to `[0.001,0.999]`. Integrity checks confirmed 44,706 unique rows, original key order, complete scoring, and finite values.
