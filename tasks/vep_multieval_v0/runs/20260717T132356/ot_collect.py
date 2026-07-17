import requests, re, io, os
import pandas as pd, numpy as np

base='https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/latest/output/credible_set/'
r=requests.get(base,timeout=30)
parts=[f for f in re.findall(r'href="([^"]+)"', r.text) if f.endswith('.parquet')]
NPARTS=25
pos_rows=[]; neg_rows=[]
for i,p in enumerate(parts[:NPARTS]):
    try:
        content=requests.get(base+p,timeout=90).content
        d=pd.read_parquet(io.BytesIO(content))
    except Exception as e:
        print("skip",p,e); continue
    d=d[d.studyType=="gwas"]
    for loc in d.locus:
        if loc is None: continue
        for v in loc:
            vid=v.get("variantId"); pp=v.get("posteriorProbability")
            if vid is None or pp is None: continue
            parts_v=vid.split("_")
            if len(parts_v)!=4: continue
            c,posn,ref,alt=parts_v
            if len(ref)!=1 or len(alt)!=1: continue  # SNVs
            rec=(c,int(posn),ref,alt,float(pp))
            if pp>=0.9: pos_rows.append(rec)
            elif pp<0.01: neg_rows.append(rec)
    print(f"part {i}: pos={len(pos_rows)} neg={len(neg_rows)}", flush=True)

P=pd.DataFrame(pos_rows,columns=["chrom","pos","ref","alt","pp"]).drop_duplicates(["chrom","pos","ref","alt"])
N=pd.DataFrame(neg_rows,columns=["chrom","pos","ref","alt","pp"]).drop_duplicates(["chrom","pos","ref","alt"])
# remove negs that are also positives
N=N[~N.set_index(["chrom","pos","ref","alt"]).index.isin(P.set_index(["chrom","pos","ref","alt"]).index)]
P["label"]=1; N["label"]=0
allv=pd.concat([P,N],ignore_index=True)
allv.to_parquet("/task/ot_labels.parquet")
print("positives",len(P),"negatives",len(N))
