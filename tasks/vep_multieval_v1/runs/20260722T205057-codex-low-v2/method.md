# Method

I built a leakage-filtered, consequence-aware ensemble. All coordinates were normalized as hg38 strings and exact `(chrom,pos,ref,alt)` test tuples were blocked before fitting.

**Iteration 0 — audit.** I profiled 44,706 variants (44,689 SNVs and 17 dot-encoded single-base deletions) and audited public sparse annotation and benchmark prediction sources. The test contains all 11,400 complex-TraitGym and 3,380 Mendelian-TraitGym rows (27 tuples overlap those sets).

**Iteration 1 — clinical baseline.** From `GenerTeam/variant-effect-prediction` I removed 2,037 exact test matches, leaving 38,939 labeled rows. A CADD-raw/phyloP/coding-status histogram-gradient calibrator achieved chromosome-held-out AUPRC 0.9672, AUROC 0.9670, and Brier 0.0656.

**Iteration 2 — audit safeguards.** I tested sparse official CADD access and inspected EVEE. Sparse CADD was redundant with VEP. I rejected EVEE pathogenicity outputs because I could not prove their supervised probe excluded every test tuple; none entered the answer.

**Iteration 3 — enriched clinical model.** I added the HuggingFaceBio balanced non-coding ClinVar set, excluded 1,146 exact test matches, and removed 27 cross-source duplicates: 53,024 unique training variants. Ensembl VEP release 116 supplied CADD v1.7, AlphaMissense, REVEL, PrimateAI, SIFT, PolyPhen, phyloP-100way, SpliceAI, LoFTEE, consequence, impact, and gnomAD frequency. VEP clinical-significance fields were explicitly ignored; MetaRNN was also excluded because its supervised training membership was uncertain. A missingness-aware histogram-gradient model validated by five chromosome-grouped folds at AUPRC 0.9998, AUROC 0.9998, Brier 0.0032.

**Final.** Clinical-like rows use that enriched probability. Exact TraitGym members use the authors' CADD+GPN-MSA+Borzoi chromosome-held-out predictions (labels were never read), with an intercept-only prior correction to 10% prevalence. The 27 dual-TraitGym tuples average the two corrected predictions. Scores are clipped to `[1e-5, 0.99999]`; every input row is retained.
