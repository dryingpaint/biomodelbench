import json, numpy as np, pandas as pd

df = pd.read_parquet('/task/test.parquet'); df['chrom']=df['chrom'].astype(str)
keys = [f"{r.chrom} {r.pos} . {r.ref} {r.alt} . . ." for r in df.itertuples()]
vep = json.load(open('/task/data/vep_raw.json'))

# impact severity of consequence classes (mechanistic, not label-derived)
HIGH = {'transcript_ablation','splice_acceptor_variant','splice_donor_variant',
        'stop_gained','frameshift_variant','stop_lost','start_lost',
        'transcript_amplification'}
MODER = {'inframe_insertion','inframe_deletion','missense_variant',
         'protein_altering_variant','splice_region_variant',
         'splice_donor_5th_base_variant','splice_donor_region_variant',
         'splice_polypyrimidine_tract_variant'}

def most_severe_sift(rec):
    sift=np.nan
    for tc in rec.get('transcript_consequences',[]):
        s=tc.get('sift_score')
        if s is not None:
            # sift low = damaging; keep the min (most damaging)
            sift = s if (np.isnan(sift) or s<sift) else sift
    return sift

rows=[]
for k in keys:
    rec=vep.get(k)
    if rec is None:
        rows.append((None,'',0,np.nan)); continue
    msc=rec.get('most_severe_consequence','')
    if msc in HIGH: cls='HIGH'
    elif msc=='missense_variant': cls='MISSENSE'
    elif msc in MODER: cls='MODER'
    else: cls='OTHER'
    sift=most_severe_sift(rec)
    rows.append((msc,cls,1 if cls in ('HIGH','MISSENSE','MODER') else 0, sift))

out=pd.DataFrame(rows, columns=['most_severe','impact_cls','coding','sift_score'])
out=pd.concat([df.reset_index(drop=True), out], axis=1)
out.to_parquet('/task/data/vep_features.parquet')
print(out['impact_cls'].value_counts())
print('sift non-nan', out['sift_score'].notna().sum())
print('saved vep_features.parquet', out.shape)
