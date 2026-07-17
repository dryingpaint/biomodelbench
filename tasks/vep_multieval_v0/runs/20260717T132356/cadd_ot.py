import requests, json, os, time, threading
import pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
d=pd.read_parquet('/task/cons_ot.parquet')
pos=d[d.label==1].sample(n=2000,random_state=1)
neg=d[d.label==0].sample(n=2000,random_state=1)
sub=pd.concat([pos,neg]).reset_index(drop=True)
sub.to_parquet('/task/ot_sub.parquet')
BASE="https://cadd.gs.washington.edu/api/v1.0/GRCh38-v1.7/"
sess=requests.Session()
def fetch(row):
    c,p,r,a=row
    url=f"{BASE}{c}:{p}_{r}_{a}"
    for att in range(6):
        try:
            resp=sess.get(url,timeout=30)
            if resp.status_code==200:
                j=resp.json()
                if j: return (c,p,r,a,float(j[0]["PHRED"]))
                time.sleep(1.5+att)
            else: time.sleep(1.5)
        except: time.sleep(1.5)
    return (c,p,r,a,np.nan)
rows=list(zip(sub.chrom,sub.pos,sub.ref,sub.alt))
res={}
with ThreadPoolExecutor(max_workers=12) as ex:
    for f in as_completed([ex.submit(fetch,r) for r in rows]):
        c,p,r,a,ph=f.result(); res[(c,int(p),r,a)]=ph
sub['cadd']=[res.get((c,int(p),r,a),np.nan) for c,p,r,a in zip(sub.chrom,sub.pos,sub.ref,sub.alt)]
sub.to_parquet('/task/ot_sub.parquet')
print("done, cadd nonnull", sub.cadd.notna().sum())
