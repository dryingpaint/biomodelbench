import pybigtools, pandas as pd, numpy as np, time, sys
TRACKS={
 'phyloP470':'hg38.phyloP470way.bw',
 'phastCons470':'hg38.phastCons470way.bw',
 'phyloP100':'hg38.phyloP100way.bw',
 'phastCons100':'hg38.phastCons100way.bw',
}
if __name__=='__main__':
    df=pd.read_parquet('test.parquet').reset_index(drop=True)
    df['ck']='chr'+df.chrom.astype(str)
    for name,fn in TRACKS.items():
        import os
        if not os.path.exists(fn):
            print('SKIP missing',fn); continue
        t=time.time()
        b=pybigtools.open(fn)
        chroms=set(b.chroms().keys())
        vals=np.full(len(df),np.nan)
        # group by chrom, query sorted
        for ck,g in df.groupby('ck'):
            if ck not in chroms: continue
            for i,p in zip(g.index, g.pos):
                try:
                    v=b.values(ck,int(p)-1,int(p),fillna=np.nan)
                    vals[i]=v[0]
                except Exception:
                    pass
        b.close()
        df[name]=vals
        print(f'{name} done {time.time()-t:.0f}s missing={np.isnan(vals).sum()}')
    df.drop(columns=['ck']).to_parquet('cons.parquet')
    print('saved cons.parquet')
