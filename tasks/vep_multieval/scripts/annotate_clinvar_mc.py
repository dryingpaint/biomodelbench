"""Post-hoc annotate hidden/clinvar_answer.parquet with molecular
consequence (MC) tags from the cached ClinVar VCF.

Reads the ClinVar VCF that build.py already downloads, extracts a
single canonical consequence per variant from the MC INFO field, and
writes an augmented `hidden/clinvar_answer.parquet` with a new
`mc_class` column. Existing rows are preserved; only the extra column
is added.

Run this after build.py has produced the hidden bundle.
"""
from __future__ import annotations

import gzip
from pathlib import Path

import pandas as pd

TASK_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = TASK_DIR / "_data"
HIDDEN_DIR = TASK_DIR / "hidden"

VCF = DATA_DIR / "clinvar.vcf.gz"
ANSWER = HIDDEN_DIR / "clinvar_answer.parquet"

# Sequence Ontology → coarse molecular-consequence class we grade by.
# ClinVar's MC field looks like: MC=SO:0001583|missense_variant,SO:0001627|intron_variant
# We collapse the SO terms into 7 grader-facing classes.
SO_TO_CLASS = {
    # coding — the missense/LoF axis
    "SO:0001583": "missense",
    "SO:0001587": "stop_gained",         # nonsense
    "SO:0001578": "stop_lost",
    "SO:0001589": "frameshift",          # SNV frameshifts are rare but include
    "SO:0001582": "initiator_codon",
    "SO:0001819": "synonymous",
    # splice — mechanistically distinct from missense
    "SO:0001574": "splice_acceptor",
    "SO:0001575": "splice_donor",
    "SO:0001630": "splice_region",
    # non-coding classes
    "SO:0001623": "5_prime_utr",
    "SO:0001624": "3_prime_utr",
    "SO:0001627": "intronic",
    "SO:0001628": "intergenic",
    "SO:0001566": "regulatory_region",
    "SO:0001891": "regulatory_region",   # regulatory_region_ablation
    # everything else falls through to "other"
}

# Priority when a variant carries multiple MC codes. Coding LoF > coding missense
# > splice > synonymous > UTR > intronic > intergenic > other.
PRIORITY = [
    "stop_gained", "stop_lost", "frameshift", "initiator_codon",
    "splice_acceptor", "splice_donor",
    "missense",
    "splice_region",
    "synonymous",
    "5_prime_utr", "3_prime_utr",
    "intronic",
    "regulatory_region",
    "intergenic",
    "other",
]


def _pick_class(mc_field: str) -> str:
    if not mc_field:
        return "other"
    classes: set[str] = set()
    for entry in mc_field.split(","):
        if "|" in entry:
            so, _ = entry.split("|", 1)
        else:
            so = entry
        cls = SO_TO_CLASS.get(so.strip(), "other")
        classes.add(cls)
    if not classes:
        return "other"
    for tier in PRIORITY:
        if tier in classes:
            return tier
    return "other"


def main() -> None:
    if not VCF.exists():
        raise SystemExit(f"ClinVar VCF cache missing at {VCF}. Run build.py first.")
    if not ANSWER.exists():
        raise SystemExit(f"hidden ClinVar answer missing at {ANSWER}. Run build.py first.")

    ans = pd.read_parquet(ANSWER)
    print(f"[mc] loaded {len(ans):,} hidden ClinVar rows")

    keyset = set(zip(ans["chrom"].astype(str), ans["pos"].astype(int), ans["ref"], ans["alt"]))

    # Review-status → coarse tier. ClinVar's stars:
    #  1★ = criteria_provided,_single_submitter (already filtered out at build)
    #  2★ = criteria_provided,_multiple_submitters,_no_conflicts
    #  3★ = reviewed_by_expert_panel
    #  4★ = practice_guideline
    STAR_MAP = {
        "criteria_provided,_multiple_submitters,_no_conflicts": "2_star",
        "reviewed_by_expert_panel": "3_star_expert_panel",
        "practice_guideline": "4_star_practice_guideline",
    }
    # Clinical significance → coarse pathogenicity strength tier.
    SIG_MAP = {
        "Pathogenic": "pathogenic",
        "Likely_pathogenic": "likely_pathogenic",
        "Pathogenic/Likely_pathogenic": "pathogenic",
        "Benign": "benign",
        "Likely_benign": "likely_benign",
        "Benign/Likely_benign": "benign",
    }

    key_to_mc: dict[tuple, str] = {}
    key_to_star: dict[tuple, str] = {}
    key_to_sig: dict[tuple, str] = {}
    seen_keys = 0
    print("[mc] scanning ClinVar VCF for MC + CLNREVSTAT + CLNSIG tags")
    with gzip.open(VCF, "rt") as f:
        for i, line in enumerate(f):
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8:
                continue
            chrom, pos, ref, alt = parts[0], parts[1], parts[3], parts[4]
            if len(ref) != 1 or len(alt) != 1:
                continue
            k = (chrom, int(pos), ref, alt)
            if k not in keyset:
                continue
            info = parts[7]
            mc_field = ""
            rev = ""
            sig = ""
            for kv in info.split(";"):
                if kv.startswith("MC="):
                    mc_field = kv[3:]
                elif kv.startswith("CLNREVSTAT="):
                    rev = kv[len("CLNREVSTAT="):]
                elif kv.startswith("CLNSIG="):
                    sig = kv[len("CLNSIG="):]
            key_to_mc[k] = _pick_class(mc_field)
            key_to_star[k] = STAR_MAP.get(rev, "unknown")
            key_to_sig[k] = SIG_MAP.get(sig, "unknown")
            seen_keys += 1
            if i % 500_000 == 0 and i > 0:
                print(f"  scanned {i:,} VCF lines; matched {seen_keys:,}/{len(ans):,}")

    ans["mc_class"] = [
        key_to_mc.get((str(c), int(p), r, a), "other")
        for c, p, r, a in zip(ans["chrom"], ans["pos"], ans["ref"], ans["alt"])
    ]
    ans["review_status"] = [
        key_to_star.get((str(c), int(p), r, a), "unknown")
        for c, p, r, a in zip(ans["chrom"], ans["pos"], ans["ref"], ans["alt"])
    ]
    ans["significance_tier"] = [
        key_to_sig.get((str(c), int(p), r, a), "unknown")
        for c, p, r, a in zip(ans["chrom"], ans["pos"], ans["ref"], ans["alt"])
    ]
    print(f"[mc] annotated {len(ans):,} rows")
    print("[mc] mc_class distribution:")
    print(ans["mc_class"].value_counts().to_string())
    print("\n[mc] review_status distribution:")
    print(ans["review_status"].value_counts().to_string())
    print("\n[mc] significance_tier distribution:")
    print(ans["significance_tier"].value_counts().to_string())

    print("\n[mc] mc_class × label:")
    print(pd.crosstab(ans["mc_class"], ans["label"]).to_string())
    print("\n[mc] review_status × label:")
    print(pd.crosstab(ans["review_status"], ans["label"]).to_string())

    ans.to_parquet(ANSWER, index=False)
    print(f"\n[mc] wrote {ANSWER}")


if __name__ == "__main__":
    main()
