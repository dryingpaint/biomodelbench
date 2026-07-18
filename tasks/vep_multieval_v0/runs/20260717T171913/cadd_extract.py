import pysam, pandas as pd, numpy as np, sys, time
from multiprocessing import Pool
URL='https://krishna.gs.washington.edu/download/CADD/v1.7/GRCh38/whole_genome_SNVs.tsv.gz'
def work(args):
    idx, rows = args  # rows: list of (chrom,pos,ref,alt)
    tb=pysam.TabixFile(URL)
    out={}
    for (c,p,r,a) in rows:
        raw=np.nan; phred=np.nan
        try:
            for line in tb.fetch(c, p-1, p):
                f=line.split('\t')
                if f[2]==r and f[3]==a:
                    raw=float(f[4]); phred=float(f[5]); break
        except Exception:
            pass
        out[(c,p,r,a)]=(raw,phred)
    tb.close()
    return out
if __name__=='__main__':
    df=pd.read_parquet('test.parquet')
    n=int(sys.argv[1]) if len(sys.argv)>1 else len(df)
    df=df.iloc[:n]
    rows=list(zip(df.chrom,df.pos,df.ref,df.alt))
    nproc=8
    chunks=[rows[i::nproc] for i in range(nproc)]
    t=time.time()
    with Pool(nproc) as pool:
        res=pool.map(work,[(i,ch) for i,ch in enumerate(chunks)])
    m={}
    for d in res: m.update(d)
    print(f'{len(rows)} variants in {time.time()-t:.1f}s')
    raw=[m[k][0] for k in rows]; phred=[m[k][1] for k in rows]
    print('missing raw:', np.isnan(raw).sum())
