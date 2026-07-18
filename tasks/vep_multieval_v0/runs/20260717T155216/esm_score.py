import json, time, requests, numpy as np, pandas as pd, torch
from transformers import AutoTokenizer, AutoModelForMaskedLM

df = pd.read_parquet('/task/test.parquet'); df['chrom']=df['chrom'].astype(str)
keys = [f"{r.chrom} {r.pos} . {r.ref} {r.alt} . . ." for r in df.itertuples()]

vep = json.load(open('/task/data/vep_raw.json'))
print("vep recs", len(vep), flush=True)

AA = set("ACDEFGHIKLMNPQRSTVWY")

def pick_missense(rec):
    """Return (transcript_id, protein_start(1-based), ref_aa, alt_aa) or None."""
    best=None
    for tc in rec.get('transcript_consequences',[]):
        if 'missense_variant' not in tc.get('consequence_terms',[]): continue
        aa=tc.get('amino_acids');ps=tc.get('protein_start');tid=tc.get('transcript_id')
        if not aa or '/' not in aa or ps is None or not tid: continue
        ref_aa,alt_aa=aa.split('/')[0],aa.split('/')[-1]
        if len(ref_aa)!=1 or len(alt_aa)!=1: continue
        if ref_aa not in AA or alt_aa not in AA: continue
        cand=(tid,int(ps),ref_aa,alt_aa)
        # prefer canonical
        if tc.get('canonical'): return cand
        if best is None: best=cand
    return best

items=[]  # (row_index, tid, ps, ref_aa, alt_aa)
for idx,k in enumerate(keys):
    rec=vep.get(k)
    if rec is None: continue
    m=pick_missense(rec)
    if m: items.append((idx,)+m)
print("missense items", len(items), flush=True)

# fetch protein seqs for unique transcripts via Ensembl POST
tids=sorted(set(x[1] for x in items))
print("unique transcripts", len(tids), flush=True)
seqs={}
S='https://rest.ensembl.org/sequence/id'
H={'Content-Type':'application/json','Accept':'application/json'}
for i in range(0,len(tids),50):
    chunk=tids[i:i+50]
    for t in range(6):
        try:
            r=requests.post(S+'?type=protein',headers=H,data=json.dumps({'ids':chunk}),timeout=120)
            if r.status_code==200:
                for o in r.json():
                    seqs[o['id']]=o.get('seq','')
                break
            if r.status_code==429: time.sleep(float(r.headers.get('Retry-After',3))+1); continue
            time.sleep(3)
        except Exception: time.sleep(3)
    if (i//50)%10==0: print(f"  fetched {len(seqs)}/{len(tids)} proteins",flush=True)
print("fetched proteins", len(seqs), flush=True)
json.dump(seqs, open('/task/data/protein_seqs.json','w'))

# ESM2 masked-marginal
dev='cuda'
tok=AutoTokenizer.from_pretrained('facebook/esm2_t33_650M_UR50D')
model=AutoModelForMaskedLM.from_pretrained('facebook/esm2_t33_650M_UR50D').half().to(dev).eval()
MASK=tok.mask_token_id
WIN=510  # +-window

# build scoring jobs (only where seq matches ref)
jobs=[]  # (row_index, alt_aa, tokens(list ids w/ mask), mask_pos_in_tokens, ref_aa)
skip_mismatch=0
for (idx,tid,ps,ref_aa,alt_aa) in items:
    seq=seqs.get(tid,'')
    if not seq or ps>len(seq): continue
    if seq[ps-1]!=ref_aa: skip_mismatch+=1; continue
    # window
    lo=max(0,(ps-1)-WIN); hi=min(len(seq),(ps-1)+WIN+1)
    sub=seq[lo:hi]
    rel=(ps-1)-lo  # index in sub
    enc=tok(sub, return_tensors=None, add_special_tokens=True)['input_ids']
    mpos=rel+1  # +1 for CLS
    if mpos>=len(enc)-1: continue
    jobs.append((idx,ref_aa,alt_aa,enc,mpos))
print("scorable jobs", len(jobs), "mismatch skipped", skip_mismatch, flush=True)

# token id for each aa
aa_tok={a:tok.convert_tokens_to_ids(a) for a in "ACDEFGHIKLMNPQRSTVWY"}

scores=np.full(len(df), np.nan)
# sort by length for batching
jobs.sort(key=lambda j: len(j[3]))
B=24
t0=time.time()
with torch.no_grad():
    for bi in range(0,len(jobs),B):
        bj=jobs[bi:bi+B]
        maxlen=max(len(j[3]) for j in bj)
        ids=torch.full((len(bj),maxlen), tok.pad_token_id, dtype=torch.long)
        att=torch.zeros((len(bj),maxlen), dtype=torch.long)
        for r,j in enumerate(bj):
            enc=list(j[3]); enc[j[4]]=MASK
            ids[r,:len(enc)]=torch.tensor(enc); att[r,:len(enc)]=1
        ids=ids.to(dev);att=att.to(dev)
        logits=model(input_ids=ids,attention_mask=att).logits
        lp=torch.log_softmax(logits.float(),dim=-1)
        for r,j in enumerate(bj):
            idx,ref_aa,alt_aa,enc,mpos=j
            row=lp[r,mpos]
            s=float(row[aa_tok[ref_aa]]-row[aa_tok[alt_aa]])  # higher = more damaging
            scores[idx]=s
        if (bi//B)%50==0:
            print(f"  {bi}/{len(jobs)} {time.time()-t0:.0f}s",flush=True)

out=pd.DataFrame({'chrom':df.chrom,'pos':df.pos,'ref':df.ref,'alt':df.alt,'esm_llr':scores})
out.to_parquet('/task/data/esm_scores.parquet')
print("saved esm_scores.parquet, non-nan", np.isfinite(scores).sum(), flush=True)
