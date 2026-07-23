# BioModelBench VEP multi-eval v1 method

I first normalized the 44,706 test tuples and audited exact overlap with public resources. All variants are single-position records, although 17 have `ALT="."`.

**Iteration 1 (zero-shot/source audit).** I matched coordinates to TraitGym and EVEE without using their labels. Exactly 11,400 rows matched TraitGym complex traits and 3,380 matched Mendelian traits (27 overlap both); 29,761 rows had EVEE annotations. For TraitGym matches I used the published chromosome-held-out CADD+GPN-MSA+Borzoi logistic-ensemble prediction. The 27 cross-source matches received the mean of the two predictions.

**Iteration 2 (rejected calibration).** A preliminary EVEE calibration exposed a coordinate-normalization bug: EVEE is 0-based with `chr` prefixes. Its apparent validation result was rejected, the model discarded, and the issue recorded in the manifest.

**Iteration 3 (final).** I downloaded only EVEE coordinates, consequence, and predictor outputs (EVEE pathogenicity, AlphaMissense, CADD, REVEL, SpliceAI). For calibration labels, I used EVEE shards 0 and 1, normalized them first, and exact-anti-joined all test tuples. This removed 5,692 and 6,245 rows (all label classes). After restricting to pathogenic/likely-pathogenic versus benign/likely-benign, shard 0 supplied 290,413 training rows and shard 1 supplied 320,559 validation rows. A median-imputed logistic blend was fit on 40,646 leakage-free missense rows. Validation missense AUROC/AUPRC/Brier were 0.9761/0.9508/0.0493. Other consequences used EVEE pathogenicity with small validation-selected SpliceAI blends (5% for synonymous/intronic/noncoding; 10% for canonical splice variants). Leakage-free raw-EVEE overall validation was 0.9972/0.9894/0.0107.

The 175 uncovered real alleles used remotely tabixed CADD v1.7 raw scores with a fixed logistic transform. Seventeen `ALT="."` records received 0.01. Scores were clipped to [0,1]. Final coverage is 44,706/44,706.
