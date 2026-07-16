"""Regenerate the <task_id> bundle from public sources.

Produces:
  tasks/<task_id>/bundle/train.parquet    → shipped to agent (with labels)
  tasks/<task_id>/bundle/test.parquet     → shipped to agent (unlabeled)
  tasks/<task_id>/bundle/prompt.md        → copy of the agent-facing prompt
  tasks/<task_id>/hidden/answer.parquet   → ground truth (never ships)
  tasks/<task_id>/hidden/build_stats.json → build summary

Rules for build.py:
  1. Idempotent — same sources produce the same bundle every time.
  2. Cache downloaded source data under `_data/` (gitignored).
  3. Anti-leak — remove any train rows that appear in the test set.
  4. Copy `prompt.md` into `bundle/` so it lands in the container workdir.
"""
from __future__ import annotations

from pathlib import Path

# import pandas as pd
# import numpy as np

TASK_DIR = Path(__file__).resolve().parent
DATA_DIR = TASK_DIR / "_data"
BUNDLE_DIR = TASK_DIR / "bundle"
HIDDEN_DIR = TASK_DIR / "hidden"


def main() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)

    # TODO: 1. Download training source to _data/
    # TODO: 2. Download test source to _data/
    # TODO: 3. Assemble train / test / answer dataframes
    # TODO: 4. Apply anti-leak filter (drop train rows appearing in test)
    # TODO: 5. Write bundle/train.parquet, bundle/test.parquet, hidden/answer.parquet
    # TODO: 6. Copy prompt.md into bundle/
    # TODO: 7. Emit hidden/build_stats.json


if __name__ == "__main__":
    main()
