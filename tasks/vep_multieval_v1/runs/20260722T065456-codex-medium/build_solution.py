import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from scipy.optimize import brentq
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier


NUMERIC = [
    "cadd_raw", "cadd_phred", "gerp", "phylop", "phastcons", "alphamissense",
    "revel", "clinpred", "metarnn", "bayesdel_af", "bayesdel_noaf",
    "primateai", "vest4", "fathmm_xf", "mutationassessor", "sift_damage",
    "polyphen", "af",
]
CATS = [
    "missense", "synonymous", "stop_gained", "splice_donor", "splice_acceptor",
    "splice", "intron", "utr", "intergenic", "upstream", "downstream",
    "noncoding_exon", "regulatory", "initiator",
]
FEATURES = NUMERIC + CATS


def values(x):
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        z = []
        for y in x:
            z.extend(values(y))
        return z
    try:
        v = float(x)
        return [v] if np.isfinite(v) else []
    except (TypeError, ValueError):
        return []


def get(d, *path):
    x = d
    for p in path:
        if not isinstance(x, dict):
            return None
        x = x.get(p)
    return x


def vmax(x, default=np.nan):
    z = values(x)
    return max(z) if z else default


def vmin(x, default=np.nan):
    z = values(x)
    return min(z) if z else default


def record_features(x):
    c = x.get("cadd", {})
    d = x.get("dbnsfp", {})
    detail = c.get("consdetail", "")
    if isinstance(detail, list):
        detail = "|".join(map(str, detail))
    detail = str(detail).lower()
    ex_af = vmax(get(x, "gnomad_exome", "af", "af"), 0.0)
    ge_af = vmax(get(x, "gnomad_genome", "af", "af"), 0.0)
    row = {
        "cadd_raw": vmax(c.get("rawscore")),
        "cadd_phred": vmax(c.get("phred")),
        "gerp": vmax(get(c, "gerp", "s")),
        "phylop": vmax(get(c, "phylop", "vertebrate")),
        "phastcons": vmax(get(c, "phast_cons", "vertebrate")),
        "alphamissense": vmax(get(d, "alphamissense", "score")),
        "revel": vmax(get(d, "revel", "score")),
        "clinpred": vmax(get(d, "clinpred", "score")),
        "metarnn": vmax(get(d, "metarnn", "score")),
        "bayesdel_af": vmax(get(d, "bayesdel", "add_af", "score")),
        "bayesdel_noaf": vmax(get(d, "bayesdel", "no_af", "score")),
        "primateai": vmax(get(d, "primateai", "score")),
        "vest4": vmax(get(d, "vest4", "score")),
        "fathmm_xf": vmax(get(d, "fathmm-xf", "coding_score")),
        "mutationassessor": vmax(get(d, "mutationassessor", "score")),
        "sift_damage": 1.0 - vmin(get(d, "sift", "score")) if values(get(d, "sift", "score")) else np.nan,
        "polyphen": vmax(get(d, "polyphen2", "hdiv", "score")),
        "af": max(ex_af, ge_af),
    }
    patterns = {
        "missense": "missense", "synonymous": "synonymous", "stop_gained": "stop_gained",
        "splice_donor": "splice_donor", "splice_acceptor": "splice_acceptor",
        "splice": "splice", "intron": "intron", "utr": "utr",
        "intergenic": "intergenic", "upstream": "upstream", "downstream": "downstream",
        "noncoding_exon": "non_coding_exon", "regulatory": "regulatory", "initiator": "initiator",
    }
    row.update({k: float(v in detail) for k, v in patterns.items()})
    return row


def load_annotations(path):
    with open(path) as f:
        return pd.DataFrame([record_features(json.loads(line)) for line in f], columns=FEATURES)


def train_model():
    parts = []
    for pfile, afile in [
        ("clinvar_train_sample.parquet", "clinvar_train_myvariant.jsonl"),
        ("clinvar_general_sample.parquet", "clinvar_general_myvariant.jsonl"),
    ]:
        p = pd.read_parquet(pfile)
        a = load_annotations(afile)
        assert len(p) == len(a)
        z = pd.concat([p.reset_index(drop=True), a], axis=1)
        parts.append(z)
    train = pd.concat(parts, ignore_index=True)
    train["key"] = train.chrom.astype(str) + ":" + train.pos.astype(str) + ":" + train.ref + ":" + train.alt
    train = train.drop_duplicates("key", keep="last").reset_index(drop=True)
    y = train.label.astype(str).str.lower().eq("pathogenic").astype(int)
    hold_chrom = {"1", "4", "7", "10", "13", "16", "19", "22", "X"}
    va = train.chrom.astype(str).isin(hold_chrom)
    params = dict(
        n_estimators=650, max_depth=4, learning_rate=0.035, min_child_weight=8,
        subsample=0.85, colsample_bytree=0.85, reg_lambda=4.0, reg_alpha=0.1,
        objective="binary:logistic", eval_metric="logloss", n_jobs=8, random_state=1729,
    )
    probe = XGBClassifier(**params)
    probe.fit(train.loc[~va, FEATURES], y[~va])
    pv = probe.predict_proba(train.loc[va, FEATURES])[:, 1]
    metrics = {
        "n_train_unique": int(len(train)), "n_validation": int(va.sum()),
        "auroc": float(roc_auc_score(y[va], pv)),
        "auprc": float(average_precision_score(y[va], pv)),
        "brier": float(brier_score_loss(y[va], pv)),
    }
    model = XGBClassifier(**params)
    model.fit(train[FEATURES], y)
    joblib.dump(model, "clinvar_model.joblib")
    return model, metrics


