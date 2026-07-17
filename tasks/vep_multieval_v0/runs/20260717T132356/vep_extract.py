import requests, json, time, os, sys
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed

OUT = "/task/vep_features.parquet"
CKPT = "/task/vep_ckpt.jsonl"
df = pd.read_parquet("/task/test.parquet")
df["key"] = df.chrom + " " + df.pos.astype(str) + " " + df.ref + " " + df.alt

# consequence severity ordinal (Ensembl impact ranking, higher = more severe)
SEV = {
 "transcript_ablation":10,"splice_acceptor_variant":9.5,"splice_donor_variant":9.5,
 "stop_gained":9,"frameshift_variant":9,"stop_lost":8.5,"start_lost":8.5,
 "transcript_amplification":8,"feature_elongation":7.9,"feature_truncation":7.9,
 "inframe_insertion":7,"inframe_deletion":7,"missense_variant":6.5,
 "protein_altering_variant":6,"splice_donor_5th_base_variant":6,
 "splice_region_variant":5.5,"splice_donor_region_variant":5.4,
 "splice_polypyrimidine_tract_variant":5.3,"incomplete_terminal_codon_variant":5,
 "start_retained_variant":4.5,"stop_retained_variant":4.5,"synonymous_variant":4,
 "coding_sequence_variant":4,"mature_miRNA_variant":4,
 "5_prime_UTR_variant":3.5,"3_prime_UTR_variant":3.4,
 "non_coding_transcript_exon_variant":3,"intron_variant":2.5,
 "NMD_transcript_variant":2.4,"non_coding_transcript_variant":2.3,
 "upstream_gene_variant":2,"downstream_gene_variant":2,
 "TFBS_ablation":3.2,"TFBS_amplification":3.1,"TF_binding_site_variant":3.0,
 "regulatory_region_ablation":3.2,"regulatory_region_amplification":3.1,
 "regulatory_region_variant":2.8,"feature_variant":1.5,
 "intergenic_variant":1,"sequence_variant":1,
}

H = {"Content-Type":"application/json","Accept":"application/json"}
URL = "https://rest.ensembl.org/vep/human/region"

def parse(rec):
    msc = rec.get("most_severe_consequence","")
    sev = SEV.get(msc, 1)
    sift_scores=[]; poly_scores=[]
    is_coding=is_missense=is_lof=is_splice=is_syn=is_utr=is_reg=0
    tcs = rec.get("transcript_consequences",[]) or []
    for tc in tcs:
        if "sift_score" in tc: sift_scores.append(tc["sift_score"])
        if "polyphen_score" in tc: poly_scores.append(tc["polyphen_score"])
        cts = tc.get("consequence_terms",[])
        for ct in cts:
            if ct in ("missense_variant","inframe_insertion","inframe_deletion","protein_altering_variant"): is_missense=1; is_coding=1
            if ct in ("stop_gained","frameshift_variant","stop_lost","start_lost","splice_acceptor_variant","splice_donor_variant"): is_lof=1; is_coding=1
            if "splice" in ct: is_splice=1
            if ct=="synonymous_variant": is_syn=1; is_coding=1
            if "UTR" in ct: is_utr=1
            if ct=="coding_sequence_variant": is_coding=1
    if rec.get("regulatory_feature_consequences") or rec.get("motif_feature_consequences"): is_reg=1
    # SIFT: lower=more damaging -> damaging = 1-sift ; take min sift (most damaging)
    sift = min(sift_scores) if sift_scores else np.nan
    poly = max(poly_scores) if poly_scores else np.nan
    return dict(msc=msc, sev=sev, sift=sift, poly=poly,
                is_coding=is_coding,is_missense=is_missense,is_lof=is_lof,
                is_splice=is_splice,is_syn=is_syn,is_utr=is_utr,is_reg=is_reg)

# load checkpoint
done = {}
if os.path.exists(CKPT):
    for line in open(CKPT):
        try:
            o=json.loads(line); done[o["input"]]=o
        except: pass
print(f"resume: {len(done)} done", flush=True)

todo = df[~df.key.isin(done.keys())].reset_index(drop=True)
print(f"todo: {len(todo)}", flush=True)

BATCH=190
batches=[todo.iloc[i:i+BATCH] for i in range(0,len(todo),BATCH)]

ck = open(CKPT,"a")
lock_lines=[]

def do_batch(bdf):
    variants=[f"{c} {p} . {r} {a} . . ." for c,p,r,a in zip(bdf.chrom,bdf.pos,bdf.ref,bdf.alt)]
    payload=json.dumps({"variants":variants})
    for attempt in range(6):
        try:
            r=requests.post(URL,headers=H,data=payload,timeout=120)
            if r.status_code==200:
                out=[]
                for rec in r.json():
                    p=parse(rec)
                    p["input"]=rec.get("input")
                    out.append(p)
                return out
            elif r.status_code==429:
                wait=float(r.headers.get("Retry-After","2"))
                time.sleep(wait+1)
            else:
                time.sleep(3)
        except Exception as e:
            time.sleep(3)
    return []

written=0
with ThreadPoolExecutor(max_workers=6) as ex:
    futs={ex.submit(do_batch,b):i for i,b in enumerate(batches)}
    for fut in as_completed(futs):
        res=fut.result()
        for o in res:
            ck.write(json.dumps(o)+"\n")
        ck.flush()
        written+=len(res)
        if written % 2000 < BATCH:
            print(f"written {written}/{len(todo)}", flush=True)
ck.close()
print("VEP fetch complete", flush=True)

# assemble
done={}
for line in open(CKPT):
    try:
        o=json.loads(line);
        if o.get("input"): done[o["input"]]=o
    except: pass
rows=[]
for c,p,r,a,k in zip(df.chrom,df.pos,df.ref,df.alt,df.key):
    o=done.get(k,{})
    rows.append(dict(chrom=c,pos=p,ref=r,alt=a,
        sev=o.get("sev",1),sift=o.get("sift",np.nan),poly=o.get("poly",np.nan),
        is_coding=o.get("is_coding",0),is_missense=o.get("is_missense",0),
        is_lof=o.get("is_lof",0),is_splice=o.get("is_splice",0),
        is_syn=o.get("is_syn",0),is_utr=o.get("is_utr",0),is_reg=o.get("is_reg",0),
        msc=o.get("msc","")))
vf=pd.DataFrame(rows)
vf.to_parquet(OUT)
print("saved", OUT, vf.shape, "missing:", (vf.msc=="").sum(), flush=True)
