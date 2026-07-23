import json
import time
from pathlib import Path

import pandas as pd
import requests

df = pd.read_parquet("test.parquet")
outdir = Path("vep_batches")
outdir.mkdir(exist_ok=True)
url = "https://rest.ensembl.org/vep/human/region"
params = {"canonical": 1, "mane": 1, "CADD": 1, "AlphaMissense": 1, "SpliceAI": 1}
headers = {"Content-Type": "application/json", "Accept": "application/json"}
batch_size = 200

for start in range(0, len(df), batch_size):
    path = outdir / f"{start:06d}.json"
    if path.exists():
        continue
    z = df.iloc[start:start + batch_size]
    variants = [f"{r.chrom} {r.pos} . {r.ref} {r.alt} . . ." for r in z.itertuples(index=False)]
    error = None
    for attempt in range(10):
        try:
            r = requests.post(url, params=params, headers=headers,
                              json={"variants": variants}, timeout=120)
            if r.status_code == 200:
                payload = r.json()
                path.write_text(json.dumps(payload))
                print(f"{start + len(z)}/{len(df)}", flush=True)
                break
            error = f"HTTP {r.status_code}: {r.text[:200]}"
            delay = float(r.headers.get("Retry-After", min(60, 2**attempt)))
        except Exception as e:
            error = repr(e)
            delay = min(60, 2**attempt)
        time.sleep(delay)
    else:
        raise RuntimeError(f"batch {start} failed: {error}")
