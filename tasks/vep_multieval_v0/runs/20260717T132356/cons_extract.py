import pyBigWig, pandas as pd, numpy as np, sys
from concurrent.futures import ThreadPoolExecutor

TRACKS={'cactus241m':'/tmp/bw/cactus241m.bw','phyloP100':'/tmp/bw/phyloP100.bw','phastCons100':'/tmp/bw/phastCons100.bw'}
WIN=7

def extract(df, outpath):
    df=df.reset_index(drop=True)
    df["ci"]=range(len(df))
    dfs=df.sort_values(["chrom","pos"]).reset_index(drop=True)
    n=len(dfs)
    feats={}
    for tname,tpath in TRACKS.items():
        vals=np.full(n,np.nan); wmax=np.full(n,np.nan); wmean=np.full(n,np.nan)
        NT=8
        idxchunks=[range(i,n,NT) for i in range(NT)]
        def work(idxs):
            bw=pyBigWig.open(tpath)
            for i in idxs:
                c='chr'+dfs.chrom[i]; p=int(dfs.pos[i])  # 1-based
                try:
                    v=bw.values(c,p-1,p)[0]
                    vals[i]=v
                except: pass
                try:
                    w=bw.values(c,max(0,p-1-WIN),p+WIN)
                    w=np.array(w,dtype=float); w=w[~np.isnan(w)]
                    if len(w): wmax[i]=np.nanmax(w); wmean[i]=np.nanmean(w)
                except: pass
            bw.close()
        with ThreadPoolExecutor(max_workers=NT) as ex:
            list(ex.map(work,idxchunks))
        feats[tname+"_v"]=vals; feats[tname+"_max"]=wmax; feats[tname+"_mean"]=wmean
        print(f"{tname} done, non-nan center={np.isfinite(vals).sum()}/{n}", flush=True)
    F=pd.DataFrame(feats)
    F["ci"]=dfs["ci"].values
    F=F.sort_values("ci").reset_index(drop=True)
    out=df.sort_values("ci").reset_index(drop=True).drop(columns=["ci"]).join(F.drop(columns=["ci"]))
    out.to_parquet(outpath)
    print("saved",outpath,out.shape, flush=True)
    return out

if __name__=="__main__":
    which=sys.argv[1]
    if which=="test":
        df=pd.read_parquet("/task/test.parquet")[["chrom","pos","ref","alt"]]
        extract(df,"/task/cons_test.parquet")
    elif which=="ot":
        df=pd.read_parquet("/task/ot_labels.parquet")
        # subsample negatives to 5x positives for speed
        pos=df[df.label==1]; neg=df[df.label==0]
        neg=neg.sample(n=min(len(neg),5*len(pos)),random_state=0)
        sub=pd.concat([pos,neg],ignore_index=True)
        extract(sub,"/task/cons_ot.parquet")
