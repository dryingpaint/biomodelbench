"""Deterministic grader for vep_c_ot_transfer_v2.

Reads a submission parquet, joins against the hidden answer, and writes a
grade.json with the headline metric (AUPRC) plus AUROC, Brier, coverage,
per-chromosome breakdown, and gap-vs-best-baseline.

Usage:
    python tasks/vep_c_ot_transfer_v2/grade.py \
        --submission tasks/vep_c_ot_transfer_v2/runs/<run_id>/answer.parquet \
        --out       tasks/vep_c_ot_transfer_v2/runs/<run_id>/grade.json
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

# Reference baselines from the original TraitGym release, on the same 11,400
# test variants. Committed so the grader can report a gap-vs-best-baseline
# without needing to re-run the baselines.
REFERENCE_BASELINES: dict[str, dict[str, float]] = {
    "phyloP-241m (Zoonomia)": {"auprc": 0.2352, "auroc": 0.6146},
    "phastCons-43p (Zoonomia primate)": {"auprc": 0.2245, "auroc": 0.6168},
    "GPN-MSA_absLLR": {"auprc": 0.2081, "auroc": 0.6068},
    "phastCons-100way (UCSC vertebrate)": {"auprc": 0.1814, "auroc": 0.5763},
    "phyloP-100v (UCSC vertebrate)": {"auprc": 0.1717, "auroc": 0.5833},
    "evo2_40b_LLR": {"auprc": 0.1265, "auroc": 0.5161},
}


def grade(submission_path: Path, out_path: Path | None = None) -> dict:
    if not ANSWER_PATH.exists():
        raise SystemExit(
            f"hidden answer not found at {ANSWER_PATH}. Run build.py first."
        )
    truth = pd.read_parquet(ANSWER_PATH)
    truth["chrom"] = truth["chrom"].astype(str)
    sub = pd.read_parquet(submission_path)
    for c in ("chrom", "pos", "ref", "alt", "causal_prob"):
        if c not in sub.columns:
            raise ValueError(f"submission missing column: {c}")
    sub["chrom"] = sub["chrom"].astype(str)

    merged = truth.merge(
        sub[["chrom", "pos", "ref", "alt", "causal_prob"]],
        on=["chrom", "pos", "ref", "alt"], how="left",
    )
    covered = merged["causal_prob"].notna()
    coverage = float(covered.mean())
    scored = merged[covered].copy()
    scored["causal_prob"] = scored["causal_prob"].clip(0.0, 1.0)

    y = scored["label"].to_numpy().astype(int)
    p = scored["causal_prob"].to_numpy(dtype=float)

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

    per_chrom = []
    for c in sorted(scored["chrom"].unique()):
        mask = scored["chrom"] == c
        yc = scored.loc[mask, "label"].to_numpy().astype(int)
        pc = scored.loc[mask, "causal_prob"].to_numpy(dtype=float)
        e = {"chrom": c, "n": int(len(yc)), "positives": int(yc.sum())}
        if len(np.unique(yc)) >= 2:
            e["auprc"] = float(average_precision_score(yc, pc))
            e["auroc"] = float(roc_auc_score(yc, pc))
        per_chrom.append(e)
    m["per_chrom"] = per_chrom

    m["reference_baselines"] = REFERENCE_BASELINES
    if m["auprc"] is not None and REFERENCE_BASELINES:
        best = max(REFERENCE_BASELINES.items(), key=lambda kv: kv[1]["auprc"])
        m["gap_vs_best_baseline"] = {
            "name": best[0],
            "baseline_auprc": best[1]["auprc"],
            "delta_auprc": m["auprc"] - best[1]["auprc"],
        }

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
