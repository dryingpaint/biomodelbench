"""Build the bacdive_gram bundle.

Produces:
  bundle/train.parquet   → strains with Gram labels; family-disjoint from test
  bundle/test.parquet    → strains with labels hidden
  hidden/answer.parquet  → ground-truth Gram labels for the test rows
  hidden/build_stats.json

Source: Madin et al. 2020 Sci Data "A synthesis of bacterial and archaeal
phenotypic trait data" — a curated table of ~170k prokaryote strain records
with Gram staining, oxygen requirement, motility, temperature range, etc.,
cross-referenced to NCBI Taxonomy. CC-BY.
  https://figshare.com/collections/…/4843290 (condensed_traits_NCBI.csv)

Assembly accession sourcing: for each strain's species_tax_id we look up
the "best" NCBI assembly via the NCBI datasets JSON-lines API. Strains
without an available assembly are dropped.

Anti-leak: bacterial strains are grouped by NCBI family, families are
randomly split 80/20 (seed=0). No family appears in both partitions.
Test rows carry only (assembly_accession, phylum) so the agent can't
name-lookup the species.
"""
from __future__ import annotations

import io
import json
import random
import subprocess
import sys
from pathlib import Path

import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
DATA_DIR = TASK_DIR / "_data"
BUNDLE_DIR = TASK_DIR / "bundle"
HIDDEN_DIR = TASK_DIR / "hidden"

# Madin et al. 2020 condensed_traits_NCBI.csv (figshare 13557827, v1.2.0)
MADIN_CSV_URL = "https://ndownloader.figshare.com/files/26019011"

# Cap the training set at this number of strains to keep the bundle
# tractable and give the agent time to fetch assemblies. Scaling up later
# is a one-line change.
MAX_TRAIN_STRAINS = 3000
MAX_TEST_STRAINS = 500
TEST_FAMILY_FRACTION = 0.2
SEED = 0


def _sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _fetch_madin() -> Path:
    dst = DATA_DIR / "madin_condensed_traits_NCBI.csv"
    if not dst.exists() or dst.stat().st_size < 10_000_000:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"[madin] downloading {dst.name}")
        _sh(["curl", "-sSfLo", str(dst), MADIN_CSV_URL])
    return dst


