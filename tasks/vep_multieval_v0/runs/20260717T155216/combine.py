import numpy as np, pandas as pd

def rank01(x):
    """Empirical-CDF rank normalize to (0,1), NaN-safe (NaN stays NaN)."""
    x=np.asarray(x, dtype=float)
    out=np.full(x.shape, np.nan)
    m=np.isfinite(x)
    if m.sum()==0: return out
    r=pd.Series(x[m]).rank(method='average').values
    out[m]=(r-0.5)/m.sum()
    return out

df = pd.read_parquet('/task/test.parquet'); df['chrom']=df['chrom'].astype(str)
cons = pd.read_parquet('/task/data/cons_features.parquet')
vep  = pd.read_parquet('/task/data/vep_features.parquet')
esm  = pd.read_parquet('/task/data/esm_scores.parquet')

N=len(df)
# ---- Conservation composite ----
def track_value(name):
    pt=cons[name+'_pt'].values.astype(float)
    w5=cons[name+'_w5mean'].values.astype(float)
    w25=cons[name+'_w25mean'].values.astype(float)
    v=pt.copy()
    v=np.where(np.isfinite(v), v, w5)
    v=np.where(np.isfinite(v), v, w25)
    return v

tracks={'phyloP241m':0.35,'phyloP470':0.30,'phastCons100':0.20,'phyloP100':0.15}
cons_rank=np.zeros(N); wsum=0.0
for name,w in tracks.items():
    if name+'_pt' not in cons.columns:
        print('missing track',name); continue
    v=track_value(name)
    r=rank01(v)
    r=np.where(np.isfinite(r), r, 0.5)  # neutral for missing
    cons_rank += w*r; wsum+=w
cons_rank/=wsum
print('cons_rank ready; wsum',wsum)

# ---- ESM ----
esm_llr=esm['esm_llr'].values.astype(float)      # higher = more damaging
esm_rank=rank01(esm_llr)                          # NaN where non-missense

# ---- SIFT (lower=damaging) -> damage rank ----
sift=vep['sift_score'].values.astype(float)
sift_damage=rank01(-sift)                         # higher = more damaging

# ---- consequence class ----
cls=vep['impact_cls'].values

raw=np.array(cons_rank, dtype=float)
for i in range(N):
    c=cls[i]
    if c=='HIGH':
        raw[i]=0.90+0.10*cons_rank[i]
    elif c=='MISSENSE':
        e=esm_rank[i]; s=sift_damage[i]
        if np.isfinite(e) and np.isfinite(s):
            raw[i]=0.35*cons_rank[i]+0.50*e+0.15*s
        elif np.isfinite(e):
            raw[i]=0.40*cons_rank[i]+0.60*e
        elif np.isfinite(s):
            raw[i]=0.50*cons_rank[i]+0.50*s
        else:
            raw[i]=cons_rank[i]
    else:
        raw[i]=cons_rank[i]

raw=np.clip(raw,0,1)
# final monotone map to (0,1)
final=rank01(raw)
final=np.where(np.isfinite(final), final, 0.5)

ans=pd.DataFrame({'chrom':df.chrom,'pos':df.pos,'ref':df.ref,'alt':df.alt,'score':final})
assert ans['score'].between(0,1).all()
assert len(ans)==N
ans.to_parquet('/task/answer.parquet')
print('saved answer.parquet', ans.shape)
print(ans['score'].describe())
print('\nby class mean score:')
for c in ['HIGH','MISSENSE','MODER','OTHER']:
    mask=cls==c
    if mask.sum(): print(f'  {c}: n={mask.sum()} mean={final[mask].mean():.3f}')
