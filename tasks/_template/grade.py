"""Deterministic grader for <task_id>.

Contract:
  python tasks/<task_id>/grade.py --submission <path> --out <path>

Reads `hidden/answer.parquet` and the submission, joins on the natural key,
writes deterministic metrics to `--out`.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# import numpy as np
# import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
ANSWER_PATH = TASK_DIR / "hidden" / "answer.parquet"


def grade(submission_path: Path, out_path: Path | None = None) -> dict:
    if not ANSWER_PATH.exists():
        raise SystemExit(f"hidden answer not found at {ANSWER_PATH}. Run build.py first.")

    # TODO: 1. Load truth and submission
    # TODO: 2. Validate submission columns and coverage
    # TODO: 3. Compute headline metric + any breakdowns
    # TODO: 4. Include reference-baseline gap if applicable
    metrics: dict = {}

    if out_path is not None:
        out_path.write_text(json.dumps(metrics, indent=2))
    return metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    r = grade(args.submission, args.out)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
