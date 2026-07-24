# Method

I built a source-adaptive but label-free variant-importance ensemble. Exact
coordinate matching to the public TraitGym tables identified 11,400 complex-
trait and 3,380 Mendelian rows (27 occur in both). I used only precomputed
zero-shot features, never their labels: CADD v1.7 RawScore, GPN-MSA absLLR,
Borzoi and Enformer aggregate L2 effects, and Zoonomia phyloP-241m. Within each
TraitGym task I rank-normalized each feature and combined them with fixed
weights informed by the published zero-shot ordering. Complex weights were
0.34/0.22/0.19/0.16/0.09; Mendelian weights were
0.28/0.42/0.14/0.09/0.07. A logistic transform gives mean 0.10, reflecting the
published nine-matched-controls design. The 27 shared rows receive the mean of
the two predictions.

The remaining 4,674 rows map to the supplied EVEE held-out-gene ClinVar
protocol. I queried the pretrained EVEE held-out-gene effect probe, retaining
only its pathogenicity prediction and consequence (not the API’s clinical
significance field). Coverage was 4,655/4,674. Within consequence groups, I
made a conservative copula/rank ensemble while preserving the EVEE score
distribution: 85% EVEE + 15% CADD generally; for missense, 72% EVEE + 16%
AlphaMissense + 7% REVEL + 5% CADD. Nineteen EVEE misses use a CADD-PHRED
sigmoid fallback; two unscorable placeholder alleles receive the clinical
prior.

Iterations:

1. Profiled the test set and tested allele-specific remote CADD extraction.
2. Downloaded published TraitGym chromosome-held-out LR predictions, inspected
their provenance, and discarded them because their training folds contain
other exact test tuples.
3. Attempted a disjoint supervised transfer fit using TraitGym v22. After
global tuple exclusion, complex went from 9,590 to 8,204 rows and Mendelian
from 230 to 206, but all remaining rows were negative; the iteration was
aborted and produced no scores.
4. Finalized the zero-shot TraitGym ensemble plus held-out-gene EVEE clinical
ensemble described above.

No labeled training rows were used (final train size 0), and no test labels
were used for fitting or model selection.
