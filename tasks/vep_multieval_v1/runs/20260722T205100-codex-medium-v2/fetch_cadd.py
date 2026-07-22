import concurrent.futures as cf
import json
import time
from pathlib import Path

import pandas as pd
import requests

TEST = Path("test.parquet")
OUT = Path("cadd_scores.jsonl")
BASE = "https://cadd.gs.washington.edu/api/v1.0/GRCh38-v1.7"


def key(row):
    return f"{row.chrom}:{row.pos}_{row.ref}_{row.alt}"


def fetch(k):
    url = f"{BASE}/{k}"
    for attempt in range(7):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                x = r.json()
                if x:
                    return k, float(x[0]["RawScore"]), float(x[0]["PHRED"]), None
            if r.status_code not in (429, 500, 502, 503, 504):
                return k, None, None, f"HTTP {r.status_code}"
        except Exception as e:
            err = repr(e)
        time.sleep(min(20, 0.5 * 2**attempt))
    return k, None, None, err if "err" in locals() else f"HTTP {r.status_code}"


df = pd.read_parquet(TEST)
keys = [key(r) for r in df.itertuples(index=False)]
done = {}
if OUT.exists():
    with OUT.open() as f:
        for line in f:
            x = json.loads(line)
            done[x["key"]] = x
todo = [k for k in keys if k not in done or done[k].get("error")]
print(f"already={len(done)} todo={len(todo)}", flush=True)
with OUT.open("a") as f, cf.ThreadPoolExecutor(max_workers=24) as ex:
    for i, (k, raw, phred, error) in enumerate(ex.map(fetch, todo), 1):
        f.write(json.dumps({"key": k, "raw": raw, "phred": phred, "error": error}) + "\n")
        if i % 100 == 0:
            f.flush()
            print(f"{i}/{len(todo)}", flush=True)
