# Method — Bacterial Gram-stain prediction (bacdive_gram_v0)

## Approach
Gram status is a genome-encoded phenotype: Gram-negatives (diderms) build an
outer membrane with LPS; Gram-positives (monoderms) build a thick peptidoglycan
wall with teichoic acids and LPXTG-anchored surface proteins. Because the test
families are unseen, I predict from **conserved biological markers in the genome
content**, not from taxon identity.

## Pipeline
1. **Genome retrieval.** For all 2704 train+test accessions I fetched assembly
   metadata (assembly name, GC%, genome length, contig count, gene count) from
   the NCBI Datasets API, then downloaded RefSeq proteomes (`_protein.faa.gz`)
   from the NCBI genome FTP. For 47 unannotated assemblies I called genes with
   pyrodigal.
2. **Marker features (HMMER).** Using `pyhmmer`, I searched each proteome
   (dom E-value < 1e-5, score > 20) against 20 curated Pfam HMMs:
   - *Gram-negative / outer-membrane*: LpxC, LpxK (lipid A), Omp85/BamA, LptD,
     LptC, LolA (LPS transport & OM assembly), OmpA, OMP β-barrel, KdsB, LPS
     heptosyltransferase, Wzz/Wzy.
   - *Gram-positive / cell-wall*: Sortase, LPXTG Gram-pos anchor, WTA
     glycerophosphotransferase.
   - *Shared*: transpeptidase/transglycosylase PBPs, SLT.
   Per genome I record hit counts and best bit-scores, plus engineered
   `gn_core`/`gp_core` presence sums.
3. **Auxiliary features.** GC%, genome length, contig count, coding density,
   proteome size, mean protein length, 20-dim amino-acid composition, and the
   provided phylum (one-hot). No genus/species/family/organism-name was ever
   used as a feature.
4. **Model.** A diversified ensemble — LightGBM on all features (5 seeds),
   LightGBM on markers+phylum only (5 seeds, most family-robust), and an
   L2 logistic regression — blended 0.45/0.30/0.25, then isotonic-calibrated.
5. **Validation.** 5-fold **family-grouped** cross-validation (families held
   out, mirroring the test split; family recovered via Entrez taxonomy for
   grouping only). Isotonic calibration fit on grouped out-of-fold predictions.

## Results (family-grouped CV)
AUPRC **0.990**, AUROC **0.994**, Brier **0.022**. An ablation shows a
markers-only model reaches AUPRC 0.989 — performance stems from
family-generalizable biology, not memorized taxonomy. Within the mixed
Firmicutes phylum, AUROC ≈ 0.90 (LPS markers identify diderm Negativicutes).
The markers also corrected a mislabeled test strain (*Agitococcus*, labeled
Firmicutes but genomically Gammaproteobacteria → correctly predicted
Gram-negative).

## Output
`answer.parquet` (`assembly_accession`, `gram_prob`), 393 rows, full coverage,
mean predicted Gram-positive rate 0.34 (matches the stated base rate).
