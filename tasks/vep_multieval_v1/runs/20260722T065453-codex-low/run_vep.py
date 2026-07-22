import concurrent.futures as cf
import json
import math
import os
import random
import sys
import time

import pandas as pd
import requests

TEST = "/task/test.parquet"
OUTDIR = "/task/vep_batches"
BATCH = 200
WORKERS = 16
URL = "https://rest.ensembl.org/vep/homo_sapiens/region"
os.makedirs(OUTDIR, exist_ok=True)

d = pd.read_parquet(TEST).reset_index(names="row_id")


def simplify(x):
    out = {
        "row_id": None,
        "input": x.get("input"),
        "most_severe_consequence": x.get("most_severe_consequence"),
        "cadd_raw": None,
        "cadd_phred": None,
        "alphamissense": None,
        "spliceai": None,
        "sift_deleterious": None,
        "polyphen_damaging": None,
    }
    vals = []
    for k, v in x.items():
        if k.endswith("_consequences") and isinstance(v, list):
            vals.extend(v)
    for v in vals:
        if v.get("cadd_raw") is not None:
            out["cadd_raw"] = float(v["cadd_raw"])
        if v.get("cadd_phred") is not None:
            out["cadd_phred"] = float(v["cadd_phred"])
        am = v.get("alphamissense") or {}
        if am.get("am_pathogenicity") is not None:
            z = float(am["am_pathogenicity"])
            out["alphamissense"] = max(z, out["alphamissense"] or 0.0)
        sp = v.get("spliceai") or {}
        ds = [float(sp[q]) for q in ("DS_AG", "DS_AL", "DS_DG", "DS_DL") if sp.get(q) is not None]
        if ds:
            out["spliceai"] = max(max(ds), out["spliceai"] or 0.0)
        if v.get("sift_score") is not None:
            z = 1.0 - float(v["sift_score"])
            out["sift_deleterious"] = max(z, out["sift_deleterious"] or 0.0)
        if v.get("polyphen_score") is not None:
            z = float(v["polyphen_score"])
            out["polyphen_damaging"] = max(z, out["polyphen_damaging"] or 0.0)
    return out


def run_batch(b):
    path = os.path.join(OUTDIR, f"batch_{b:04d}.json")
    if os.path.exists(path):
        return b, "cached"
    g = d.iloc[b * BATCH : (b + 1) * BATCH]
    variants = [f"{r.chrom} {r.pos} . {r.ref} {r.alt} . . ." for r in g.itertuples()]
    payload = {
        "variants": variants,
        "CADD": 1,
        "AlphaMissense": 1,
        "SpliceAI": 1,
        "minimal": 1,
        "pick": 1,
    }
    err = None
    for attempt in range(8):
        try:
            r = requests.post(
                URL,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json=payload,
                timeout=300,
            )
            if r.status_code == 200:
                by_input = {x.get("input"): simplify(x) for x in r.json()}
                rows = []
                for row_id, v in zip(g.row_id, variants):
                    z = by_input.get(v, {"input": v})
                    z["row_id"] = int(row_id)
                    rows.append(z)
                tmp = path + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(rows, f)
                os.replace(tmp, path)
                return b, "ok"
            err = f"HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            err = repr(e)
        time.sleep(min(30, 2 ** attempt + random.random()))
    return b, "FAILED " + str(err)


nb = math.ceil(len(d) / BATCH)
start_batch = int(sys.argv[1]) if len(sys.argv) > 1 else 0
end_batch = int(sys.argv[2]) if len(sys.argv) > 2 else nb
with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = [ex.submit(run_batch, b) for b in range(start_batch, min(end_batch, nb))]
    for i, fut in enumerate(cf.as_completed(futs), 1):
        b, status = fut.result()
        print(f"{i}/{len(futs)} batch={b} {status}", flush=True)
