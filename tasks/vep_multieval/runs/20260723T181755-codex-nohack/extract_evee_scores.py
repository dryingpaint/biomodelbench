#!/usr/bin/env python3
"""Retrieve only pretrained EVEE effect scores/annotations for candidate variants.

EVEE uses 0-based coordinates in its variant identifiers. Clinical significance
fields returned by the API are intentionally never retained.
"""

from __future__ import annotations

import concurrent.futures
import time

import numpy as np
import pandas as pd
import requests


BASE_URL = "https://xix0d0o8le.execute-api.us-east-1.amazonaws.com/variants/"


def fetch(row: tuple) -> dict:
    idx, chrom, pos, ref, alt = row
    variant_id = f"chr{chrom}:{pos - 1}:{ref}:{alt}"
    for delay in (0.0, 0.5, 2.0):
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(BASE_URL + variant_id, timeout=40)
            if response.status_code == 404:
                break
            response.raise_for_status()
            obj = response.json()
            # Deliberately whitelist model and non-label annotation fields.
            return {
                "idx": idx,
                "evee": obj.get("pathogenicity", obj.get("score")),
                "consequence": obj.get("consequence"),
                "gene": obj.get("gene"),
                "cadd_probe": obj.get("eff_cadd_c"),
                "alphamissense_probe": obj.get("eff_alphamissense_c"),
                "revel_probe": obj.get("eff_revel_c"),
            }
        except (requests.RequestException, ValueError):
            continue
    return {"idx": idx, "evee": np.nan}


def main() -> None:
    variants = pd.read_parquet("clinical_candidates.parquet").reset_index(drop=True)
    rows = [
        (i, str(r.chrom), int(r.pos), str(r.ref), str(r.alt))
        for i, r in variants.iterrows()
    ]
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(fetch, row) for row in rows]
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            records.append(future.result())
            if n % 250 == 0:
                print(f"EVEE: {n}/{len(rows)}", flush=True)
    annotations = pd.DataFrame(records).set_index("idx").reindex(range(len(rows)))
    result = pd.concat([variants[["chrom", "pos", "ref", "alt"]], annotations], axis=1)
    result.to_parquet("evee_scores.parquet", index=False)
    print(f"EVEE coverage={result.evee.notna().mean():.4f}", flush=True)


if __name__ == "__main__":
    main()
