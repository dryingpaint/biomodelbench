"""Build the vep_multieval_v0 bundle.

Test set = union of variant IDs from:
  - TraitGym complex_traits_matched_9 (11,400 rows, ~10% positive)
  - NCBI ClinVar 2-star+ Pathogenic/Likely_pathogenic vs. Benign/Likely_benign,
    subsampled to a tractable ~30k rows

The agent gets only (chrom, pos, ref, alt) and doesn't know which source
each row is from. The grader has separate hidden answer files per source.

Produces:
  tasks/vep_multieval_v0/bundle/test.parquet         → 11,400 + ~30k rows
  tasks/vep_multieval_v0/bundle/prompt.md            → agent prompt
  tasks/vep_multieval_v0/hidden/traitgym_answer.parquet
  tasks/vep_multieval_v0/hidden/clinvar_answer.parquet
  tasks/vep_multieval_v0/hidden/build_stats.json
"""
from __future__ import annotations

import gzip
import json
import random
import subprocess
import sys
from pathlib import Path

import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
DATA_DIR = TASK_DIR / "_data"
BUNDLE_DIR = TASK_DIR / "bundle"
HIDDEN_DIR = TASK_DIR / "hidden"

TG_URL = (
    "https://huggingface.co/datasets/songlab/TraitGym/resolve/main/"
    "complex_traits_matched_9/test.parquet"
)

# NCBI ClinVar clean VCF (GRCh38, filtered for review status). We use the
# stable production release VCF and post-filter for 2-star+ + binary P/B
# significance below. If a per-day snapshot pin becomes necessary for
# reproducibility, swap in a specific dated archive.
CLINVAR_VCF_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
)

# Cap ClinVar rows to keep the bundle + agent's inference cost tractable.
# 30k gives strong statistical power for AUPRC estimation and is small
# enough that per-variant online-feature extraction fits in ~10h wall clock.
CLINVAR_TARGET_ROWS = 30_000

# Balance ClinVar positives:negatives at roughly 1:1. Real ClinVar is
# ~70% pathogenic among 2-star+ variants, so we downsample positives.
CLINVAR_TARGET_POS_FRAC = 0.5

SEED = 0


def _sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _fetch_traitgym() -> pd.DataFrame:
    dst = DATA_DIR / "traitgym_complex_matched_9_test.parquet"
    if not dst.exists() or dst.stat().st_size < 100_000:
        print(f"[traitgym] fetching {dst.name}")
        _sh(["curl", "-sSfLo", str(dst), TG_URL])
    df = pd.read_parquet(dst)
    df["chrom"] = df["chrom"].astype(str)
    print(f"[traitgym] {len(df):,} rows, {int(df['label'].sum())} positives")
    return df


def _fetch_clinvar() -> Path:
    dst = DATA_DIR / "clinvar.vcf.gz"
    if not dst.exists() or dst.stat().st_size < 10_000_000:
        print(f"[clinvar] fetching {dst.name} (~120 MB)")
        _sh(["curl", "-sSfLo", str(dst), CLINVAR_VCF_URL])
    return dst


CANONICAL = {str(i) for i in range(1, 23)}

# ClinVar review-status field CLNREVSTAT values that count as ≥2-star.
# Golden-standard subset from NCBI's docs.
GOLD_REVSTAT = {
    "criteria_provided,_multiple_submitters,_no_conflicts",
    "reviewed_by_expert_panel",
    "practice_guideline",
}

# Significance mapping.
PATHOGENIC = {"Pathogenic", "Likely_pathogenic", "Pathogenic/Likely_pathogenic"}
BENIGN = {"Benign", "Likely_benign", "Benign/Likely_benign"}


