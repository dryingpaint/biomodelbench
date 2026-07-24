#!/usr/bin/env python3
"""Fit leakage-filtered TraitGym v22 transfer models and score shipped rows."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path("data/traitgym")
KEY = ["chrom", "pos", "ref", "alt"]


def path(ds: str, group: str, name: str) -> Path:
    return ROOT / f"{ds}__{group}__{name}.parquet"


def coordinates(ds: str) -> pd.DataFrame:
    p = ROOT / f"{ds}__test.parquet"
    frame = pd.read_parquet(p)
    frame["chrom"] = frame.chrom.astype(str).str.removeprefix("chr")
    return frame


def features(ds: str, full: bool) -> pd.DataFrame:
    names = ["CADD", "GPN-MSA_LLR", "GPN-MSA_absLLR", "Borzoi_L2_L2"]
    if full:
        names += ["GPN-MSA_InnerProducts", "Borzoi_L2"]
    frames = []
    for name in names:
        frame = pd.read_parquet(path(ds, "features", name))
        frame.columns = [f"{name}_{column}" for column in frame.columns]
        frames.append(frame)
    return pd.concat(frames, axis=1)


def make_model(c: float) -> Pipeline:
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="mean", keep_empty_features=True)),
            ("scale", StandardScaler()),
            (
                "lr",
                LogisticRegression(
                    C=c,
                    class_weight="balanced",
                    max_iter=500,
                    random_state=42,
                    solver="liblinear",
                ),
            ),
        ]
    )


def cross_validate(
    x: pd.DataFrame, y: np.ndarray, groups: np.ndarray, c_values: list[float]
) -> tuple[float, list[dict]]:
    rows = []
    splitter = GroupKFold(n_splits=5)
    for c in c_values:
        pred = np.full(len(y), np.nan)
        for train_idx, valid_idx in splitter.split(x, y, groups):
            model = make_model(c)
            model.fit(x.iloc[train_idx], y[train_idx])
            pred[valid_idx] = model.predict_proba(x.iloc[valid_idx])[:, 1]
        row = {
            "C": c,
            "auprc": float(average_precision_score(y, pred)),
            "auroc": float(roc_auc_score(y, pred)),
        }
        rows.append(row)
        print(row, flush=True)
    return max(rows, key=lambda row: row["auprc"])["C"], rows


def fit_dataset(train_ds: str, test_ds: str, full: bool, output: str) -> dict:
    shipped = pd.read_parquet("test.parquet")[KEY].copy()
    shipped_set = pd.MultiIndex.from_frame(shipped)
    train_meta = coordinates(train_ds)
    excluded = pd.MultiIndex.from_frame(train_meta[KEY]).isin(shipped_set)
    usable = ~excluded

    train_x = features(train_ds, full=full).loc[usable].reset_index(drop=True)
    train_y = train_meta.loc[usable, "label"].astype(int).to_numpy()
    groups = train_meta.loc[usable, "chrom"].astype(str).to_numpy()
    test_meta = coordinates(test_ds)
    test_x = features(test_ds, full=full)

    c_values = [1e-7, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2]
    best_c, cv_rows = cross_validate(train_x, train_y, groups, c_values)
    model = make_model(best_c)
    model.fit(train_x, train_y)
    score = model.predict_proba(test_x)[:, 1]
    result = test_meta[KEY].copy()
    result["score"] = score
    result.to_parquet(output, index=False)
    return {
        "train_dataset": train_ds,
        "test_dataset": test_ds,
        "feature_set": "full" if full else "light",
        "rows_before_dedup": int(len(train_meta)),
        "exact_test_tuples_excluded": int(excluded.sum()),
        "rows_after_dedup": int(usable.sum()),
        "positive_rows_after_dedup": int(train_y.sum()),
        "best_C": best_c,
        "validation": cv_rows,
    }


def main() -> None:
    reports = []
    reports.append(
        fit_dataset(
            "complex_traits_v22_matched_9",
            "complex_traits_matched_9",
            full=True,
            output="complex_scores.parquet",
        )
    )
    reports.append(
        fit_dataset(
            "mendelian_traits_v22_matched_9",
            "mendelian_traits_matched_9",
            full=False,
            output="mendelian_scores.parquet",
        )
    )
    Path("traitgym_training_report.json").write_text(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
