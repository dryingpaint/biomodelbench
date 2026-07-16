# <task title>

## Task

<One paragraph describing what the agent has to predict.>

## What's shipped

### `train.parquet` — <N> rows

Columns:
- ...

### `test.parquet` — <N> rows

Columns:
- ... **No label.**

## Feature extraction is on you

<Or: "features are pre-extracted, see columns above" — pick one. State
what online resources the agent may hit.>

## Compute + wall clock

Modal A10G, 8 CPU, 32 GB RAM, 24 GB VRAM. ~4 hours.

## Deliverables

- `answer.parquet` — columns `<natural key>, <prediction>`.
- `method.md` (< 500 words).
- `training_manifest.json` — every URL / API / dataset you touched.

## Rules

- You cannot see the test labels.
- <Any task-specific label-leak restrictions, e.g. "no fetching TraitGym
  from HF.">