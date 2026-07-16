# `_template` — how to add a new task

Copy this directory to `tasks/<your_task_id>/` and fill in:

```
tasks/<your_task_id>/
├── README.md              → what the task is, why this shape, quickstart
├── task.yaml              → metadata (see below)
├── prompt.md              → agent-facing prompt (goes into container)
├── build.py               → regenerates bundle/ + hidden/ from public sources
├── grade.py               → deterministic grader (--submission, --out)
├── .gitignore             → per-task binary-artifact ignores
├── bundle/                → what ships to the agent (created by build.py)
├── hidden/                → ground truth (created by build.py, gitignored)
└── runs/<run_id>/         → per-run artifacts (grade.json, method.md, ...)
```

## Contracts

- **`build.py`** — takes no arguments. Downloads source data, writes
  `bundle/*.parquet` + `bundle/prompt.md` (copy of the top-level prompt.md)
  + `hidden/answer.parquet` + `hidden/build_stats.json`. Idempotent.
- **`grade.py`** — takes `--submission <path>` and `--out <path>`. Reads
  `hidden/answer.parquet`, joins on the natural key, emits deterministic
  metrics to `--out`. No rubric, no LLM judge.
- **`prompt.md`** — the exact text the agent sees. Must state: the task,
  what files ship (with column schemas), what resources may be queried,
  what the submission format is (schema + row count), and what the rules
  are (no external label lookup, no self-eval on test, etc.).
- **`task.yaml`** — see `vep_c_ot_transfer_v2/task.yaml` for the shape.
  Required keys: `id, title, modality, compute_tier, headline_metric,
  answer_file, data_files, wall_clock_hours`.

## What the harness will do for you

Once your task directory follows the contract above, the generic runner
picks it up:

```bash
python tasks/<your_task_id>/build.py
uv run modal run harness/modal_runner.py::volume_upload --task <your_task_id>
uv run modal run --detach harness/modal_runner.py::launch --task <your_task_id>
```

No changes to `harness/` are needed to add a new task.

## Anti-patterns to avoid

- **Shipping features the agent should extract.** If your task is really
  about modeling, that's fine — say so in `prompt.md`. But if the interesting
  question is discovery-cost + modeling-cost combined (which is often the
  case for real problems), keep features out of `bundle/` and let the agent
  work.
- **Rubric-graded outputs.** BioModelBench grades numbers, not judgment.
  If the answer is "a well-argued case for X", this framework isn't the
  right home.
- **Non-idempotent `build.py`.** Later collaborators need to be able to
  regenerate the bundle. Cache downloaded data under `_data/` (gitignored)
  but always produce the same bundle from the same sources.
- **Answer keys in the container.** Hidden ground truth must live under
  `hidden/` and never appear in `bundle/`. The runner uploads `bundle/`,
  not the whole task dir.
