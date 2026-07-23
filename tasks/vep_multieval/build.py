"""Build the vep_multieval bundle.

Same shape as v0, adds TraitGym Mendelian as a third hidden partition and
uses the same ClinVar sub-sample. Total test size ≈ 42,500 rows.

Test set = union of variant IDs from:
  - TraitGym complex_traits_matched_9 (11,400 rows, ~10% positive)
  - TraitGym mendelian_traits_matched_9 (~1,140 rows, ~10% positive)
  - NCBI ClinVar 2-star+ P/LP vs B/LB, subsampled to ~30k rows

The agent gets only (chrom, pos, ref, alt) and doesn't know which
source each row is from. The grader has separate hidden answer files
per source.

Produces:
  tasks/vep_multieval/bundle/test.parquet
  tasks/vep_multieval/bundle/prompt.md
  tasks/vep_multieval/hidden/traitgym_complex_answer.parquet
  tasks/vep_multieval/hidden/traitgym_mendelian_answer.parquet
  tasks/vep_multieval/hidden/clinvar_answer.parquet
  tasks/vep_multieval/hidden/build_stats.json
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

TG_COMPLEX_URL = (
    "https://huggingface.co/datasets/songlab/TraitGym/resolve/main/"
    "complex_traits_matched_9/test.parquet"
)
TG_MENDELIAN_URL = (
    "https://huggingface.co/datasets/songlab/TraitGym/resolve/main/"
    "mendelian_traits_matched_9/test.parquet"
)

CLINVAR_VCF_URL = (
    "https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar.vcf.gz"
)

CLINVAR_TARGET_ROWS = 30_000
CLINVAR_TARGET_POS_FRAC = 0.5
SEED = 0

CANONICAL = {str(i) for i in range(1, 23)}

GOLD_REVSTAT = {
    "criteria_provided,_multiple_submitters,_no_conflicts",
    "reviewed_by_expert_panel",
    "practice_guideline",
}
PATHOGENIC = {"Pathogenic", "Likely_pathogenic", "Pathogenic/Likely_pathogenic"}
BENIGN = {"Benign", "Likely_benign", "Benign/Likely_benign"}


def _sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _fetch_traitgym(name: str, url: str) -> pd.DataFrame:
    dst = DATA_DIR / f"traitgym_{name}_matched_9_test.parquet"
    if not dst.exists() or dst.stat().st_size < 100_000:
        print(f"[traitgym-{name}] fetching {dst.name}")
        _sh(["curl", "-sSfLo", str(dst), url])
    df = pd.read_parquet(dst)
    df["chrom"] = df["chrom"].astype(str)
    print(f"[traitgym-{name}] {len(df):,} rows, {int(df['label'].sum())} positives")
    return df


def _fetch_clinvar() -> Path:
    dst = DATA_DIR / "clinvar.vcf.gz"
    if not dst.exists() or dst.stat().st_size < 10_000_000:
        print(f"[clinvar] fetching {dst.name} (~120 MB)")
        _sh(["curl", "-sSfLo", str(dst), CLINVAR_VCF_URL])
    return dst


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
                continue
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


def _dedup_against(df: pd.DataFrame, exclude_keys: set) -> pd.DataFrame:
    tuples = df[["chrom", "pos", "ref", "alt"]].apply(tuple, axis=1)
    mask = ~tuples.isin(exclude_keys)
    dropped = int((~mask).sum())
    if dropped:
        print(f"[dedup] dropped {dropped} rows overlapping earlier partition(s)")
    return df[mask].reset_index(drop=True)


def main() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tg_c = _fetch_traitgym("complex", TG_COMPLEX_URL)
    tg_m = _fetch_traitgym("mendelian", TG_MENDELIAN_URL)
    clinvar_vcf = _fetch_clinvar()
    clinvar = _parse_clinvar_vcf(clinvar_vcf)
    clinvar = _subsample_clinvar(clinvar)

    # Precedence for overlap resolution: TraitGym complex > TraitGym Mendelian > ClinVar.
    tg_c_keys = set(map(tuple, tg_c[["chrom", "pos", "ref", "alt"]].to_numpy()))
    tg_m = _dedup_against(tg_m, tg_c_keys)
    tg_m_keys = set(map(tuple, tg_m[["chrom", "pos", "ref", "alt"]].to_numpy()))
    clinvar = _dedup_against(clinvar, tg_c_keys | tg_m_keys)

    test = pd.concat(
        [
            tg_c[["chrom", "pos", "ref", "alt"]],
            tg_m[["chrom", "pos", "ref", "alt"]],
            clinvar[["chrom", "pos", "ref", "alt"]],
        ],
        ignore_index=True,
    )
    test["chrom"] = test["chrom"].astype(str)
    # Shuffle so ordering doesn't leak source.
    test = test.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    test.to_parquet(BUNDLE_DIR / "test.parquet", index=False)

    (BUNDLE_DIR / "prompt.md").write_bytes((TASK_DIR / "prompt.md").read_bytes())

    tg_c_answer = tg_c[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)
    tg_c_answer.to_parquet(HIDDEN_DIR / "traitgym_complex_answer.parquet", index=False)

    tg_m_answer = tg_m[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)
    tg_m_answer.to_parquet(HIDDEN_DIR / "traitgym_mendelian_answer.parquet", index=False)

    clinvar_answer = clinvar[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)
    clinvar_answer.to_parquet(HIDDEN_DIR / "clinvar_answer.parquet", index=False)

    stats = {
        "test_rows_total": int(len(test)),
        "traitgym_complex_rows": int(len(tg_c_answer)),
        "traitgym_complex_positives_hidden": int(tg_c_answer["label"].sum()),
        "traitgym_complex_positive_rate": float(tg_c_answer["label"].mean()),
        "traitgym_mendelian_rows": int(len(tg_m_answer)),
        "traitgym_mendelian_positives_hidden": int(tg_m_answer["label"].sum()),
        "traitgym_mendelian_positive_rate": float(tg_m_answer["label"].mean()),
        "clinvar_rows": int(len(clinvar_answer)),
        "clinvar_positives_hidden": int(clinvar_answer["label"].sum()),
        "clinvar_positive_rate": float(clinvar_answer["label"].mean()),
        "sources": {
            "traitgym_complex": TG_COMPLEX_URL,
            "traitgym_mendelian": TG_MENDELIAN_URL,
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
    print(f"  hidden/traitgym_complex_answer.parquet   — {len(tg_c_answer):,} rows, {int(tg_c_answer['label'].sum())} pos")
    print(f"  hidden/traitgym_mendelian_answer.parquet — {len(tg_m_answer):,} rows, {int(tg_m_answer['label'].sum())} pos")
    print(f"  hidden/clinvar_answer.parquet            — {len(clinvar_answer):,} rows, {int(clinvar_answer['label'].sum())} pos")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"subprocess failed: {exc}", file=sys.stderr)
        sys.exit(1)