def _fetch_assembly_accessions(tax_ids: list[int]) -> dict[int, str]:
    """For each tax_id, ask NCBI datasets which is the best reference assembly.

    Uses the datasets-cli JSON API via a POST to the Datasets v2 REST endpoint
    (no auth required). Handles a large list by batching in chunks of 300.

    Returns a dict {tax_id: assembly_accession}. Missing tax_ids are skipped.
    """
    import requests

    out: dict[int, str] = {}
    # NCBI datasets Rest v2 rate-limits at ~10 req/s and paginates at
    # 1000 records; we go one taxon at a time to get "any RefSeq or
    # GenBank assembly" and pick the newest.
    session = requests.Session()
    for j, t in enumerate(tax_ids):
        # Just ask for anything under this taxon; pick the latest.
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
        # Prefer RefSeq (GCF_) over GenBank (GCA_); pick the first eligible.
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

    print("[1/5] fetching Madin traits table")
    madin_csv = _fetch_madin()
    df = pd.read_csv(madin_csv, low_memory=False)
    print(f"      {len(df):,} strain rows")

    # Filter: bacteria only, has gram_stain, has family, has taxid
    df = df[df["superkingdom"] == "Bacteria"].copy()
    df = df[df["gram_stain"].isin(["positive", "negative"])].copy()
    df = df[df["family"].notna() & (df["family"] != "NA")].copy()
    df = df[df["species_tax_id"].notna()].copy()
    df["species_tax_id"] = df["species_tax_id"].astype(int)
    df["label"] = (df["gram_stain"] == "positive").astype(int)
    print(f"[2/5] {len(df):,} bacterial strains with Gram label and NCBI tax_id")
    print("      gram distribution:", df["label"].value_counts().to_dict())
    print("      unique families:", df["family"].nunique())

    # De-duplicate by species_tax_id: keep the first row per species. Multiple
    # strain rows per species in Madin usually agree on Gram but occasionally
    # disagree due to source noise — drop conflicts.
    df = (
        df.groupby("species_tax_id")
        .agg(
            label=("label", lambda s: int(s.mode().iloc[0]) if s.mode().shape[0] else None),
            label_consistent=("label", lambda s: s.nunique() == 1),
            phylum=("phylum", "first"),
            family=("family", "first"),
        )
        .reset_index()
    )
    df = df[df["label_consistent"] & df["label"].notna()].drop(columns=["label_consistent"])
    print(f"[3/5] {len(df):,} species after dedup + consistent Gram label")

    # Family-level 80/20 holdout
    families = sorted(df["family"].unique().tolist())
    rng = random.Random(SEED)
    rng.shuffle(families)
    n_test = max(1, int(len(families) * TEST_FAMILY_FRACTION))
    test_families = set(families[:n_test])
    train_families = set(families[n_test:])
    train_df = df[df["family"].isin(train_families)].reset_index(drop=True)
    test_df = df[df["family"].isin(test_families)].reset_index(drop=True)
    print(f"      family-holdout: {len(train_families):,} train families, {len(test_families):,} test families")
    print(f"      before cap: train={len(train_df):,}  test={len(test_df):,}")

    # Cap sizes
    if len(train_df) > MAX_TRAIN_STRAINS:
        train_df = train_df.sample(n=MAX_TRAIN_STRAINS, random_state=SEED).reset_index(drop=True)
    if len(test_df) > MAX_TEST_STRAINS:
        test_df = test_df.sample(n=MAX_TEST_STRAINS, random_state=SEED).reset_index(drop=True)

    # Fetch assembly accessions for the union of tax_ids
    print("[4/5] fetching NCBI assembly accessions for train + test tax_ids")
    all_tax_ids = sorted(
        set(train_df["species_tax_id"].tolist()) | set(test_df["species_tax_id"].tolist())
    )
    print(f"      {len(all_tax_ids):,} unique species tax_ids to look up")
    tax_to_acc = _fetch_assembly_accessions(all_tax_ids)
    print(f"      resolved {len(tax_to_acc):,} accessions")

    train_df["assembly_accession"] = train_df["species_tax_id"].map(tax_to_acc)
    test_df["assembly_accession"] = test_df["species_tax_id"].map(tax_to_acc)

    # Keep only strains with an assembly available
    train_df = train_df[train_df["assembly_accession"].notna()].reset_index(drop=True)
    test_df = test_df[test_df["assembly_accession"].notna()].reset_index(drop=True)
    print(f"      after assembly filter: train={len(train_df):,}  test={len(test_df):,}")

    # Ship: assembly_accession, phylum, label (train only). Species name /
    # family / genus / species_tax_id are NOT shipped — those would let the
    # agent lookup the answer by name.
    train_shipped = train_df[["assembly_accession", "phylum", "label"]].copy()
    test_shipped = test_df[["assembly_accession", "phylum"]].copy()
    train_shipped.to_parquet(BUNDLE_DIR / "train.parquet", index=False)
    test_shipped.to_parquet(BUNDLE_DIR / "test.parquet", index=False)

    # Copy the agent-facing prompt into bundle/
    (BUNDLE_DIR / "prompt.md").write_bytes((TASK_DIR / "prompt.md").read_bytes())

    # Hidden ground truth for grader
    hidden = test_df[["assembly_accession", "label"]].copy()
    hidden.to_parquet(HIDDEN_DIR / "answer.parquet", index=False)

    stats = {
        "train_rows": int(len(train_shipped)),
        "train_positives": int(train_shipped["label"].sum()),
        "train_positive_rate": float(train_shipped["label"].mean()),
        "test_rows": int(len(test_shipped)),
        "test_positives_hidden": int(hidden["label"].sum()),
        "test_positive_rate": float(hidden["label"].mean()),
        "n_train_families": int(len(train_families)),
        "n_test_families": int(len(test_families)),
        "assemblies_resolved_pct": float(len(tax_to_acc) / max(1, len(all_tax_ids))),
        "sources": {
            "madin_csv": MADIN_CSV_URL,
            "ncbi_assembly_api": "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/dataset_report",
        },
    }
    (HIDDEN_DIR / "build_stats.json").write_text(json.dumps(stats, indent=2))

    print("\ndone.")
    print(f"  bundle/train.parquet — {len(train_shipped):,} rows ({int(train_shipped['label'].sum())} Gram+)")
    print(f"  bundle/test.parquet  — {len(test_shipped):,} rows (labels hidden)")
    print(f"  hidden/answer.parquet — {len(hidden):,} rows (ground truth)")
    print(f"  hidden/build_stats.json — {stats}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"subprocess failed: {exc}", file=sys.stderr)
        sys.exit(1)
