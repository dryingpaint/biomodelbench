"""Build the bacdive_multitrait bundle.

Produces:
  bundle/train.parquet   → strains with per-target labels; family-disjoint from test
  bundle/test.parquet    → strains with labels hidden
  hidden/answer.parquet  → ground-truth per-target labels for the test rows
  hidden/build_stats.json

Source: Madin et al. 2020 Sci Data "A synthesis of bacterial and archaeal
phenotypic trait data" — a curated table of ~170k prokaryote strain records,
cross-referenced to NCBI Taxonomy. CC-BY.
  https://figshare.com/collections/…/4843290 (condensed_traits_NCBI.csv)

Anti-leak: bacterial species are grouped by NCBI family, families are
randomly split 80/20 (seed=0). No family appears in both partitions.
Test rows carry only (assembly_accession, phylum) so the agent can't
name-lookup the species.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
DATA_DIR = TASK_DIR / "_data"
BUNDLE_DIR = TASK_DIR / "bundle"
HIDDEN_DIR = TASK_DIR / "hidden"

MADIN_CSV_URL = "https://ndownloader.figshare.com/files/26019011"

MAX_TRAIN_STRAINS = 5000
MAX_TEST_STRAINS = 800
TEST_FAMILY_FRACTION = 0.2
SEED = 0
MIN_TRAITS_POPULATED = 3  # keep species with ≥ this many primary traits

# ── target definitions ────────────────────────────────────────────────
# Binary probability targets. Ground truth is 0/1; agent predicts P in [0,1].
BINARY_TARGETS = {
    "gram_positive_prob": {
        "source_col": "gram_stain",
        "positive_label": "positive",
        "negative_label": "negative",
    },
    "sporulation_prob": {
        "source_col": "sporulation",
        "positive_label": "yes",
        "negative_label": "no",
    },
    "motility_prob": {
        "source_col": "motility",
        # Madin has 'no', 'yes', 'flagella', 'gliding', 'axial filament'.
        # Everything except 'no' is motile.
        "positive_labels": {"yes", "flagella", "gliding", "axial filament"},
        "negative_labels": {"no"},
    },
}

# Categorical (multiclass) targets. Ground truth is a string label; agent
# predicts a string label. Grader computes macro-F1, balanced accuracy.
CATEGORICAL_TARGETS = {
    "oxygen_tolerance": {
        "source_col": "metabolism",
        # Madin has: aerobic, obligate aerobic, anaerobic, obligate anaerobic,
        # microaerophilic, facultative
        "label_map": {
            "aerobic": "aerobic",
            "obligate aerobic": "aerobic",
            "anaerobic": "anaerobic",
            "obligate anaerobic": "anaerobic",
            "microaerophilic": "microaerophilic",
            "facultative": "facultative",
        },
        "valid_labels": ["aerobic", "anaerobic", "facultative", "microaerophilic"],
    },
    "temperature_range": {
        "source_col": "range_tmp",
        # Madin has: psychrophilic, mesophilic, thermophilic, extreme thermophilic,
        # psychrotolerant, thermotolerant, facultative psychrophilic.
        # Collapse tolerants into their nearest range.
        "label_map": {
            "psychrophilic": "psychrophilic",
            "psychrotolerant": "psychrophilic",
            "facultative psychrophilic": "psychrophilic",
            "mesophilic": "mesophilic",
            "thermophilic": "thermophilic",
            "thermotolerant": "thermophilic",
            "extreme thermophilic": "extreme_thermophilic",
        },
        "valid_labels": ["psychrophilic", "mesophilic", "thermophilic", "extreme_thermophilic"],
    },
    "cell_shape": {
        "source_col": "cell_shape",
        # Madin has: bacillus, coccus, filament, coccobacillus, spiral, vibrio,
        # pleomorphic, irregular, fusiform, star, square, flask, spindle, disc, branced.
        # Keep 6 main classes + `other`.
        "label_map": {
            "bacillus": "bacillus",
            "coccus": "coccus",
            "spiral": "spiral",
            "coccobacillus": "coccobacillus",
            "vibrio": "vibrio",
            "filament": "filament",
        },
        "default": "other",
        "valid_labels": ["bacillus", "coccus", "spiral", "coccobacillus", "vibrio", "filament", "other"],
    },
}

# Continuous targets. Ground truth is a float; agent predicts a float.
# Grader computes Spearman ρ, MAE. Optionally: clip to reasonable range.
CONTINUOUS_TARGETS = {
    "optimum_temperature_c": {
        "source_col": "optimum_tmp",
        "min": 0.0,
        "max": 110.0,
    },
    "optimum_ph": {
        "source_col": "optimum_ph",
        "min": 0.0,
        "max": 14.0,
    },
}

# Pathway multi-label targets. `pathways` in Madin is a comma-delimited
# string of pathway tokens. Each pathway becomes an independent 0/1 target;
# agent predicts probability in [0,1] per pathway.
PATHWAY_TARGETS = [
    "nitrogen_fixation",
    "nitrate_reduction",
    "denitrification",
    "sulfate_reduction",
    "fermentation",
    "cellulose_degradation",
    "xylan_degradation",
    "chitin_degradation",
    "fumarate_reduction",
    "iron_reduction",
]

# Columns that appear in the shipped train.parquet and hidden answer.parquet.
def all_target_columns() -> list[str]:
    cols: list[str] = []
    cols += list(BINARY_TARGETS.keys())
    cols += list(CATEGORICAL_TARGETS.keys())
    cols += list(CONTINUOUS_TARGETS.keys())
    cols += [f"pathway_{p}_prob" for p in PATHWAY_TARGETS]
    return cols


def _sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _fetch_madin() -> Path:
    dst = DATA_DIR / "madin_condensed_traits_NCBI.csv"
    if not dst.exists() or dst.stat().st_size < 10_000_000:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[madin] downloading {dst.name}")
        _sh(["curl", "-sSfLo", str(dst), MADIN_CSV_URL])
    return dst


def _species_agg(df: pd.DataFrame) -> pd.DataFrame:
    """Dedup by species_tax_id, majority-vote per column, drop conflicts."""
    def mode_or_nan(s: pd.Series):
        s = s.dropna()
        if len(s) == 0:
            return np.nan
        m = s.mode()
        if len(m) == 0:
            return np.nan
        # If the top mode is >= half the observations, take it; else NaN (conflict).
        top = m.iloc[0]
        if (s == top).sum() >= max(1, len(s) // 2):
            return top
        return np.nan

    def mean_or_nan(s: pd.Series):
        s = s.dropna()
        return float(s.mean()) if len(s) else np.nan

    def union_tokens(s: pd.Series):
        toks: set[str] = set()
        for entry in s.dropna():
            for tok in str(entry).split(","):
                tok = tok.strip()
                if tok:
                    toks.add(tok)
        return ",".join(sorted(toks)) if toks else np.nan

    agg = {
        "phylum": mode_or_nan,
        "family": mode_or_nan,
        "gram_stain": mode_or_nan,
        "metabolism": mode_or_nan,
        "sporulation": mode_or_nan,
        "motility": mode_or_nan,
        "range_tmp": mode_or_nan,
        "cell_shape": mode_or_nan,
        "optimum_tmp": mean_or_nan,
        "optimum_ph": mean_or_nan,
        "pathways": union_tokens,
    }
    out = df.groupby("species_tax_id").agg(agg).reset_index()
    return out


def _label_binary(source_val, spec) -> float:
    if pd.isna(source_val):
        return np.nan
    v = str(source_val).strip()
    if "positive_labels" in spec:
        if v in spec["positive_labels"]:
            return 1.0
        if v in spec["negative_labels"]:
            return 0.0
        return np.nan
    if v == spec["positive_label"]:
        return 1.0
    if v == spec["negative_label"]:
        return 0.0
    return np.nan


def _label_categorical(source_val, spec):
    if pd.isna(source_val):
        return np.nan
    v = str(source_val).strip()
    mapped = spec["label_map"].get(v)
    if mapped is not None:
        return mapped
    if "default" in spec:
        return spec["default"]
    return np.nan


def _label_continuous(source_val, spec) -> float:
    if pd.isna(source_val):
        return np.nan
    try:
        v = float(source_val)
    except (TypeError, ValueError):
        return np.nan
    if not (spec["min"] <= v <= spec["max"]):
        return np.nan
    return v


def _label_pathways(source_val) -> dict[str, float]:
    """Return {pathway: 0/1} for every pathway in PATHWAY_TARGETS.

    A species has a pathway = 1 iff the token is present in `pathways`.
    We return NaN for ALL pathways if `pathways` is missing — this species
    was not annotated for metabolic pathways at all. If `pathways` is
    populated, absent pathways get 0.
    """
    if pd.isna(source_val):
        return {p: np.nan for p in PATHWAY_TARGETS}
    tokens = {t.strip() for t in str(source_val).split(",") if t.strip()}
    return {p: (1.0 if p in tokens else 0.0) for p in PATHWAY_TARGETS}


def _build_target_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Given species-level Madin rows, emit the 18 target columns."""
    out = df[["species_tax_id", "phylum", "family"]].copy()
    for name, spec in BINARY_TARGETS.items():
        out[name] = df[spec["source_col"]].map(lambda v: _label_binary(v, spec))
    for name, spec in CATEGORICAL_TARGETS.items():
        out[name] = df[spec["source_col"]].map(lambda v: _label_categorical(v, spec))
    for name, spec in CONTINUOUS_TARGETS.items():
        out[name] = df[spec["source_col"]].map(lambda v: _label_continuous(v, spec))
    pathway_records = df["pathways"].map(_label_pathways).tolist()
    for p in PATHWAY_TARGETS:
        col = f"pathway_{p}_prob"
        out[col] = [rec[p] for rec in pathway_records]
    return out


