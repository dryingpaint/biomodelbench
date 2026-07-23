# Method — Bacterial multi-phenotype profile (bacdive_multitrait)

## Overview
Phenotypes are predicted **mechanistically from genome content**, so the models
generalize to the held-out (family-disjoint) test strains. Only the given inputs
(`assembly_accession`, `phylum`) are used at prediction time; taxonomy names were
never used as features.

## Pipeline
1. **Genome retrieval.** Resolved every accession to its FASTA via the NCBI
   RefSeq/GenBank assembly summaries (+ FTP directory listing for suppressed
   records) and downloaded all 4,331 assemblies (`*_genomic.fna.gz`).
2. **Gene calling & composition (pyrodigal).** Per genome: size, GC, contig N50,
   gene count, coding density, mean gene length, genome-wide **amino-acid
   composition (20)**, the **IVYWREL** thermophily index, charged-residue
   fraction, and dinucleotide frequencies (16). These are strong for growth
   temperature and carry lifestyle signal.
3. **Functional gene content (pyhmmer).**
   - **KOfam** (KEGG ortholog HMMs): a curated subset of ~650 KOs selected by
     keyword-matching KO definitions to the target phenotypes (nitrogen/sulfur
     metabolism, respiration & oxidative stress, fermentation, fumarate/iron
     reduction, flagellar/chemotaxis, sporulation, cell envelope) plus explicit
     marker genes (nifHDK, dsrAB, nirK/S, nosZ, frdABCD, spo*, fli/flg*, …).
     Hits filtered by KOfam's per-KO adaptive score thresholds.
   - **dbCAN** (CAZy HMMs): 201 GH/CBM/CE/AA families implicated in
     cellulose / xylan / chitin degradation.
   Both produce per-genome copy-number profiles.
4. **Models.** One LightGBM model per target on the combined feature matrix
   (composition + KOfam + dbCAN + phylum one-hot):
   - binary probability targets → gradient-boosted classifiers (natural
     probabilities for good Brier);
   - `optimum_temperature_c`, `optimum_ph` → L1-regression;
   - `oxygen_tolerance`, `temperature_range`, `cell_shape` → multiclass
     (class-balanced) predicting the label string.
   NaN training labels are dropped per target (missing-target-aware).

## Validation
All hyper-parameters and estimates use **family-grouped 5-fold CV** (families
mapped from NCBI taxonomy, used only to build folds), matching the family-holdout
evaluation. Reported family-holdout CV meets/exceeds several reference bars
(gram AUROC ≈ 0.99, sporulation ≈ 0.97, sulfate-reduction AUPRC ≈ 0.80,
temperature ρ ≈ 0.58).
