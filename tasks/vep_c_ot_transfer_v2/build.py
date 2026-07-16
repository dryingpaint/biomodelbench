"""Regenerate the vep_c_ot_transfer_v2 bundle from public sources.

Idempotent. Downloads on first run, reuses local cache on subsequent runs.

Produces:
  tasks/vep_c_ot_transfer_v2/bundle/train.parquet   → 72,093 rows shipped to agent
  tasks/vep_c_ot_transfer_v2/bundle/test.parquet    → 11,400 rows shipped (unlabeled)
  tasks/vep_c_ot_transfer_v2/hidden/answer.parquet  → ground-truth labels for grader
  tasks/vep_c_ot_transfer_v2/hidden/build_stats.json → summary of the ingest

Sources:
  - Open Targets Genetics credible_set parquet dumps (EBI FTP, public)
  - TraitGym complex_traits_matched_9 test set (HuggingFace, public)

Design notes:
  - We sample 40 parts across the full 200-part OT credible_set release to
    get genome-wide coverage. Grabbing all 200 works too — just slower.
  - Positives: unique variants with pip_max >= 0.9 across all GWAS studies.
  - Negatives: unique variants with pip_max < 0.01, sampled to cap size.
  - Anti-leak: any (chrom, pos, ref, alt) present in the TraitGym test set
    is dropped from the OT training corpus before shipping.
  - Only canonical autosomes (chr 1..22) — TraitGym's test set is autosome-only.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
DATA_DIR = TASK_DIR / "_data"
BUNDLE_DIR = TASK_DIR / "bundle"
HIDDEN_DIR = TASK_DIR / "hidden"

OT_URL_BASE = "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/credible_set"
OT_UUID = "8ee8599e-d3fd-478e-bb9b-6a3c3243641d"
OT_PART_STRIDE = 5  # sample every 5th part → 40 parts across 200

TG_URL = (
    "https://huggingface.co/datasets/songlab/TraitGym/resolve/main/"
    "complex_traits_matched_9/test.parquet"
)

POS_PIP = 0.9
NEG_PIP = 0.01
MAX_NEGATIVES = 30_000


def _sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _ensure_ot_parts() -> list[Path]:
    """Download a genome-wide sample of OT credible-set parquet parts."""
    ot_dir = DATA_DIR / "opentargets"
    ot_dir.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for n in range(0, 200, OT_PART_STRIDE):
        name = f"part-{n:05d}-{OT_UUID}-c000.snappy.parquet"
        dst = ot_dir / f"cs_gw_{n:05d}.parquet"
        if not dst.exists() or dst.stat().st_size < 100_000:
            if dst.exists():
                dst.unlink()
            print(f"  fetch {name}")
            _sh(["curl", "-sSfLo", str(dst), f"{OT_URL_BASE}/{name}"])
        parts.append(dst)
    return parts


def _ensure_traitgym() -> Path:
    """Download the TraitGym complex_traits_matched_9 test set."""
    tg_dir = DATA_DIR / "traitgym"
    tg_dir.mkdir(parents=True, exist_ok=True)
    dst = tg_dir / "complex_traits_matched_9_test.parquet"
    if not dst.exists() or dst.stat().st_size < 100_000:
        print(f"  fetch {dst.name}")
        _sh(["curl", "-sSfLo", str(dst), TG_URL])
    return dst


def _explode_gwas(parts: list[Path]) -> pd.DataFrame:
    """Load OT credible-set parts, filter to GWAS, explode nested `locus` array."""
    frames = [pd.read_parquet(p) for p in parts]
    df = pd.concat(frames, ignore_index=True)
    gwas = df[df["studyType"] == "gwas"].reset_index(drop=True)
    print(f"  {len(gwas):,} GWAS credible sets")
    canonical = {str(i) for i in range(1, 23)}
    rows: list[dict] = []
    for _, row in gwas.iterrows():
        loc = row["locus"]
        if loc is None or (isinstance(loc, float) and pd.isna(loc)):
            continue
        for v in loc:
            vid = v.get("variantId")
            if not vid:
                continue
            parts_id = vid.split("_")
            if len(parts_id) < 4 or parts_id[0] not in canonical:
                continue
            chrom, pos_s, ref, alt = parts_id[0], parts_id[1], parts_id[2], "_".join(parts_id[3:])
            try:
                pos = int(pos_s)
            except ValueError:
                continue
            rows.append({
                "chrom": chrom,
                "pos": pos,
                "ref": ref,
                "alt": alt,
                "pip": float(v.get("posteriorProbability") or 0.0),
                "studyId": row["studyId"],
            })
    return pd.DataFrame(rows)


def main() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] fetching Open Targets credible-set parts")
    parts = _ensure_ot_parts()
    print(f"      {len(parts)} parts available in {DATA_DIR/'opentargets'}")

    print("[2/4] fetching TraitGym complex_traits_matched_9 test set")
    tg_path = _ensure_traitgym()
    tg = pd.read_parquet(tg_path)
    tg["chrom"] = tg["chrom"].astype(str)
    print(f"      {len(tg):,} test variants, {int(tg['label'].sum())} positives")

    print("[3/4] exploding OT credible sets and computing per-variant max PIP")
    ot = _explode_gwas(parts)
    print(f"      {len(ot):,} variant×locus rows across {ot['studyId'].nunique():,} studies")
    ot_max = (
        ot.groupby(["chrom", "pos", "ref", "alt"], as_index=False)
        .agg(pip_max=("pip", "max"), n_studies=("studyId", "nunique"))
    )
    ot_max["chrom"] = ot_max["chrom"].astype(str)
    print(f"      {len(ot_max):,} unique variants after dedup")

    tg_keys = set(map(tuple, tg[["chrom", "pos", "ref", "alt"]].to_numpy()))
    ot_keys = ot_max[["chrom", "pos", "ref", "alt"]].apply(tuple, axis=1)
    overlap_mask = ot_keys.isin(tg_keys)
    dropped = int(overlap_mask.sum())
    print(f"      anti-leak: dropping {dropped} OT variants that overlap TraitGym test")
    ot_clean = ot_max[~overlap_mask].reset_index(drop=True)

    pos = ot_clean[ot_clean["pip_max"] >= POS_PIP].copy()
    pos["label"] = 1
    neg = ot_clean[ot_clean["pip_max"] < NEG_PIP].copy()
    if len(neg) > MAX_NEGATIVES:
        neg = neg.sample(n=MAX_NEGATIVES, random_state=0).reset_index(drop=True)
    neg["label"] = 0
    train = pd.concat([pos, neg], ignore_index=True)[
        ["chrom", "pos", "ref", "alt", "label", "pip_max", "n_studies"]
    ]

    test = tg[["chrom", "pos", "ref", "alt"]].reset_index(drop=True)
    answer = tg[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)

    print("[4/4] writing bundle and hidden answer")
    train.to_parquet(BUNDLE_DIR / "train.parquet", index=False)
    test.to_parquet(BUNDLE_DIR / "test.parquet", index=False)
    answer.to_parquet(HIDDEN_DIR / "answer.parquet", index=False)

    # Copy the task-facing prompt into bundle/ so it lands next to the parquets.
    prompt_src = TASK_DIR / "prompt.md"
    (BUNDLE_DIR / "prompt.md").write_bytes(prompt_src.read_bytes())

    stats = {
        "train_rows": int(len(train)),
        "train_positives": int(train["label"].sum()),
        "train_chromosomes": sorted(train["chrom"].unique().tolist()),
        "test_rows": int(len(test)),
        "test_positives_hidden": int(answer["label"].sum()),
        "test_positive_rate": float(answer["label"].mean()),
        "overlap_dropped": dropped,
        "ot_pos_pip_threshold": POS_PIP,
        "ot_neg_pip_threshold": NEG_PIP,
        "ot_parts_used": len(parts),
    }
    (HIDDEN_DIR / "build_stats.json").write_text(json.dumps(stats, indent=2))

    print("done.")
    print(f"  bundle/train.parquet — {len(train):,} rows ({int(train['label'].sum())} pos)")
    print(f"  bundle/test.parquet  — {len(test):,} rows (labels hidden)")
    print(f"  hidden/answer.parquet — {len(answer):,} rows (ground truth)")
    print(f"  hidden/build_stats.json — {stats}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"subprocess failed: {exc}", file=sys.stderr)
        sys.exit(1)
