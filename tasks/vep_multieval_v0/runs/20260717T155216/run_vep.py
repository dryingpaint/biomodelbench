import requests, json, time, os
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

df = pd.read_parquet('/task/test.parquet')
df['chrom'] = df['chrom'].astype(str)
variants = [f"{r.chrom} {r.pos} . {r.ref} {r.alt} . . ." for r in df.itertuples()]
print(f"total variants: {len(variants)}", flush=True)

URL = 'https://rest.ensembl.org/vep/human/region'
HEAD = {'Content-Type':'application/json','Accept':'application/json'}
BATCH = 200
WORKERS = 10

batches = [(i, variants[i:i+BATCH]) for i in range(0, len(variants), BATCH)]

def post_batch(args):
    i, batch = args
    for t in range(8):
        try:
            r = requests.post(URL, headers=HEAD,
                              data=json.dumps({'variants':batch,'SIFT':1}), timeout=200)
            if r.status_code == 200:
                return i, r.json()
            if r.status_code == 429:
                wait = float(r.headers.get('Retry-After', 3))
                time.sleep(wait + 1); continue
            time.sleep(4)
        except Exception:
            time.sleep(4)
    return i, None

out = {}
done = 0
t0 = time.time()
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = [ex.submit(post_batch, b) for b in batches]
    for fut in as_completed(futs):
        i, j = fut.result()
        done += 1
        if j is None:
            print(f"batch @{i} FAILED", flush=True); continue
        for rec in j:
            out[rec.get('input','').strip()] = rec
        if done % 20 == 0:
            el = time.time()-t0
            print(f"{done}/{len(batches)} batches, {len(out)} recs, {el:.0f}s", flush=True)
            with open('/task/data/vep_raw.json','w') as f:
                json.dump(out, f)

with open('/task/data/vep_raw.json','w') as f:
    json.dump(out, f)
print(f"DONE collected {len(out)} / {len(variants)} in {time.time()-t0:.0f}s", flush=True)
