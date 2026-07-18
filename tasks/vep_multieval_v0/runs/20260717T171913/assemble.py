import pandas as pd, numpy as np
from scipy.stats import rankdata

def rank01(x):
    x=np.asarray(x,float)
    r=np.full(len(x),np.nan)
    m=~np.isnan(x)
    if m.sum()==0: return np.zeros(len(x))
    r[m]=(rankdata(x[m])-1)/(m.sum()-1 if m.sum()>1 else 1)
    # impute missing with median rank 0.5
    r[~m]=0.5
    return r

def main():
    base=pd.read_parquet('test.parquet').reset_index(drop=True)
    key=['chrom','pos','ref','alt']
    df=base.copy()
    for f in ['cadd.parquet','cons.parquet']:
        import os
        if os.path.exists(f):
            d=pd.read_parquet(f)
            newcols=[c for c in d.columns if c not in key]
            df=df.merge(d[key+newcols],on=key,how='left')
    print('columns:',[c for c in df.columns if c not in key])
    print(df[[c for c in df.columns if c not in key]].describe())
    # feature list present
    feats=[c for c in ['cadd_raw','cadd_phred','phyloP470','phastCons470','phyloP100','phastCons100'] if c in df.columns]
    print('using feats',feats)
    # baseline: rank-average of CADD_raw + phyloP470 (balanced transfer)
    comps=[]
    weights={'cadd_raw':1.0,'phyloP470':1.0,'phastCons470':0.5,'phyloP100':0.5}
    for f in feats:
        if f in weights:
            comps.append(weights[f]*rank01(df[f].values))
    score=np.sum(comps,axis=0)/sum(weights[f] for f in feats if f in weights)
    score=rank01(score)  # final rank-normalize to [0,1]
    out=base.copy(); out['score']=score
    out.to_parquet('answer.parquet')
    print('wrote answer.parquet', out.score.describe())

if __name__=='__main__': main()
