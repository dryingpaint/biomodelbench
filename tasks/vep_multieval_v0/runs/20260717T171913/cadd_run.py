import pysam, pandas as pd, numpy as np, time, sys
from multiprocessing import Pool
URL='https://krishna.gs.washington.edu/download/CADD/v1.7/GRCh38/whole_genome_SNVs.tsv.gz'
def work(rows):
    tb=pysam.TabixFile(URL); out=[]
    for (i,c,p,r,a) in rows:
        raw=np.nan; phred=np.nan
        for _t in range(4):
            try:
                for line in tb.fetch(c,p-1,p):
                    f=line.split('\t')
                    if f[2]==r and f[3]==a: raw=float(f[4]); phred=float(f[5]); break
                break
            except Exception:
                time.sleep(1.5)
        out.append((i,raw,phred))
    tb.close(); return out
if __name__=='__main__':
    df=pd.read_parquet('test.parquet').reset_index(drop=True)
    rows=[(i,c,p,r,a) for i,(c,p,r,a) in enumerate(zip(df.chrom,df.pos,df.ref,df.alt))]
    raw=np.full(len(df),np.nan); phred=np.full(len(df),np.nan)
    nproc=16; BATCH=4000; t0=time.time()
    with Pool(nproc) as pool:
        for start in range(0,len(rows),BATCH):
            batch=rows[start:start+BATCH]
            chunks=[batch[i::nproc] for i in range(nproc)]
            res=pool.map(work,chunks)
            for ch in res:
                for (i,rw,ph) in ch: raw[i]=rw; phred[i]=ph
            df['cadd_raw']=raw; df['cadd_phred']=phred
            df.to_parquet('cadd.parquet')
            done=start+len(batch); miss=np.isnan(raw[:done]).sum()
            print(f'{done}/{len(rows)} {time.time()-t0:.0f}s miss={miss}',flush=True)
    print('CADD DONE',flush=True)
