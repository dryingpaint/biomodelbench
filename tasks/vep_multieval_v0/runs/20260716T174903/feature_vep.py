import requests, json, time, sys
import pandas as pd, numpy as np
from concurrent.futures import ThreadPoolExecutor
import threading

# Ensembl consequence severity ranking (higher = more severe)
SEV = ["intergenic_variant","downstream_gene_variant","upstream_gene_variant",
 "intron_variant","non_coding_transcript_variant","non_coding_transcript_exon_variant",
 "3_prime_UTR_variant","5_prime_UTR_variant","synonymous_variant",
 "mature_miRNA_variant","coding_sequence_variant","stop_retained_variant",
 "start_retained_variant","incomplete_terminal_codon_variant","protein_altering_variant",
 "regulatory_region_variant","TF_binding_site_variant","splice_region_variant",
 "splice_donor_5th_base_variant","splice_polypyrimidine_tract_variant","splice_donor_region_variant",
 "inframe_deletion","inframe_insertion","missense_variant","transcript_amplification",
 "start_lost","stop_lost","frameshift_variant","stop_gained",
 "splice_acceptor_variant","splice_donor_variant","transcript_ablation"]
SEVRANK = {c:i for i,c in enumerate(SEV)}

LOF = {"stop_gained","frameshift_variant","splice_acceptor_variant","splice_donor_variant",
       "start_lost","stop_lost","transcript_ablation"}
SPLICE = {"splice_region_variant","splice_donor_5th_base_variant","splice_polypyrimidine_tract_variant",
          "splice_donor_region_variant","splice_acceptor_variant","splice_donor_variant"}

URL = "https://rest.ensembl.org/vep/human/region"
HEAD = {"Content-Type":"application/json","Accept":"application/json"}
_lock = threading.Lock()

def vep_batch(batch):
    # batch: list of (idx, chrom, pos, ref, alt)
    variants = [f"{c} {p} {i} {r} {a} . . ." for (i,c,p,r,a) in batch]
    for attempt in range(6):
        try:
            r = requests.post(URL, headers=HEAD, data=json.dumps({"variants":variants}), timeout=90)
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", 2)); time.sleep(wait+0.5); continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            time.sleep(2+attempt)
    print("VEP FAILED batch len", len(batch), flush=True)
    return []

def parse_one(res):
    msc = res.get("most_severe_consequence","intergenic_variant")
    out = {"most_severe": msc,
           "sev": SEVRANK.get(msc, 0),
           "is_lof": int(msc in LOF),
           "is_missense": int(msc=="missense_variant"),
           "is_synonymous": int(msc=="synonymous_variant"),
           "is_splice": int(msc in SPLICE),
           "is_utr": int("UTR" in msc),
           "is_coding": 0, "is_regulatory": int("regulat" in msc or "TF_binding" in msc),
           "is_intron": int(msc=="intron_variant"),
           "sift_score": np.nan, "polyphen_score": np.nan,
           "gene_id": None, "transcript_id": None, "protein_start": np.nan,
           "aa_ref": None, "aa_alt": None, "loeuf_gene": None}
    tcs = res.get("transcript_consequences") or []
    sift=[]; poly=[]; best=None; best_sev=-1
    for tc in tcs:
        if tc.get("biotype")!="protein_coding":
            continue
        out["is_coding"]=1
        if tc.get("sift_score") is not None: sift.append(tc["sift_score"])
        if tc.get("polyphen_score") is not None: poly.append(tc["polyphen_score"])
        terms = tc.get("consequence_terms",[])
        tsev = max((SEVRANK.get(t,0) for t in terms), default=0)
        # prefer canonical transcript for representative gene/protein info
        rank = tsev + (1000 if tc.get("canonical") else 0)
        if rank > best_sev:
            best_sev = rank; best = tc
    if sift: out["sift_score"] = float(np.min(sift))
    if poly: out["polyphen_score"] = float(np.max(poly))
    if best is not None:
        out["gene_id"] = best.get("gene_id")
        out["transcript_id"] = best.get("transcript_id")
        out["loeuf_gene"] = best.get("gene_id")
        ps = best.get("protein_start")
        aa = best.get("amino_acids")
        if ps is not None and aa and "/" in aa:
            out["protein_start"] = ps
            r_,a_ = aa.split("/")[:2]
            out["aa_ref"]=r_; out["aa_alt"]=a_
    return out

def run(df, out_path, workers=6, bs=200):
    df = df.reset_index(drop=True)
    batches=[]
    for s in range(0, len(df), bs):
        sub = df.iloc[s:s+bs]
        batches.append([(int(r.Index), r.chrom, int(r.pos), r.ref, r.alt) for r in sub.itertuples()])
    results = {}
    done=[0]; t0=time.time()
    def work(b):
        js = vep_batch(b)
        idmap={}
        for x in js:
            inp = x.get("input","")
            toks = inp.split()
            if len(toks)>=3 and toks[2].isdigit():
                idmap[int(toks[2])] = x
        loc={}
        for (i,c,p,r,a) in b:
            res = idmap.get(i)
            loc[i] = parse_one(res) if res else parse_one({})
        with _lock:
            results.update(loc); done[0]+=1
            if done[0]%20==0:
                print(f"VEP {done[0]}/{len(batches)} batches {time.time()-t0:.0f}s", flush=True)
        return None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(work, batches))
    rows=[results[i] for i in range(len(df))]
    feat = pd.DataFrame(rows)
    out = pd.concat([df[["chrom","pos","ref","alt"]].reset_index(drop=True), feat], axis=1)
    out.to_parquet(out_path)
    print("saved", out_path, out.shape, flush=True)
    return out

if __name__=="__main__":
    which=sys.argv[1]
    df=pd.read_parquet(sys.argv[2])
    run(df, sys.argv[3])
