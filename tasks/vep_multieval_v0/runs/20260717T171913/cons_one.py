import pybigtools, pandas as pd, numpy as np, time
df=pd.read_parquet('test.parquet').reset_index(drop=True)
df['ck']='chr'+df.chrom.astype(str)
b=pybigtools.open('hg38.phyloP470way.bw')
chroms=set(b.chroms().keys())
vals=np.full(len(df),np.nan)
t=time.time()
for ck,g in df.groupby('ck'):
    if ck not in chroms: continue
    for i,p in zip(g.index,g.pos):
        try: vals[i]=b.values(ck,int(p)-1,int(p),fillna=np.nan)[0]
        except Exception: pass
b.close()
df['phyloP470']=vals
df.drop(columns=['ck']).to_parquet('cons.parquet')
print(f'phyloP470 done {time.time()-t:.0f}s missing={np.isnan(vals).sum()}')
