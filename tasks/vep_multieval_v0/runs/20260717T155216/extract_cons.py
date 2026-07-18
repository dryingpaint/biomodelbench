import pyBigWig, numpy as np, pandas as pd, sys, time

df = pd.read_parquet('/task/test.parquet')
df['chrom'] = df['chrom'].astype(str)
N = len(df)

TRACKS = {
 'phyloP241m': '/task/cons/phyloP241m.bw',
 'phyloP470':  '/task/cons/phyloP470.bw',
 'phyloP100':  '/task/cons/phyloP100.bw',
 'phastCons100':'/task/cons/phastCons100.bw',
}

def chrom_name(bw, c):
    ch = bw.chroms()
    if ('chr'+c) in ch: return 'chr'+c
    if c in ch: return c
    return None

feat = pd.DataFrame({'chrom':df['chrom'],'pos':df['pos'],'ref':df['ref'],'alt':df['alt']})

for name, path in TRACKS.items():
    t=time.time()
    try:
        bw = pyBigWig.open(path)
    except Exception as e:
        print(f"{name}: cannot open {e}", flush=True); continue
    csample = list(bw.chroms().keys())[:3]
    print(f"{name}: chroms sample {csample}", flush=True)
    pt = np.full(N, np.nan)
    w5 = np.full(N, np.nan)   # mean over +-5
    m5 = np.full(N, np.nan)   # max over +-5
    w25 = np.full(N, np.nan)  # mean over +-25
    # group by chrom to reuse chrom-name lookup
    for c, sub in df.groupby('chrom'):
        cn = chrom_name(bw, c)
        if cn is None:
            print(f"  {name}: chrom {c} not found", flush=True); continue
        clen = bw.chroms()[cn]
        for idx, pos in zip(sub.index, sub['pos'].values):
            p0 = pos-1  # 0-based
            if p0<0 or p0>=clen: continue
            try:
                v = bw.values(cn, p0, p0+1)
                pt[idx] = v[0]
            except Exception:
                pass
            s = max(0,p0-5); e = min(clen,p0+6)
            try:
                arr = np.array(bw.values(cn, s, e), dtype=float)
                arr = arr[~np.isnan(arr)]
                if arr.size:
                    w5[idx]=arr.mean(); m5[idx]=arr.max()
            except Exception:
                pass
            s2 = max(0,p0-25); e2 = min(clen,p0+26)
            try:
                arr2 = np.array(bw.values(cn, s2, e2), dtype=float)
                arr2 = arr2[~np.isnan(arr2)]
                if arr2.size: w25[idx]=arr2.mean()
            except Exception:
                pass
    feat[name+'_pt']=pt
    feat[name+'_w5mean']=w5
    feat[name+'_w5max']=m5
    feat[name+'_w25mean']=w25
    bw.close()
    print(f"{name}: done in {time.time()-t:.0f}s, pt non-nan={np.isfinite(pt).sum()}", flush=True)

feat.to_parquet('/task/data/cons_features.parquet')
print("saved cons_features.parquet", feat.shape, flush=True)
