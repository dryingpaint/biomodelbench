import requests, io, re, random, json, time
import pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor

random.seed(0)
base = "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/credible_set/"
r = requests.get(base, timeout=60)
parts = sorted(h for h in re.findall(r'href="([^"]+)"', r.text) if h.endswith('.parquet'))
print("parts:", len(parts), flush=True)

# positives: variant -> max pp (only keep pp>=0.5 to bound memory)
# negatives: reservoir sample of gwas-locus variants with pp<0.01
pos = {}
neg_reservoir = []
NEG_CAP = 400000
seen_neg = 0

def fetch(p):
    for attempt in range(4):
        try:
            b = requests.get(base + p, timeout=180).content
            return pd.read_parquet(io.BytesIO(b), columns=['studyType','locus'])
        except Exception as e:
            time.sleep(3)
    print("FAILED", p, flush=True)
    return None

def process(df):
    global seen_neg
    g = df[df.studyType == "gwas"]
    for loc in g.locus.values:
        if loc is None: continue
        for el in loc:
            pp = el.get('posteriorProbability')
            vid = el.get('variantId')
            if pp is None or vid is None: continue
            if pp >= 0.5:
                if vid not in pos or pp > pos[vid]:
                    pos[vid] = pp
            elif pp < 0.01:
                seen_neg += 1
                if len(neg_reservoir) < NEG_CAP:
                    neg_reservoir.append(vid)
                else:
                    j = random.randint(0, seen_neg-1)
                    if j < NEG_CAP:
                        neg_reservoir[j] = vid

t0=time.time()
with ThreadPoolExecutor(max_workers=8) as ex:
    for i, df in enumerate(ex.map(fetch, parts)):
        if df is not None:
            process(df)
        if (i+1) % 20 == 0:
            print(f"{i+1}/200 parts  pos(>=0.5)={len(pos)}  negseen={seen_neg}  {time.time()-t0:.0f}s", flush=True)

# finalize: positives pp>=0.9
pos_final = {v:p for v,p in pos.items() if p >= 0.9}
neg_set = set(neg_reservoir) - set(pos.keys())  # exclude any variant that ever had pp>=0.5
print("positives pp>=0.9:", len(pos_final), " negatives unique:", len(neg_set), flush=True)

def to_rows(vids, label, ppmap=None):
    rows=[]
    for v in vids:
        parts_v = v.split("_")
        if len(parts_v)!=4: continue
        c,p,ref,alt = parts_v
        if not p.isdigit(): continue
        if len(ref)!=1 or len(alt)!=1: continue  # SNVs only
        if ref not in "ACGT" or alt not in "ACGT": continue
        rows.append((c, int(p), ref, alt, label, ppmap[v] if ppmap else 0.0))
    return rows

rows = to_rows(pos_final.keys(), 1, pos_final) + to_rows(neg_set, 0)
tr = pd.DataFrame(rows, columns=['chrom','pos','ref','alt','label','pp'])
tr = tr[tr.chrom.isin([str(i) for i in range(1,23)])].reset_index(drop=True)
tr = tr.drop_duplicates(['chrom','pos','ref','alt'])
print("train rows (SNV, chr1-22):", len(tr), "pos:", int(tr.label.sum()), "neg:", int((tr.label==0).sum()), flush=True)
tr.to_parquet("data/ot_labels.parquet")
print("saved data/ot_labels.parquet", flush=True)