def _fetch_assembly_accessions(tax_ids: list[int]) -> dict[int, str]:
    """For each tax_id, ask NCBI datasets which is the best reference assembly."""
    import requests

    out: dict[int, str] = {}
    session = requests.Session()
    for j, t in enumerate(tax_ids):
        url = (
            f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/taxon/{t}/dataset_report"
            "?page_size=5&filters.assembly_version=current"
        )
        try:
            r = session.get(url, timeout=30)
            r.raise_for_status()
        except Exception as e:
            if j % 200 == 0:
                print(f"[assembly] taxon {t} failed: {e}", flush=True)
            continue
        reports = r.json().get("reports") or []
        best: str | None = None
        for rep in reports:
            acc = rep.get("accession")
            if not acc:
                continue
            if acc.startswith("GCF_"):
                best = acc
                break
            if best is None and acc.startswith("GCA_"):
                best = acc
        if best is not None:
            out[t] = best
        if (j + 1) % 200 == 0:
            print(f"[assembly] {j+1}/{len(tax_ids):,} tax_ids probed, {len(out):,} accessions resolved", flush=True)
    return out


def main() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/6] fetching Madin traits table")
    madin_csv = _fetch_madin()
    df = pd.read_csv(madin_csv, low_memory=False)
    print(f"      {len(df):,} strain rows")

    df = df[df["superkingdom"] == "Bacteria"].copy()
    df = df[df["species_tax_id"].notna()].copy()
    df["species_tax_id"] = df["species_tax_id"].astype(int)

    print("[2/6] species-level dedup with mode voting")
    sp = _species_agg(df)
    print(f"      {len(sp):,} species after dedup")

    sp = sp[sp["family"].notna() & (sp["family"] != "NA")].copy()

    print("[3/6] building target label columns")
    labels = _build_target_columns(sp)
    n_traits = labels[
        [
            *BINARY_TARGETS.keys(),
            *CATEGORICAL_TARGETS.keys(),
            *CONTINUOUS_TARGETS.keys(),
        ]
    ].notna().sum(axis=1)
    labels = labels[n_traits >= MIN_TRAITS_POPULATED].reset_index(drop=True)
    print(f"      {len(labels):,} species with ≥{MIN_TRAITS_POPULATED} of 8 primary traits")

    # Family holdout
    families = sorted(labels["family"].unique().tolist())
    rng = random.Random(SEED)
    rng.shuffle(families)
    n_test = max(1, int(len(families) * TEST_FAMILY_FRACTION))
    test_families = set(families[:n_test])
    train_families = set(families[n_test:])
    train_labels = labels[labels["family"].isin(train_families)].reset_index(drop=True)
    test_labels = labels[labels["family"].isin(test_families)].reset_index(drop=True)
    print(f"      family-holdout: {len(train_families):,} train families, {len(test_families):,} test families")
    print(f"      before cap: train={len(train_labels):,}  test={len(test_labels):,}")

    if len(train_labels) > MAX_TRAIN_STRAINS:
        train_labels = train_labels.sample(n=MAX_TRAIN_STRAINS, random_state=SEED).reset_index(drop=True)
    if len(test_labels) > MAX_TEST_STRAINS:
        test_labels = test_labels.sample(n=MAX_TEST_STRAINS, random_state=SEED).reset_index(drop=True)

    print("[4/6] fetching NCBI assembly accessions for train + test tax_ids")
    all_tax_ids = sorted(
        set(train_labels["species_tax_id"].tolist())
        | set(test_labels["species_tax_id"].tolist())
    )
    print(f"      {len(all_tax_ids):,} unique species tax_ids to look up")
    tax_to_acc = _fetch_assembly_accessions(all_tax_ids)
    print(f"      resolved {len(tax_to_acc):,} accessions")

    train_labels["assembly_accession"] = train_labels["species_tax_id"].map(tax_to_acc)
    test_labels["assembly_accession"] = test_labels["species_tax_id"].map(tax_to_acc)
    train_labels = train_labels[train_labels["assembly_accession"].notna()].reset_index(drop=True)
    test_labels = test_labels[test_labels["assembly_accession"].notna()].reset_index(drop=True)
    print(f"      after assembly filter: train={len(train_labels):,}  test={len(test_labels):,}")

    # Shipped columns: assembly_accession + phylum + 18 target cols (train only)
    target_cols = all_target_columns()
    train_shipped = train_labels[["assembly_accession", "phylum", *target_cols]].copy()
    test_shipped = test_labels[["assembly_accession", "phylum"]].copy()

    print("[5/6] writing bundle")
    train_shipped.to_parquet(BUNDLE_DIR / "train.parquet", index=False)
    test_shipped.to_parquet(BUNDLE_DIR / "test.parquet", index=False)
    (BUNDLE_DIR / "prompt.md").write_bytes((TASK_DIR / "prompt.md").read_bytes())

    hidden = test_labels[["assembly_accession", *target_cols]].copy()
    hidden.to_parquet(HIDDEN_DIR / "answer.parquet", index=False)

    print("[6/6] writing build stats")
    stats: dict = {
        "train_rows": int(len(train_shipped)),
        "test_rows": int(len(test_shipped)),
        "n_train_families": int(len(train_families)),
        "n_test_families": int(len(test_families)),
        "assemblies_resolved_pct": float(len(tax_to_acc) / max(1, len(all_tax_ids))),
        "sources": {
            "madin_csv": MADIN_CSV_URL,
            "ncbi_assembly_api": "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/dataset_report",
        },
        "per_target_test_coverage": {},
        "per_target_test_base_rate": {},
    }
    for col in target_cols:
        non_nan = hidden[col].notna().sum()
        stats["per_target_test_coverage"][col] = int(non_nan)
        if col in BINARY_TARGETS or col.startswith("pathway_"):
            stats["per_target_test_base_rate"][col] = float(
                hidden[col].dropna().mean()
            ) if non_nan else None
        elif col in CATEGORICAL_TARGETS:
            vc = hidden[col].dropna().value_counts(normalize=True).to_dict()
            stats["per_target_test_base_rate"][col] = {k: float(v) for k, v in vc.items()}
        else:  # continuous
            vals = hidden[col].dropna()
            stats["per_target_test_base_rate"][col] = {
                "mean": float(vals.mean()) if len(vals) else None,
                "median": float(vals.median()) if len(vals) else None,
                "std": float(vals.std()) if len(vals) > 1 else None,
            }
    (HIDDEN_DIR / "build_stats.json").write_text(json.dumps(stats, indent=2))

    print("\ndone.")
    print(f"  bundle/train.parquet — {len(train_shipped):,} rows × {len(target_cols)+2} cols")
    print(f"  bundle/test.parquet  — {len(test_shipped):,} rows × 2 cols (labels hidden)")
    print(f"  hidden/answer.parquet — {len(hidden):,} rows × {len(target_cols)+1} cols (ground truth)")
    print(f"  hidden/build_stats.json — coverage per target logged")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"subprocess failed: {exc}", file=sys.stderr)
        sys.exit(1)