def _parse_clinvar_vcf(vcf_gz: Path) -> pd.DataFrame:
    rows: list[dict] = []
    print("[clinvar] parsing VCF (this reads the file linearly, ~1-2 min)")
    with gzip.open(vcf_gz, "rt") as f:
        for i, line in enumerate(f):
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                continue
            chrom, pos, _id, ref, alt = parts[0], parts[1], parts[2], parts[3], parts[4]
            if chrom not in CANONICAL:
                continue
            if len(ref) != 1 or len(alt) != 1:
                continue  # SNVs only
            info = parts[7]
            info_kv: dict[str, str] = {}
            for kv in info.split(";"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    info_kv[k] = v
            clnrevstat = info_kv.get("CLNREVSTAT", "")
            if clnrevstat not in GOLD_REVSTAT:
                continue
            clnsig = info_kv.get("CLNSIG", "")
            if clnsig in PATHOGENIC:
                label = 1
            elif clnsig in BENIGN:
                label = 0
            else:
                continue
            rows.append({
                "chrom": chrom,
                "pos": int(pos),
                "ref": ref,
                "alt": alt,
                "label": label,
                "clnsig": clnsig,
            })
            if i % 500_000 == 0 and i > 0:
                print(f"  scanned {i:,} VCF lines; kept {len(rows):,}")
    df = pd.DataFrame(rows)
    print(f"[clinvar] {len(df):,} 2-star+ P/LP/B/LB variants after filter")
    return df


def _subsample_clinvar(df: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(SEED)
    positives = df[df["label"] == 1]
    negatives = df[df["label"] == 0]
    n_pos_target = int(CLINVAR_TARGET_ROWS * CLINVAR_TARGET_POS_FRAC)
    n_neg_target = CLINVAR_TARGET_ROWS - n_pos_target
    if len(positives) > n_pos_target:
        positives = positives.sample(n=n_pos_target, random_state=SEED)
    if len(negatives) > n_neg_target:
        negatives = negatives.sample(n=n_neg_target, random_state=SEED)
    out = pd.concat([positives, negatives], ignore_index=True)
    out = out.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    print(f"[clinvar] subsampled to {len(out):,} rows (pos={int(out['label'].sum())})")
    return out


def main() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tg = _fetch_traitgym()
    clinvar_vcf = _fetch_clinvar()
    clinvar = _parse_clinvar_vcf(clinvar_vcf)
    clinvar = _subsample_clinvar(clinvar)

    # De-duplicate any variants that happen to be in both sources (unlikely
    # but possible for a very small handful). Keep the TraitGym label there
    # (source of truth for the primary bench).
    tg_keys = set(map(tuple, tg[["chrom", "pos", "ref", "alt"]].to_numpy()))
    clinvar_keys = set(map(tuple, clinvar[["chrom", "pos", "ref", "alt"]].to_numpy()))
    overlap = tg_keys & clinvar_keys
    if overlap:
        print(f"[dedup] {len(overlap)} variants appear in both TraitGym and ClinVar; dropping from ClinVar side")
        clinvar_ok = clinvar[
            ~clinvar[["chrom", "pos", "ref", "alt"]].apply(tuple, axis=1).isin(overlap)
        ].reset_index(drop=True)
    else:
        clinvar_ok = clinvar

    test = pd.concat(
        [
            tg[["chrom", "pos", "ref", "alt"]],
            clinvar_ok[["chrom", "pos", "ref", "alt"]],
        ],
        ignore_index=True,
    )
    test["chrom"] = test["chrom"].astype(str)
    # Shuffle so ordering doesn't leak source (agent should not infer from row order).
    test = test.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    test.to_parquet(BUNDLE_DIR / "test.parquet", index=False)

    (BUNDLE_DIR / "prompt.md").write_bytes((TASK_DIR / "prompt.md").read_bytes())

    tg_answer = tg[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)
    tg_answer.to_parquet(HIDDEN_DIR / "traitgym_answer.parquet", index=False)

    clinvar_answer = clinvar_ok[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)
    clinvar_answer.to_parquet(HIDDEN_DIR / "clinvar_answer.parquet", index=False)

    stats = {
        "test_rows_total": int(len(test)),
        "traitgym_rows": int(len(tg_answer)),
        "traitgym_positives_hidden": int(tg_answer["label"].sum()),
        "traitgym_positive_rate": float(tg_answer["label"].mean()),
        "clinvar_rows": int(len(clinvar_answer)),
        "clinvar_positives_hidden": int(clinvar_answer["label"].sum()),
        "clinvar_positive_rate": float(clinvar_answer["label"].mean()),
        "sources": {
            "traitgym": TG_URL,
            "clinvar": CLINVAR_VCF_URL,
        },
        "clinvar_review_status_kept": sorted(GOLD_REVSTAT),
        "clinvar_significance_positive": sorted(PATHOGENIC),
        "clinvar_significance_negative": sorted(BENIGN),
    }
    (HIDDEN_DIR / "build_stats.json").write_text(json.dumps(stats, indent=2))

    print()
    print("done.")
    print(f"  bundle/test.parquet — {len(test):,} rows (source hidden)")
    print(f"  hidden/traitgym_answer.parquet — {len(tg_answer):,} rows, {int(tg_answer['label'].sum())} pos")
    print(f"  hidden/clinvar_answer.parquet — {len(clinvar_answer):,} rows, {int(clinvar_answer['label'].sum())} pos")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"subprocess failed: {exc}", file=sys.stderr)
        sys.exit(1)
