import pysam, pandas as pd, numpy as np, time
from multiprocessing import Pool
URL='https://krishna.gs.washington.edu/download/CADD/v1.7/GRCh38/whole_genome_SNVs.tsv.gz'
def work(rows):
    tb=pysam.TabixFile(URL); out=[]
    for (i,c,p,r,a) in rows:
        raw=np.nan; phred=np.nan
        for _try in range(3):
            try:
                for line in tb.fetch(c, p-1, p):
                    f=line.split('\t')
                    if f[2]==r and f[3]==a:
                        raw=float(f[4]); phred=float(f[5]); break
                break
            except Exception:
                time.sleep(1.0)
        out.append((i,raw,phred))
    tb.close(); return out
if __name__=='__main__':
    df=pd.read_parquet('test.parquet').reset_index(drop=True)
    rows=[(i,c,p,r,a) for i,(c,p,r,a) in enumerate(zip(df.chrom,df.pos,df.ref,df.alt))]
    nproc=24
    chunks=[rows[i::nproc] for i in range(nproc)]
    t=time.time()
    with Pool(nproc) as pool:
        res=pool.map(work,chunks)
    raw=np.full(len(df),np.nan); phred=np.full(len(df),np.nan)
    for chunk in res:
        for (i,rw,ph) in chunk: raw[i]=rw; phred[i]=ph
    df['cadd_raw']=raw; df['cadd_phred']=phred
    df.to_parquet('cadd.parquet')
    print(f'DONE {len(df)} in {time.time()-t:.0f}s missing={np.isnan(raw).sum()}')
