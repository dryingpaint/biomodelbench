# Method — transferable variant-impact score

## Goal
One score of *functional impact* that ranks well on **both** hidden
partitions (GWAS fine-mapped causal SNPs and clinical P/LP vs B/LB). I did
not try to detect which variant is which; I built a single monotone
composite of signals that are positively associated with impact in **both**
biological regimes.

## Training / reference sources
- **UCSC hg38 conservation bigWigs** (features): `cactus241way` phyloP
  (Zoonomia 241-mammal — the strongest published TraitGym single feature),
  `phyloP100way`, `phastCons100way`. `phyloP470way` was tested and **dropped**
  (weaker than the above on held-out validation).
- **CADD v1.7 API** (feature): per-variant PHRED. CADD is trained on
  derived-vs-simulated alleles, independent of ClinVar and TraitGym.
- **Ensembl VEP REST** (feature): most-severe consequence, SIFT, PolyPhen.
  The ClinVar-derived `clin_sig` / phenotype / COSMIC / HGMD colocated
  fields returned by VEP were **explicitly discarded** (they are the
  blacklisted label). SIFT/PolyPhen are algorithmic (alignment/structure).
- **Open Targets Genetics credible sets** (validation only, not a feature):
  `studyType=="gwas"`, positives = credible-set variants with
  `posteriorProbability >= 0.9`; hard negatives = in-set variants with
  PP < 0.01. Used only to sanity-check that conservation/CADD rank causal
  variants above non-causal ones — never trained on and never applied to test.

No blacklisted source was touched (no ClinVar, no TraitGym datasets, no
Kanai/PolyFun UKBB, no AlphaMissense/REVEL tables).

## Features
For each SNV: conservation at the base and max/mean over a ±7 bp window
(3 tracks); CADD PHRED; consequence-severity ordinal; missense damage
`max(PolyPhen, 1−SIFT)`; loss-of-function flag. Missing conservation is
imputed to the unconserved 5th percentile; missing CADD to the median.

## Model
A hand-weighted, rank-normalised monotone composite (no label training,
so zero label leakage into test scores):

`score = 0.40·CONS + 0.35·CADD + 0.25·CODE`, then percentile-ranked to [0,1].

- `CONS` = weighted percentile-rank blend of the conservation tracks
  (balanced between the exact-base value — what discriminates conserved
  *coding* positions for the clinical partition — and the window-max —
  what flags conserved regulatory neighbourhoods for the GWAS partition).
- `CADD` = percentile-rank of PHRED (integrated, calibrated deleteriousness).
- `CODE` = severity + missense/LoF damage; ≈constant (~0) for non-coding
  variants, so it sharpens the clinical ranking **without** reordering the
  GWAS partition.

Because AUPRC is computed within each partition and the two partitions
occupy largely different feature regimes (non-coding vs coding), an
additive monotone score ranks each well simultaneously.

## Validation
Open Targets held-out (test-overlap removed): every component is positively
associated with causal status; conservation ≥ CADD on non-coding, so
conservation carries the largest weight. Consequence ordering on test is
correct (splice/stop_gained ≈0.86 > missense ≈0.70 > synonymous ≈0.42 >
UTR/intron lower). Test coverage: VEP 41370/41390, CADD 41381/41390,
conservation >99.8%; gaps imputed to neutral.

## Anti-leak
Training/validation labels dropped for rows whose `(chrom,pos,ref,alt)`
appears in `test.parquet`: **366**. The submitted model is not fitted to
any labels, so no label information can leak into the test scores.
