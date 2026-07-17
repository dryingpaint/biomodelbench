import requests, json, os, time
import pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

CKPT="/task/cadd_ckpt.jsonl"
OUT="/task/cadd_features.parquet"
df=pd.read_parquet("/task/test.parquet")
df["key"]=df.chrom+":"+df.pos.astype(str)+"_"+df.ref+"_"+df.alt

done={}
if os.path.exists(CKPT):
    for line in open(CKPT):
        try:
            o=json.loads(line)
            # only count as done if we have a real value (retry NaNs)
            if o.get("phred") is not None and o["phred"]==o["phred"]:
                done[o["k"]]=o
        except: pass
print("resume",len(done),flush=True)
todo=df[~df.key.isin(done.keys())].reset_index(drop=True)
print("todo",len(todo),flush=True)

BASE="https://cadd.gs.washington.edu/api/v1.0/GRCh38-v1.7/"
sess=requests.Session()
ck=open(CKPT,"a")
import threading
lock=threading.Lock()

def fetch(row):
    c,p,r,a,k=row
    url=f"{BASE}{c}:{p}_{r}_{a}"
    for attempt in range(5):
        try:
            resp=sess.get(url,timeout=30)
            if resp.status_code==200:
                j=resp.json()
                if j:
                    return dict(k=k,phred=float(j[0]["PHRED"]),raw=float(j[0]["RawScore"]))
                else:
                    time.sleep(1.5+attempt)  # empty is transient rate-limit; retry
            elif resp.status_code in (429,503):
                time.sleep(2+attempt*2)
            else:
                time.sleep(1)
        except Exception:
            time.sleep(1.5)
    return dict(k=k,phred=np.nan,raw=np.nan)

rows=list(zip(todo.chrom,todo.pos,todo.ref,todo.alt,todo.key))
cnt=0
with ThreadPoolExecutor(max_workers=12) as ex:
    futs=[ex.submit(fetch,r) for r in rows]
    for fut in as_completed(futs):
        o=fut.result()
        with lock:
            ck.write(json.dumps(o)+"\n"); ck.flush()
            cnt+=1
            if cnt%2000==0: print("done",cnt,"/",len(rows),flush=True)
ck.close()
print("fetch complete",flush=True)

done={}
for line in open(CKPT):
    try:
        o=json.loads(line)
        if o.get("phred") is not None and o["phred"]==o["phred"]:
            done[o["k"]]=o
    except: pass
rows=[]
for c,p,r,a,k in zip(df.chrom,df.pos,df.ref,df.alt,df.key):
    o=done.get(k,{})
    rows.append(dict(chrom=c,pos=p,ref=r,alt=a,cadd_phred=o.get("phred",np.nan),cadd_raw=o.get("raw",np.nan)))
cf=pd.DataFrame(rows)
cf.to_parquet(OUT)
print("saved",OUT,cf.shape,"nonnull",cf.cadd_phred.notna().sum(),flush=True)