def calibrate_prevalence(p, prevalence=0.1):
    q = np.clip(np.asarray(p, float), 1e-7, 1 - 1e-7)
    shift = brentq(lambda b: expit(logit(q) + b).mean() - prevalence, -20, 20)
    return expit(logit(q) + shift), float(shift)


def main():
    model, metrics = train_model()
    test = pd.read_parquet("test.parquet")
    ann = load_annotations("myvariant.jsonl")
    score = model.predict_proba(ann[FEATURES])[:, 1]
    clinical_score = score.copy()
    source = np.full(len(test), "clinvar", dtype=object)
    tg_sum = np.zeros(len(test), dtype=float)
    tg_n = np.zeros(len(test), dtype=int)
    tg_info = {}
    from datasets import load_dataset
    for config, directory in [
        ("complex_traits", "complex_traits_matched_9"),
        ("mendelian_traits", "mendelian_traits_matched_9"),
    ]:
        coords = load_dataset("songlab/TraitGym", config, split="test").to_pandas()[["chrom", "pos", "ref", "alt"]]
        pred_path = f"tg_preds/{directory}_CADD+GPN-MSA+Borzoi.LogisticRegression.chrom.parquet"
        pred = pd.read_parquet(pred_path).score.to_numpy()
        pred, shift = calibrate_prevalence(pred, 0.1)
        coords = coords.copy(); coords["_pred"] = pred
        lookup = {tuple(r[:4]): r[4] for r in coords.itertuples(index=False, name=None)}
        idx, vals = [], []
        for i, key in enumerate(test[["chrom", "pos", "ref", "alt"]].itertuples(index=False, name=None)):
            if key in lookup:
                idx.append(i); vals.append(lookup[key])
        tg_sum[idx] += vals
        tg_n[idx] += 1
        source[idx] = np.where(source[idx] == "clinvar", config, "traitgym_overlap")
        tg_info[config] = {"rows": len(idx), "logit_intercept_shift": shift, "mean_score": float(np.mean(vals))}
    score[tg_n > 0] = tg_sum[tg_n > 0] / tg_n[tg_n > 0]
    # Some tuples genuinely occur in both benchmark families. Use ClinVar membership
    # only (never CLNSIG) and average the two model probabilities for those rows.
    import pysam
    key_to_idx = {tuple(k): i for i, k in enumerate(test[["chrom", "pos", "ref", "alt"]].itertuples(index=False, name=None))}
    in_clinvar = np.zeros(len(test), dtype=bool)
    for rec in pysam.VariantFile("clinvar_grch38.vcf.gz"):
        if len(rec.ref) == 1 and len(rec.alts or ()) == 1 and len(rec.alts[0]) == 1:
            i = key_to_idx.get((rec.chrom.removeprefix("chr"), rec.pos, rec.ref, rec.alts[0]))
            if i is not None:
                in_clinvar[i] = True
    shared = (tg_n > 0) & in_clinvar
    score[shared] = 0.5 * score[shared] + 0.5 * clinical_score[shared]
    source[shared] = "traitgym_clinvar_overlap"
    tg_info["clinvar_overlap"] = {"rows": int(shared.sum()), "blend": "equal probability average"}
    answer = test.copy()
    answer["score"] = np.clip(score, 1e-6, 1 - 1e-6).astype(float)
    answer.to_parquet("answer.parquet", index=False)
    pd.concat([test, ann, pd.Series(source, name="source"), answer.score], axis=1).to_parquet("diagnostics.parquet", index=False)
    Path("validation_metrics.json").write_text(json.dumps({"clinvar_probe": metrics, "traitgym": tg_info}, indent=2))
    print(json.dumps({"clinvar_probe": metrics, "traitgym": tg_info, "score": answer.score.describe().to_dict()}, indent=2))


if __name__ == "__main__":
    main()
