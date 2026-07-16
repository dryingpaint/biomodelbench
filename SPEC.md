# BioModelBench — design

## Motivation

Modern biology has more open modeling questions than trained ML researchers
to work on them. If a coding agent can build a variant-effect predictor from
scratch by choosing features, running foundation-model inference, and
training a supervised head — all without human intervention — that's both a
useful capability signal and a directly useful piece of infrastructure for
biology.

BioModelBench is a set of tasks structured around that hypothesis. Each
task ships a labeled training set + an unlabeled test set + a prompt
describing the goal, and the agent has to figure out the rest.

## What a BioModelBench task IS

- **Agentic.** The evaluation target is a Claude (or other) coding agent
  running headless in a Modal container with internet access and GPU. It
  writes and runs Python, downloads data, trains models, and submits
  predictions.
- **Blind.** Test labels never enter the container. A deterministic grader
  has them and runs after the container exits.
- **Objectively scored.** Every task's headline metric is a single number
  (AUPRC, AUROC, Spearman ρ, …) computed against ground truth. No rubrics,
  no keyword matching, no LLM-as-judge.
- **Self-contained.** One directory per task under `tasks/<task_id>/`
  containing everything needed to regenerate the bundle, run the agent, and
  grade a submission.

## What a task is NOT

- **Not a curriculum.** Tasks don't depend on each other. Ordering exists
  only for the compute-tier taxonomy below.
- **Not a hosted leaderboard.** The grader emits `grade.json`; sharing is a
  separate concern.
- **Not a coding-style exam.** Ability to write clean Python is not the
  measurement — building a model that generalizes is.

## Compute tiers

Every task declares a compute tier that describes how much work is expected
of the agent. This shapes wall-clock budgets and GPU allocations.

| Tier | What the agent typically does |
|------|-------------------------------|
| **T0** | Inference-only. Zero-shot scoring with an existing FM. |
| **T1** | Light training. Frozen embeddings + linear probe / MLP / LoRA. |
| **T2** | Full pretraining or de-novo model design. |

`vep_c_ot_transfer_v2` is T1 in nominal budget but with an important
addition: the agent must also *decide which features to extract* and *from
which online resources*. That decision-cost is part of the challenge.

## Scoring properties every task must have

1. **Deterministic.** Same submission → same grade. No stochastic judges.
2. **Auditable.** Every intermediate — training set composition, hidden
   answer, baseline scores on the same test — is derivable from public
   sources by re-running `build.py`.
3. **Anti-leak.** If the training source and test source might share
   variants, positions, or trait metadata, `build.py` must remove the
   overlap before shipping.
4. **Method-agnostic.** The grader scores predictions, never the pipeline
   that produced them. An FM ensemble, a mechanistic model, a well-tuned
   linear baseline — all fair game if the numbers say so.

## Detailed task specs

Individual task designs live under `docs/`. See:

- [`docs/variant_effect_prediction.md`](docs/variant_effect_prediction.md) —
  the VEP track spec (VEP-M / VEP-N / VEP-C). Only VEP-C is shipped today.
