import glob
import json
import math
import os

import numpy as np
import pandas as pd

ROOT = "/task"
K = ["chrom", "pos", "ref", "alt"]


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


test = pd.read_parquet(f"{ROOT}/test.parquet").reset_index(names="row_id")
test["chrom"] = test.chrom.astype(str)

# Out-of-chromosome predictions from TraitGym's best published ensemble.
gw = []
for dataset in ["complex_traits_matched_9", "mendelian_traits_matched_9"]:
    coords = pd.read_parquet(f"{ROOT}/hf/{dataset}/test.parquet", columns=K)
    coords["chrom"] = coords.chrom.astype(str)
    pred = pd.read_parquet(
        f"{ROOT}/hf/{dataset}/preds/all/"
        "CADD+GPN-MSA+Borzoi.LogisticRegression.chrom.parquet"
    ).iloc[:, 0]
    coords["balanced_score"] = pred.to_numpy()
    coords["source"] = dataset
    gw.append(coords)
gw = pd.concat(gw, ignore_index=True)
# Average the 27 naturally shared variants. Ranking is preserved by prior correction.
gw = gw.groupby(K, as_index=False).balanced_score.mean()
ans = test.merge(gw, on=K, how="left")
q = np.clip(ans.balanced_score.to_numpy(float), 1e-7, 1 - 1e-7)
# Models were fit with class_weight='balanced'; matched_9 has one case per 9 controls.
ans["gwas_score"] = q / (q + 9.0 * (1.0 - q))

# Consolidate leakage-safe VEP annotations (clinical labels were never parsed).
records = []
for p in sorted(glob.glob(f"{ROOT}/vep_batches/batch_*.json")):
    with open(p) as f:
        records.extend(json.load(f))
vep = pd.DataFrame(records)
if len(vep):
    vep = vep.drop_duplicates("row_id", keep="last").set_index("row_id")
    ans = ans.join(vep.drop(columns=["input"], errors="ignore"), on="row_id")

# Seventeen input rows use '.' as an alternate-allele sentinel.  For these only,
# use the maximum CADD score across the three possible non-reference SNVs.
override_path = f"{ROOT}/dot_alt_overrides.json"
if os.path.exists(override_path):
    with open(override_path) as f:
        ov = pd.DataFrame(json.load(f))
    ov = ov.sort_values("cadd_phred").groupby("row_id", as_index=False).tail(1).set_index("row_id")
    for rid, z in ov.iterrows():
        ans.loc[ans.row_id == rid, "cadd_phred"] = z.cadd_phred
        ans.loc[ans.row_id == rid, "most_severe_consequence"] = z.most_severe_consequence

n = len(ans)
cadd_phred = pd.to_numeric(ans.get("cadd_phred"), errors="coerce").to_numpy(float)
cadd_p = sigmoid((np.nan_to_num(cadd_phred, nan=8.0) - 15.0) / 4.0)
am = pd.to_numeric(ans.get("alphamissense"), errors="coerce").to_numpy(float)
am_p = sigmoid((np.nan_to_num(am, nan=0.45) - 0.45) * 8.0)
sp = pd.to_numeric(ans.get("spliceai"), errors="coerce").to_numpy(float)
sp_p = sigmoid((np.nan_to_num(sp, nan=0.0) - 0.30) * 10.0)
sift = pd.to_numeric(ans.get("sift_deleterious"), errors="coerce").to_numpy(float)
poly = pd.to_numeric(ans.get("polyphen_damaging"), errors="coerce").to_numpy(float)
cons = ans.get("most_severe_consequence", pd.Series("", index=ans.index)).fillna("").astype(str)

clinical = cadd_p.copy()
miss = cons.str.contains("missense").to_numpy()
for i in np.where(miss)[0]:
    vals, weights = [cadd_p[i]], [0.20]
    if np.isfinite(am[i]): vals.append(am_p[i]); weights.append(0.70)
    if np.isfinite(sift[i]): vals.append(sift[i]); weights.append(0.05)
    if np.isfinite(poly[i]): vals.append(poly[i]); weights.append(0.05)
    clinical[i] = np.average(vals, weights=weights)

splice_core = cons.str.contains("splice_donor|splice_acceptor").to_numpy()
clinical[splice_core] = 0.35 * cadd_p[splice_core] + 0.65 * sp_p[splice_core]
splice_sensitive = cons.str.contains("synonymous|intron|splice_region|polypyrimidine").to_numpy()
clinical[splice_sensitive] = np.maximum(
    clinical[splice_sensitive], 0.90 * sp_p[splice_sensitive]
)
utr = cons.str.contains("UTR").to_numpy()
clinical[utr] = 0.80 * cadd_p[utr] + 0.20 * sp_p[utr]

is_gwas = ans.balanced_score.notna().to_numpy()
score = np.where(is_gwas, ans.gwas_score.to_numpy(float), clinical)
ans["score"] = np.clip(score, 0.0, 1.0)
out = ans[K + ["score"]]
out.to_parquet(f"{ROOT}/answer.parquet", index=False)

summary = {
    "rows": len(out),
    "gwas_ensemble_rows": int(is_gwas.sum()),
    "clinical_rows": int((~is_gwas).sum()),
    "vep_rows": int(ans.most_severe_consequence.notna().sum()),
    "cadd_rows": int(np.isfinite(cadd_phred).sum()),
    "alphamissense_rows": int(np.isfinite(am).sum()),
    "spliceai_rows": int(np.isfinite(sp).sum()),
    "score_min": float(out.score.min()),
    "score_max": float(out.score.max()),
    "score_mean": float(out.score.mean()),
}
with open(f"{ROOT}/build_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(json.dumps(summary, indent=2))
