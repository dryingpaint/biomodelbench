"""Deterministic grader for bacdive_multitrait.

Reads a submission parquet, joins against the hidden per-target labels
on `assembly_accession`, and reports per-target metrics + per-tier and
overall normalized composites.

Per-target metrics:
- Binary probability targets → AUPRC, AUROC, Brier
- Multiclass label targets → macro-F1, balanced accuracy
- Continuous float targets → Spearman ρ, MAE
- Pathway probability targets → AUPRC, AUROC

Composite: for each target, normalize as
    max(0, (score - trivial) / (published_ref - trivial))
where trivial is the always-predict-prior baseline for that metric,
and published_ref is the literature bar in `REFERENCE_BASELINES`.
Then average within each tier and take the weighted mean across tiers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    mean_absolute_error,
    roc_auc_score,
)

TASK_DIR = Path(__file__).resolve().parent
ANSWER_PATH = TASK_DIR / "hidden" / "answer.parquet"

# ── target-type registry (must match build.py) ────────────────────────
BINARY_TARGETS = ["gram_positive_prob", "sporulation_prob", "motility_prob"]
CATEGORICAL_TARGETS = {
    "oxygen_tolerance": ["aerobic", "anaerobic", "facultative", "microaerophilic"],
    "temperature_range": ["psychrophilic", "mesophilic", "thermophilic", "extreme_thermophilic"],
    "cell_shape": ["bacillus", "coccus", "spiral", "coccobacillus", "vibrio", "filament", "other"],
}
CONTINUOUS_TARGETS = ["optimum_temperature_c", "optimum_ph"]
PATHWAYS = [
    "nitrogen_fixation", "nitrate_reduction", "denitrification", "sulfate_reduction",
    "fermentation", "cellulose_degradation", "xylan_degradation", "chitin_degradation",
    "fumarate_reduction", "iron_reduction",
]
PATHWAY_COLS = [f"pathway_{p}_prob" for p in PATHWAYS]

TIER1_TARGETS = ["oxygen_tolerance", "optimum_temperature_c", "optimum_ph", "temperature_range"]
TIER2_TARGETS = ["gram_positive_prob", "sporulation_prob", "motility_prob", "cell_shape"]
TIER3_TARGETS = PATHWAY_COLS
TIER_WEIGHTS = {"tier1_growth": 0.40, "tier2_morphology": 0.30, "tier3_pathways": 0.30}

# Published family-holdout reference baselines (see prompt.md, README.md).
# Primary metric per target:
REFERENCE_BASELINES: dict[str, dict] = {
    # Tier 1
    "oxygen_tolerance":       {"metric": "macro_f1", "trivial": 0.25, "ref": 0.70},
    "optimum_temperature_c":  {"metric": "spearman", "trivial": 0.0,  "ref": 0.70},
    "optimum_ph":             {"metric": "spearman", "trivial": 0.0,  "ref": 0.35},
    "temperature_range":      {"metric": "macro_f1", "trivial": 0.25, "ref": 0.60},
    # Tier 2
    "gram_positive_prob":     {"metric": "auroc",    "trivial": 0.5,  "ref": 0.95},
    "sporulation_prob":       {"metric": "auroc",    "trivial": 0.5,  "ref": 0.90},
    "motility_prob":          {"metric": "auroc",    "trivial": 0.5,  "ref": 0.85},
    "cell_shape":             {"metric": "macro_f1", "trivial": 1/7,  "ref": 0.55},
    # Tier 3 — pathways (macro-AUPRC per pathway)
    "pathway_nitrogen_fixation_prob":     {"metric": "auprc", "ref": 0.90, "trivial_from_prior": True},
    "pathway_sulfate_reduction_prob":     {"metric": "auprc", "ref": 0.80, "trivial_from_prior": True},
    "pathway_nitrate_reduction_prob":     {"metric": "auprc", "ref": 0.75, "trivial_from_prior": True},
    "pathway_denitrification_prob":       {"metric": "auprc", "ref": 0.75, "trivial_from_prior": True},
    "pathway_cellulose_degradation_prob": {"metric": "auprc", "ref": 0.75, "trivial_from_prior": True},
    "pathway_xylan_degradation_prob":     {"metric": "auprc", "ref": 0.70, "trivial_from_prior": True},
    "pathway_chitin_degradation_prob":    {"metric": "auprc", "ref": 0.70, "trivial_from_prior": True},
    "pathway_fermentation_prob":          {"metric": "auprc", "ref": 0.65, "trivial_from_prior": True},
    "pathway_iron_reduction_prob":        {"metric": "auprc", "ref": 0.60, "trivial_from_prior": True},
    "pathway_fumarate_reduction_prob":    {"metric": "auprc", "ref": 0.55, "trivial_from_prior": True},
}


def _score_binary(y: np.ndarray, p: np.ndarray) -> dict:
    m: dict = {}
    p = np.clip(p, 0.0, 1.0)
    if len(np.unique(y)) < 2:
        m["auprc"] = m["auroc"] = m["brier"] = None
    else:
        m["auprc"] = float(average_precision_score(y, p))
        m["auroc"] = float(roc_auc_score(y, p))
        m["brier"] = float(brier_score_loss(y, p))
    return m


def _score_categorical(y_true: np.ndarray, y_pred: np.ndarray, labels: list[str]) -> dict:
    mask = pd.Series(y_pred).isin(labels).to_numpy()
    # Rows where the agent emitted an out-of-vocab label count as "wrong" —
    # we substitute a sentinel that won't match any true label.
    y_pred_norm = np.where(mask, y_pred, "__oov__")
    m: dict = {}
    if len(np.unique(y_true)) < 2:
        m["macro_f1"] = m["balanced_accuracy"] = None
    else:
        # Use labels= to fix class order; f1 uses zero_division=0 to avoid
        # division-by-zero warnings when a class is absent from predictions.
        m["macro_f1"] = float(
            f1_score(y_true, y_pred_norm, labels=labels, average="macro", zero_division=0)
        )
        m["balanced_accuracy"] = float(balanced_accuracy_score(y_true, y_pred_norm))
    # Distribution of predicted labels (sanity check)
    vc = pd.Series(y_pred_norm).value_counts(normalize=True).to_dict()
    m["prediction_distribution"] = {str(k): float(v) for k, v in vc.items()}
    m["oov_rate"] = float((~mask).mean())
    return m


def _score_continuous(y: np.ndarray, p: np.ndarray) -> dict:
    m: dict = {}
    # Drop rows where the prediction is NaN
    mask = ~np.isnan(p)
    y_c = y[mask]
    p_c = p[mask]
    if len(y_c) < 3 or float(np.std(p_c)) == 0 or float(np.std(y_c)) == 0:
        m["spearman"] = None
    else:
        rho, _ = spearmanr(y_c, p_c)
        m["spearman"] = float(rho) if np.isfinite(rho) else None
    m["mae"] = float(mean_absolute_error(y_c, p_c)) if len(y_c) else None
    m["prediction_coverage"] = float(mask.mean())
    return m


def _normalize(score: float | None, trivial: float, ref: float) -> float | None:
    if score is None:
        return None
    if ref == trivial:
        return None
    v = (score - trivial) / (ref - trivial)
    return float(max(0.0, v))


def _primary_score(target: str, per_target: dict) -> float | None:
    spec = REFERENCE_BASELINES[target]
    return per_target.get(spec["metric"])


def _trivial_for_pathway(base_rate: float, metric: str) -> float:
    # AUPRC baseline = base rate; AUROC baseline = 0.5.
    if metric == "auprc":
        return float(base_rate)
    if metric == "auroc":
        return 0.5
    return 0.0


def _score_one_target(target: str, truth: pd.Series, sub: pd.Series) -> dict:
    """Score one target column against the hidden truth. Returns a dict."""
    # Mask rows where the truth is NaN — grader ignores those species.
    truth_mask = truth.notna()
    truth_c = truth[truth_mask]
    sub_c = sub[truth_mask]
    n_scored = int(truth_mask.sum())
    result: dict = {"n_scored": n_scored, "n_total": int(len(truth))}
    if n_scored == 0:
        result["metrics"] = None
        result["primary"] = None
        result["normalized"] = None
        return result

    if target in BINARY_TARGETS:
        y = truth_c.astype(int).to_numpy()
        p = pd.to_numeric(sub_c, errors="coerce").to_numpy(dtype=float)
        p = np.where(np.isnan(p), 0.5, p)  # NaN prediction → prior of 0.5
        metrics = _score_binary(y, p)
        primary = metrics.get("auroc")
    elif target in CATEGORICAL_TARGETS:
        labels = CATEGORICAL_TARGETS[target]
        y = truth_c.astype(str).to_numpy()
        p = sub_c.fillna("__missing__").astype(str).to_numpy()
        metrics = _score_categorical(y, p, labels)
        primary = metrics.get("macro_f1")
    elif target in CONTINUOUS_TARGETS:
        y = truth_c.astype(float).to_numpy()
        p = pd.to_numeric(sub_c, errors="coerce").to_numpy(dtype=float)
        metrics = _score_continuous(y, p)
        primary = metrics.get("spearman")
    elif target in PATHWAY_COLS:
        y = truth_c.astype(int).to_numpy()
        p = pd.to_numeric(sub_c, errors="coerce").to_numpy(dtype=float)
        p = np.where(np.isnan(p), 0.0, p)
        p = np.clip(p, 0.0, 1.0)
        metrics = _score_binary(y, p)
        primary = metrics.get("auprc")
    else:
        raise ValueError(f"unknown target: {target}")

    result["metrics"] = metrics
    result["primary"] = primary

    # Normalization to composite score
    spec = REFERENCE_BASELINES[target]
    ref = spec["ref"]
    if spec.get("trivial_from_prior"):
        base_rate = float(truth_c.astype(float).mean())
        trivial = _trivial_for_pathway(base_rate, spec["metric"])
        result["base_rate"] = base_rate
    else:
        trivial = spec["trivial"]
    result["reference_bar"] = ref
    result["trivial_baseline"] = trivial
    result["normalized"] = _normalize(primary, trivial, ref)
    return result


def grade(submission_path: Path, out_path: Path | None = None) -> dict:
    if not ANSWER_PATH.exists():
        raise SystemExit(f"hidden answer not found at {ANSWER_PATH}. Run build.py first.")
    truth = pd.read_parquet(ANSWER_PATH)
    sub = pd.read_parquet(submission_path)
    if "assembly_accession" not in sub.columns:
        raise ValueError("submission missing column: assembly_accession")

    required_targets = (
        BINARY_TARGETS
        + list(CATEGORICAL_TARGETS.keys())
        + CONTINUOUS_TARGETS
        + PATHWAY_COLS
    )
    missing_cols = [c for c in required_targets if c not in sub.columns]
    if missing_cols:
        # Not a hard failure — grader treats missing columns as fully-uncovered
        # (all NaN). Report so the agent can see what it skipped.
        print(f"warning: submission missing target columns: {missing_cols}")
        for c in missing_cols:
            sub[c] = np.nan

    merged = truth.merge(
        sub[["assembly_accession", *required_targets]],
        on="assembly_accession",
        how="left",
        suffixes=("_truth", "_pred"),
    )
    n_test = int(len(truth))
    coverage_row = float(
        merged[required_targets[0] + "_pred"].notna().mean()
    ) if (required_targets[0] + "_pred") in merged.columns else 0.0

    per_target_result: dict = {}
    for target in required_targets:
        t_col = target + "_truth"
        p_col = target + "_pred"
        # When target didn't collide with truth col name (unlikely since we always
        # ship truth as `target`), the merge still gave us the right names via suffix.
        if t_col not in merged.columns:
            t_col = target
        if p_col not in merged.columns:
            p_col = target
        per_target_result[target] = _score_one_target(target, merged[t_col], merged[p_col])

    # Tier composites: mean of normalized scores over targets with a value
    def tier_mean(target_list: list[str]) -> float | None:
        vals = [
            per_target_result[t]["normalized"]
            for t in target_list
            if per_target_result[t]["normalized"] is not None
        ]
        return float(np.mean(vals)) if vals else None

    tier1 = tier_mean(TIER1_TARGETS)
    tier2 = tier_mean(TIER2_TARGETS)
    tier3 = tier_mean(TIER3_TARGETS)

    # Overall composite: weighted mean over tiers with a value
    tiers = [
        ("tier1_growth", tier1),
        ("tier2_morphology", tier2),
        ("tier3_pathways", tier3),
    ]
    active = [(name, v) for name, v in tiers if v is not None]
    if active:
        w_sum = sum(TIER_WEIGHTS[name] for name, _ in active)
        composite = float(sum(TIER_WEIGHTS[name] * v for name, v in active) / w_sum)
    else:
        composite = None

    out: dict = {
        "n_test_strains": n_test,
        "row_coverage": coverage_row,
        "composite": composite,
        "tier1_growth_composite": tier1,
        "tier2_morphology_composite": tier2,
        "tier3_pathways_composite": tier3,
        "tier_weights": TIER_WEIGHTS,
        "per_target": per_target_result,
        "reference_baselines_note": (
            "Reference bars are literature ballparks under family-holdout: Traitar "
            "(Weimann 2016) for categorical traits, Sauer & Wang (2019) for OGT, "
            "Weissman 2021 for growth-rate-adjacent codon signals, dbCAN / CAZy for "
            "carbohydrate pathways, and marker-gene analyses for N/S/Fe cycles."
        ),
    }

    if out_path is not None:
        out_path.write_text(json.dumps(out, indent=2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    r = grade(args.submission, args.out)
    print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
