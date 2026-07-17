"""Deterministic grader for vep_multieval_v0.

Reads the shared submission (one score per variant), joins each hidden
answer file on (chrom, pos, ref, alt), and reports AUPRC / AUROC per
source plus a generalization-gap summary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

TASK_DIR = Path(__file__).resolve().parent
HIDDEN_DIR = TASK_DIR / "hidden"


def _grade_slice(truth: pd.DataFrame, sub: pd.DataFrame) -> dict:
    truth = truth.copy()
    truth["chrom"] = truth["chrom"].astype(str)
    merged = truth.merge(
        sub[["chrom", "pos", "ref", "alt", "score"]],
        on=["chrom", "pos", "ref", "alt"], how="left",
    )
    covered = merged["score"].notna()
    scored = merged[covered].copy()
    scored["score"] = scored["score"].clip(0.0, 1.0)
    y = scored["label"].to_numpy().astype(int)
    p = scored["score"].to_numpy(dtype=float)
    out: dict = {
        "n_total": int(len(truth)),
        "n_scored": int(len(scored)),
        "coverage": float(len(scored) / max(1, len(truth))),
        "positive_rate": float(y.mean()) if len(y) else None,
    }
    if len(np.unique(y)) < 2:
        out["auprc"] = out["auroc"] = out["brier"] = None
    else:
        out["auprc"] = float(average_precision_score(y, p))
        out["auroc"] = float(roc_auc_score(y, p))
        out["brier"] = float(brier_score_loss(y, p))
    return out


def grade(submission_path: Path, out_path: Path | None = None) -> dict:
    tg_path = HIDDEN_DIR / "traitgym_answer.parquet"
    cv_path = HIDDEN_DIR / "clinvar_answer.parquet"
    for p in (tg_path, cv_path):
        if not p.exists():
            raise SystemExit(f"hidden answer not found at {p}. Run build.py first.")
    sub = pd.read_parquet(submission_path)
    for c in ("chrom", "pos", "ref", "alt", "score"):
        if c not in sub.columns:
            raise ValueError(f"submission missing column: {c}")
    sub["chrom"] = sub["chrom"].astype(str)

    tg = pd.read_parquet(tg_path)
    cv = pd.read_parquet(cv_path)

    result = {
        "traitgym": _grade_slice(tg, sub),
        "clinvar": _grade_slice(cv, sub),
    }

    # Generalization gap: TraitGym AUPRC minus ClinVar AUPRC, at parity of
    # inputs. Interpret with base rates in mind — ClinVar's ~50% base rate
    # inflates AUPRC vs. TraitGym's 10%, so raw gap is not directly
    # comparable. We report both.
    if result["traitgym"]["auprc"] is not None and result["clinvar"]["auprc"] is not None:
        result["generalization_gap"] = {
            "delta_auprc_traitgym_minus_clinvar": (
                result["traitgym"]["auprc"] - result["clinvar"]["auprc"]
            ),
            "note": (
                "Raw AUPRC gap is confounded by base-rate differences "
                "(TraitGym base rate ~10%, ClinVar subsample ~50%). "
                "Compare each partition's AUPRC to its own base rate for "
                "a fair transfer read."
            ),
        }

    # Reference bars per source, baked in.
    result["reference_baselines"] = {
        "traitgym": {
            "phyloP-241m_Zoonomia": {"auprc": 0.2352, "auroc": 0.6146},
            "phastCons-43p_Zoonomia_primate": {"auprc": 0.2245, "auroc": 0.6168},
            "GPN-MSA_absLLR": {"auprc": 0.2081, "auroc": 0.6068},
        },
        "clinvar": {
            "note": (
                "Reference AUPRCs on this exact ClinVar subsample are "
                "computed at build time and would live in "
                "hidden/build_stats.json. Field-standard predictors "
                "(AlphaMissense, REVEL, ClinPred) score >0.9 on ClinVar "
                "P/LP vs B/LB but are trained on ClinVar and are near-"
                "circular — treat them as an upper bound, not a bar."
            ),
        },
    }

    if out_path is not None:
        out_path.write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    r = grade(args.submission, args.out)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
