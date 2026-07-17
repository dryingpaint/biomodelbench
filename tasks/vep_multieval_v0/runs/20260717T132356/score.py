import pandas as pd, numpy as np

def pr(s):
    """percentile rank in [0,1], NaN-aware (NaN -> 0)."""
    s=pd.Series(s).astype(float)
    r=s.rank(pct=True, na_option='keep')
    return r.fillna(0.0).values

def lowimpute(s, q=0.05):
    s=pd.Series(s).astype(float)
    return s.fillna(s.quantile(q)).values

def build_features(cons, vep, cadd):
    m=cons.merge(vep, on=['chrom','pos','ref','alt'], how='left', suffixes=('','_v'))
    m=m.merge(cadd[['chrom','pos','ref','alt','cadd_phred']], on=['chrom','pos','ref','alt'], how='left')
    return m

def composite(m, w_cons=0.40, w_cadd=0.35, w_code=0.25):
    # conservation composite (mammalian + vertebrate), low-impute missing
    c241v=lowimpute(m['cactus241m_v']); c241m=lowimpute(m['cactus241m_max'])
    p100v=lowimpute(m['phyloP100_v']); p100m=lowimpute(m['phyloP100_max'])
    pc=lowimpute(m['phastCons100_max'])
    CONS = (0.30*pr(c241m)+0.25*pr(c241v)+0.25*pr(p100v)+0.10*pr(p100m)+0.10*pr(pc))
    # CADD integrated
    CADD = pr(lowimpute(m['cadd_phred'], q=0.5))
    # coding damage: severity + missense damage (SIFT/PolyPhen) + LoF
    sev = m['sev'].fillna(1.0).values
    poly = m['poly'].fillna(0.0).values          # 0..1 damaging
    sift = m['sift'].values
    sift_dmg = np.where(np.isnan(sift), 0.0, 1.0-sift)
    miss_dmg = np.maximum(poly, sift_dmg)
    is_lof = m['is_lof'].fillna(0).values
    CODE = 0.5*pr(sev) + 0.5*np.maximum(miss_dmg, is_lof*1.0)
    raw = w_cons*CONS + w_cadd*CADD + w_code*CODE
    # final rank-normalize to [0,1]
    score = pd.Series(raw).rank(pct=True).values
    return score, dict(CONS=CONS,CADD=CADD,CODE=CODE)

if __name__=="__main__":
    cons=pd.read_parquet('/task/cons_test.parquet')
    vep=pd.read_parquet('/task/vep_features.parquet')
    cadd=pd.read_parquet('/task/cadd_features.parquet')
    m=build_features(cons,vep,cadd)
    score,comp=composite(m)
    out=m[['chrom','pos','ref','alt']].copy()
    out['score']=score
    out.to_parquet('/task/answer.parquet')
    print("wrote answer.parquet", out.shape)
    print(out.score.describe())
