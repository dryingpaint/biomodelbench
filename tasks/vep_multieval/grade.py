"""Deterministic grader for vep_multieval.

Reads the shared submission (one score per variant), joins each hidden
answer file on (chrom, pos, ref, alt), and reports AUPRC / AUROC per
partition plus ClinVar per-consequence / per-review-status /
per-significance-pair slices.

Hidden partitions:
- traitgym_complex     — TraitGym complex_traits_matched_9 (GWAS-fine-mapped common regulatory)
- traitgym_mendelian   — TraitGym mendelian_traits_matched_9 (GWAS-fine-mapped Mendelian rare)
- clinvar              — 2-star+ ClinVar P/LP vs B/LB
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
    tg_c_path = HIDDEN_DIR / "traitgym_complex_answer.parquet"
    tg_m_path = HIDDEN_DIR / "traitgym_mendelian_answer.parquet"
    cv_path = HIDDEN_DIR / "clinvar_answer.parquet"
    for p in (tg_c_path, tg_m_path, cv_path):
        if not p.exists():
            raise SystemExit(f"hidden answer not found at {p}. Run build.py first.")
    sub = pd.read_parquet(submission_path)
    for c in ("chrom", "pos", "ref", "alt", "score"):
        if c not in sub.columns:
            raise ValueError(f"submission missing column: {c}")
    sub["chrom"] = sub["chrom"].astype(str)

    tg_c = pd.read_parquet(tg_c_path)
    tg_m = pd.read_parquet(tg_m_path)
    cv = pd.read_parquet(cv_path)

    result = {
        "traitgym_complex": _grade_slice(tg_c, sub),
        "traitgym_mendelian": _grade_slice(tg_m, sub),
        "clinvar": _grade_slice(cv, sub),
    }

    MIN_ROWS_PER_SLICE = 100
    if "mc_class" in cv.columns:
        clinvar_slices: dict[str, dict] = {}
        for cls, sub_truth in cv.groupby("mc_class"):
            if len(sub_truth) < MIN_ROWS_PER_SLICE:
                continue
            drop_cols = [c for c in ("mc_class", "review_status", "significance_tier") if c in sub_truth.columns]
            metrics = _grade_slice(sub_truth.drop(columns=drop_cols), sub)
            metrics["mc_class"] = cls
            clinvar_slices[cls] = metrics
        result["clinvar_by_consequence"] = clinvar_slices

    if "review_status" in cv.columns:
        rev_slices: dict[str, dict] = {}
        for tier, sub_truth in cv.groupby("review_status"):
            if len(sub_truth) < MIN_ROWS_PER_SLICE:
                continue
            drop_cols = [c for c in ("mc_class", "review_status", "significance_tier") if c in sub_truth.columns]
            metrics = _grade_slice(sub_truth.drop(columns=drop_cols), sub)
            metrics["review_status"] = tier
            rev_slices[tier] = metrics
        result["clinvar_by_review_status"] = rev_slices

    if "significance_tier" in cv.columns:
        sig_pairs = {
            "strong_only_P_vs_B": ["pathogenic", "benign"],
            "hedged_only_LP_vs_LB": ["likely_pathogenic", "likely_benign"],
            "any_P_vs_any_B": ["pathogenic", "likely_pathogenic", "benign", "likely_benign"],
        }
        sig_slices: dict[str, dict] = {}
        for name, allowed in sig_pairs.items():
            sub_truth = cv[cv["significance_tier"].isin(allowed)]
            if len(sub_truth) < MIN_ROWS_PER_SLICE:
                continue
            drop_cols = [c for c in ("mc_class", "review_status", "significance_tier") if c in sub_truth.columns]
            metrics = _grade_slice(sub_truth.drop(columns=drop_cols), sub)
            metrics["significance_tiers_included"] = allowed
            sig_slices[name] = metrics
        result["clinvar_by_significance_pair"] = sig_slices

    result["reference_baselines"] = {
        "traitgym_complex": {
            "note": "AUPRC by chromosome-weighted average (Benegas et al. 2025).",
            "CADD+GPN-MSA+Borzoi_LR_ensemble": {"auprc": 0.362},
            "Enformer_LR_probe": {"auprc": 0.303},
            "Borzoi_LR_probe": {"auprc": 0.297},
            "CADD_v1.7_LR": {"auprc": 0.284},
            "GPN-MSA_LR_probe": {"auprc": 0.269},
            "CADD_v1.7_zero_shot": {"auprc": 0.250},
            "Enformer_L2_zero_shot": {"auprc": 0.245},
            "phastCons-43p_Zoonomia": {"auprc": 0.237},
            "phyloP-241m_Zoonomia": {"auprc": 0.227},
            "GPN-MSA_absLLR_zero_shot": {"auprc": 0.224},
        },
        "traitgym_mendelian": {
            "note": "AUPRC by chromosome-weighted average (Benegas et al. 2025).",
            "CADD+GPN-MSA+Borzoi_LR_ensemble": {"auprc": 0.648},
            "GPN-MSA_LR_probe": {"auprc": 0.584},
            "CADD_v1.7_LR": {"auprc": 0.549},
            "Enformer_LR_probe": {"auprc": 0.501},
            "Borzoi_LR_probe": {"auprc": 0.487},
            "phyloP-241m_Zoonomia": {"auprc": 0.462},
        },
        "clinvar_missense": {
            "note": "Missense-only AUROC on ClinVar (various curated splits).",
            "AlphaMissense": {"auroc": 0.972},
            "Evo-2_covariance_probe": {"auroc": 0.971},
            "CADD_v1.7": {"auroc": 0.966},
            "GPN-MSA": {"auroc": 0.952},
            "REVEL": {"auroc": 0.930},
            "Evo-2_loss_based": {"auroc": 0.932},
            "CADD_v1.6": {"auroc": 0.911},
            "ESM-1v": {"auroc": 0.83},
            "NTv3": {"auroc": 0.586},
        },
        "clinvar_by_consequence_evo2": {
            "note": "Evo-2 covariance probe per-consequence AUROC (EVEE 2026).",
            "missense": 0.971,
            "synonymous": 0.961,
            "nonsense": 0.900,
            "splice": 0.924,
            "utr": 0.929,
            "intronic": 0.984,
            "other_noncoding": 0.969,
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
