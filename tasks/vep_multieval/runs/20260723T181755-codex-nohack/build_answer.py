#!/usr/bin/env python3
"""Build the final leakage-safe cross-source variant-importance scores."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit
from scipy.stats import norm, rankdata


ROOT = Path("data/traitgym")
KEY = ["chrom", "pos", "ref", "alt"]


def feature(ds: str, name: str, column: str) -> np.ndarray:
    path = ROOT / f"{ds}__features__{name}.parquet"
    return pd.read_parquet(path, columns=[column])[column].to_numpy(dtype=float)


def zrank(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    finite = np.isfinite(values)
    filled = values.copy()
    filled[~finite] = np.nanmedian(filled[finite])
    q = (rankdata(filled, method="average") - 0.5) / len(filled)
    return norm.ppf(np.clip(q, 1e-5, 1 - 1e-5))


def calibrated_scores(z: np.ndarray, prior: float, slope: float) -> np.ndarray:
    z = (z - np.mean(z)) / max(np.std(z), 1e-8)
    intercept = brentq(lambda b: expit(b + slope * z).mean() - prior, -20, 20)
    return expit(intercept + slope * z)


def trait_scores(ds: str, kind: str) -> pd.DataFrame:
    meta = pd.read_parquet(ROOT / f"{ds}__test.parquet", columns=KEY)
    meta["chrom"] = meta.chrom.astype(str).str.removeprefix("chr")
    cadd = feature(ds, "CADD", "RawScore")
    gpn = feature(ds, "GPN-MSA_absLLR", "score")
    borzoi = feature(ds, "Borzoi_L2_L2", "all")
    enformer = feature(ds, "Enformer_L2_L2", "all")
    phylo = feature(ds, "phyloP-241m", "score")

    if kind == "complex":
        weights = [0.34, 0.22, 0.19, 0.16, 0.09]
        slope = 0.9
    else:
        weights = [0.28, 0.42, 0.14, 0.09, 0.07]
        slope = 1.25
    z = sum(
        weight * zrank(values)
        for weight, values in zip(weights, [cadd, gpn, borzoi, enformer, phylo])
    )
    # Both public benchmark configurations use nine matched controls per positive.
    meta["score"] = calibrated_scores(z, prior=0.10, slope=slope)
    return meta


def quantile_map(reference: np.ndarray, ordering: np.ndarray) -> np.ndarray:
    """Return the reference distribution arranged according to a new ordering."""
    n = len(reference)
    order = np.argsort(ordering, kind="mergesort")
    result = np.empty(n, dtype=float)
    result[order] = np.sort(reference)
    return result


def clinical_scores() -> pd.DataFrame:
    evee = pd.read_parquet("evee_scores.parquet")
    ucsc = pd.read_parquet("ucsc_scores.parquet")
    frame = evee.merge(ucsc, on=KEY, how="left", validate="one_to_one")
    base = frame.evee.to_numpy(dtype=float)
    cadd = frame.cadd_raw.to_numpy(dtype=float)
    alpha = frame.alphamissense.to_numpy(dtype=float)
    revel = frame.revel.to_numpy(dtype=float)

    final = base.copy()
    groups = frame.consequence.fillna("unknown").astype(str)
    for consequence in groups.unique():
        idx = np.flatnonzero(groups.to_numpy() == consequence)
        valid = idx[np.isfinite(base[idx])]
        if len(valid) < 20:
            continue
        order_score = 0.85 * zrank(base[valid]) + 0.15 * zrank(cadd[valid])
        if consequence == "missense_variant":
            order_score = (
                0.72 * zrank(base[valid])
                + 0.16 * zrank(alpha[valid])
                + 0.07 * zrank(revel[valid])
                + 0.05 * zrank(cadd[valid])
            )
        final[valid] = quantile_map(base[valid], order_score)

    # A small number of API misses receive conservative annotation-only fallbacks.
    missing = ~np.isfinite(final)
    # UCSC's allele-specific CADD bigWigs contain the PHRED-like score. A
    # conservative sigmoid around the usual 20--25 deleteriousness range is
    # used only for the handful of EVEE misses.
    cadd_probability = expit((cadd - 24.0) / 2.5)
    fallback = np.where(np.isfinite(cadd_probability), cadd_probability, 0.44)
    final[missing] = fallback[missing]
    frame["score"] = np.clip(final, 0.0001, 0.9999)
    return frame[KEY + ["score"]]


def main() -> None:
    test = pd.read_parquet("test.parquet")
    complex_frame = trait_scores("complex_traits_matched_9", "complex")
    mendelian_frame = trait_scores("mendelian_traits_matched_9", "mendelian")
    clinical_frame = clinical_scores()

    candidates = pd.concat(
        [
            complex_frame.assign(source="complex"),
            mendelian_frame.assign(source="mendelian"),
            clinical_frame.assign(source="clinical"),
        ],
        ignore_index=True,
    )
    # The 27 variants shared by both TraitGym tasks get the mean of both
    # importance probabilities; all other rows have one source prediction.
    combined = candidates.groupby(KEY, as_index=False, sort=False).score.mean()
    answer = test.merge(combined, on=KEY, how="left", validate="one_to_one")
    if answer.score.isna().any():
        raise RuntimeError(f"{answer.score.isna().sum()} test rows lack scores")
    answer["score"] = answer.score.clip(0, 1).astype(float)
    answer.to_parquet("answer.parquet", index=False)


if __name__ == "__main__":
    main()
