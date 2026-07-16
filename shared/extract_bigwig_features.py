"""Extract per-variant conservation features from public UCSC bigWig files.

Queries are done via HTTP range requests (pyBigWig can do this natively),
so no full 10+ GB local download is needed. Query cost: ~5-10 ms/variant.

Features extracted per variant (chrom, pos, ref, alt):
  - score_phyloP-100v         100-vertebrate phyloP, UCSC hg38
  - score_phastCons-100way    100-way vertebrate phastCons, UCSC hg38

Note on tracks:
  TraitGym ships `phyloP-100v` and `phastCons-43p` (43-primate). We match
  TraitGym's `phyloP-100v` exactly. We substitute UCSC's 100-way phastCons
  for phastCons-43p — different underlying alignment but similar signal;
  we extract this same track for BOTH the OT training set AND the TraitGym
  test set so both sides see identical feature values (apples-to-apples).

Usage:
  python extract_bigwig_features.py --variants <in.parquet> --out <out.parquet>

`--variants` needs columns chrom / pos / ref / alt (pos is 1-based, VCF-style).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyBigWig  # type: ignore

TRACKS = {
    "phyloP-100v": "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw",
    "phastCons-100way": "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phastCons100way/hg38.phastCons100way.bw",
}


def _norm_chrom(c: str) -> str:
    c = str(c)
    if c.startswith("chr"):
        return c
    return "chr" + c


def extract(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["_chrom_ucsc"] = df["chrom"].apply(_norm_chrom)

    out: dict[str, np.ndarray] = {}
    for name, url in TRACKS.items():
        print(f"opening {name}: {url}")
        bw = pyBigWig.open(url)
        if bw is None:
            raise RuntimeError(f"failed to open {url}")
        vals = np.full(len(df), np.nan, dtype=float)
        t0 = time.time()
        for i, (chrom, pos) in enumerate(zip(df["_chrom_ucsc"], df["pos"])):
            if i and i % 5000 == 0:
                elapsed = time.time() - t0
                print(f"  {name}: {i:>7,d}/{len(df):,}  {i/elapsed:.0f} /s")
            try:
                v = bw.values(chrom, int(pos) - 1, int(pos))
                vals[i] = v[0] if v and v[0] is not None else np.nan
            except (RuntimeError, ValueError):
                pass
        bw.close()
        out[f"score_{name}"] = vals
        n_ok = np.isfinite(vals).sum()
        print(f"  {name}: {n_ok:,}/{len(df):,} non-null")

    df = df.drop(columns=["_chrom_ucsc"])
    for k, v in out.items():
        df[k] = v
    return df


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    df = pd.read_parquet(args.variants)
    for c in ("chrom", "pos"):
        if c not in df.columns:
            raise SystemExit(f"input missing required column: {c}")
    print(f"Extracting for {len(df):,} variants")
    result = extract(df)
    result.to_parquet(args.out, index=False)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
