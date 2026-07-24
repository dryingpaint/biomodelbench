#!/usr/bin/env python3
"""Extract allele-specific bigWig values for selected SNVs via UCSC range requests."""

from __future__ import annotations

import argparse
import concurrent.futures
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd


TRACKS = {
    "cadd_raw": "http://hgdownload.soe.ucsc.edu/gbdb/hg38/cadd1.7/{alt}.bw",
    "alphamissense": "http://hgdownload.soe.ucsc.edu/gbdb/hg38/alphaMissense/{alt}.bw",
    "revel": "http://hgdownload.soe.ucsc.edu/gbdb/hg38/revel/{alt}.bw",
}


def fetch_one(tool: str, track: str, row: tuple) -> tuple[int, float]:
    idx, chrom, pos, _ref, alt = row
    url = TRACKS[track].format(alt=alt.lower())
    cmd = [
        tool,
        f"-chrom=chr{chrom}",
        f"-start={pos - 1}",
        f"-end={pos}",
        url,
        "stdout",
    ]
    for delay in (0.0, 0.2, 1.0):
        if delay:
            time.sleep(delay)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                fields = result.stdout.strip().split()
                return idx, float(fields[3]) if len(fields) >= 4 else np.nan
        except (subprocess.TimeoutExpired, ValueError):
            pass
    return idx, np.nan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="clinical_candidates.parquet")
    parser.add_argument("--output", default="ucsc_scores.parquet")
    parser.add_argument("--tool", default="/tmp/bigWigToBedGraph")
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()

    variants = pd.read_parquet(args.input).reset_index(drop=True)
    required = ["chrom", "pos", "ref", "alt"]
    rows = [
        (i, str(r.chrom), int(r.pos), str(r.ref), str(r.alt))
        for i, r in variants[required].iterrows()
    ]
    output = variants[required].copy()
    for track in TRACKS:
        values = np.full(len(rows), np.nan)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(fetch_one, args.tool, track, row) for row in rows]
            for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
                idx, value = future.result()
                values[idx] = value
                if n % 1000 == 0:
                    print(f"{track}: {n}/{len(rows)}", flush=True)
        output[track] = values
        output.to_parquet(args.output, index=False)
        print(f"{track}: coverage={np.isfinite(values).mean():.4f}", flush=True)

    Path(args.output).resolve()


if __name__ == "__main__":
    main()
