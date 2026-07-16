# BioModelBench

An agentic benchmark for biological modeling. Each task hands a coding agent
labeled training data plus a set of unlabeled test variants and asks it to
build a predictor from scratch — deciding which foundation models, which
online resources, and which features to use, then submitting predictions.
A deterministic grader compares the submission to hidden ground truth.

## Repo layout

```
biomodelbench/
├── SPEC.md                       overall design intent, task tiers, scoring
├── harness/
│   ├── modal_runner.py           generic Modal launcher — takes a task_id
│   └── image.py                  shared container image (A10G, torch, pyBigWig, …)
├── shared/
│   └── extract_bigwig_features.py    per-variant lookup against remote bigWig
├── tasks/
│   └── <task_id>/                one directory per task; self-contained
│       ├── README.md             what the task is + how to build/grade
│       ├── task.yaml             metadata (id, modality, tier, headline metric)
│       ├── prompt.md             agent-facing prompt (goes into container)
│       ├── build.py              builds the bundle from public sources
│       ├── grade.py              deterministic grader
│       ├── bundle/               what ships to the agent (gitignored data)
│       ├── hidden/               ground truth — never ships (gitignored)
│       └── runs/<run_id>/        per-run artifacts (grade.json, method.md, ...)
└── docs/
```

## One-time setup

You need a [Modal](https://modal.com) account and an Anthropic API key.

```bash
# authenticate the modal CLI once
uv run modal token new

# create the anthropic-api Modal secret that the runner references
uv run modal secret create anthropic-api ANTHROPIC_API_KEY=sk-ant-...
```

The runner is otherwise self-contained — the container image, GPU
allocation, and shared Volume are provisioned on first launch.

## Running the shipped task

```bash
# 1. Regenerate the bundle + hidden answer from public sources
uv run python tasks/vep_c_ot_transfer_v2/build.py

# 2. Upload the bundle to a shared Modal Volume
uv run modal run harness/modal_runner.py::volume_upload \
    --task vep_c_ot_transfer_v2

# 3. Launch a single agent attempt (headless claude in a Modal A10G container)
uv run modal run --detach harness/modal_runner.py::launch \
    --task vep_c_ot_transfer_v2

# 4. Grade a downloaded submission
uv run python tasks/vep_c_ot_transfer_v2/grade.py \
    --submission tasks/vep_c_ot_transfer_v2/runs/<run_id>/answer.parquet \
    --out tasks/vep_c_ot_transfer_v2/runs/<run_id>/grade.json
```

`modal_runner.launch` will do steps 3 + 4 in one call by default: it syncs
artifacts back after the container exits and invokes the task's local
`grade.py`.

## Adding a new task

Every task is a directory under `tasks/<task_id>/`. Minimum contents:

- **`task.yaml`** — id, modality (dna / protein / rna / …), compute tier
  (T0 zero-shot → T2 full pretraining), headline metric (auprc / auroc /
  spearman / …), and a one-line description.
- **`prompt.md`** — the exact text the agent sees. Should include: the task
  statement, what files ship (schema of `train.parquet` / `test.parquet`),
  what resources the agent may query, what the submission format is, and
  the rules (what it cannot do). See `vep_c_ot_transfer_v2/prompt.md` for
  the reference shape.
- **`build.py`** — regenerates `bundle/` (what ships) and `hidden/` (ground
  truth) from public sources. Must be idempotent and self-contained (no
  arguments — just runs).
- **`grade.py`** — reads `--submission <path>` and `--out <path>`, joins
  against `hidden/answer.parquet`, writes `grade.json` with the headline
  metric plus any per-slice breakdowns. Deterministic. No rubric, no
  keyword matching.

Optional:

- **`README.md`** — quickstart, motivation, links.
- **`runs/`** — committed per-run summaries (small text/JSON only). Large
  binary intermediates (parquet, npz) go through the per-task `.gitignore`.

The generic `harness/modal_runner.py` finds any task under `tasks/<task_id>/`
and can launch it — as long as `bundle/` and `prompt.md` exist and
`grade.py` follows the CLI convention above.

## Non-goals

- **Rubric-graded / LLM-judged tasks.** BioModelBench tasks require an
  objective ground truth and a deterministic scoring function. If the
  answer can't be graded by comparing numbers, it doesn't belong here.
- **Curriculum-style dependencies between tasks.** Each task is independent.
- **Hosted leaderboards.** The framework produces `grade.json`; publishing
  results is a separate concern.
