"""Deterministic grader for bacdive_gram.

Reads a submission parquet, joins against the hidden Gram-staining labels
on `assembly_accession`, and reports AUPRC / AUROC / Brier / coverage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

TASK_DIR = Path(__file__).resolve().parent
ANSWER_PATH = TASK_DIR / "hidden" / "answer.parquet"

# Reference-baseline ballpark for Gram prediction from genome content. These
# are field-standard order-of-magnitude bars for a family-holdout setting;
# swap in exact numbers once we compute per-baseline scores on this split.
REFERENCE_BASELINES: dict[str, dict[str, float]] = {
    "class_prior (always Gram-)": {"auprc": None, "auroc": 0.5, "note": "trivial baseline"},
    "codon-usage_+_tetranucleotide": {"auprc": None, "auroc": 0.85, "note": "field-standard rough bar"},
    "protein-family-profile_classifier": {"auprc": None, "auroc": 0.95, "note": "well-tuned; drops on family-holdout"},
}


def grade(submission_path: Path, out_path: Path | None = None) -> dict:
    if not ANSWER_PATH.exists():
        raise SystemExit(f"hidden answer not found at {ANSWER_PATH}. Run build.py first.")
    truth = pd.read_parquet(ANSWER_PATH)
    sub = pd.read_parquet(submission_path)
    for c in ("assembly_accession", "gram_prob"):
        if c not in sub.columns:
            raise ValueError(f"submission missing column: {c}")

    merged = truth.merge(
        sub[["assembly_accession", "gram_prob"]], on="assembly_accession", how="left"
    )
    covered = merged["gram_prob"].notna()
    coverage = float(covered.mean())
    scored = merged[covered].copy()
    scored["gram_prob"] = scored["gram_prob"].clip(0.0, 1.0)

    y = scored["label"].to_numpy().astype(int)
    p = scored["gram_prob"].to_numpy(dtype=float)
    m: dict = {
        "test_variants_total": int(len(truth)),
        "test_variants_scored": int(len(scored)),
        "coverage": coverage,
        "positive_rate": float(y.mean()) if len(y) else None,
    }
    if len(np.unique(y)) < 2:
        m["auprc"] = m["auroc"] = m["brier"] = None
    else:
        m["auprc"] = float(average_precision_score(y, p))
        m["auroc"] = float(roc_auc_score(y, p))
        m["brier"] = float(brier_score_loss(y, p))

    m["reference_baselines"] = REFERENCE_BASELINES

    if out_path is not None:
        out_path.write_text(json.dumps(m, indent=2))
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    r = grade(args.submission, args.out)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
