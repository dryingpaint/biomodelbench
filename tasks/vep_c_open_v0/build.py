"""Build the vep_c_open_v0 bundle.

Ships ONLY the TraitGym complex_traits_matched_9 test variant IDs and the
agent-facing prompt. No training labels, no features. The agent must find
its own labeled training data from an allowlisted online source, apply
anti-leak filtering against the shipped test set, and construct features.

Produces:
  tasks/vep_c_open_v0/bundle/test.parquet    → 11,400 rows shipped (no labels)
  tasks/vep_c_open_v0/bundle/prompt.md       → copy of the agent-facing prompt
  tasks/vep_c_open_v0/hidden/answer.parquet  → ground truth labels for grader
  tasks/vep_c_open_v0/hidden/build_stats.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
DATA_DIR = TASK_DIR / "_data"
BUNDLE_DIR = TASK_DIR / "bundle"
HIDDEN_DIR = TASK_DIR / "hidden"

TG_URL = (
    "https://huggingface.co/datasets/songlab/TraitGym/resolve/main/"
    "complex_traits_matched_9/test.parquet"
)


def _sh(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tg_path = DATA_DIR / "complex_traits_matched_9_test.parquet"
    if not tg_path.exists() or tg_path.stat().st_size < 100_000:
        print(f"fetching TraitGym test set → {tg_path.name}")
        _sh(["curl", "-sSfLo", str(tg_path), TG_URL])

    tg = pd.read_parquet(tg_path)
    tg["chrom"] = tg["chrom"].astype(str)
    print(f"loaded {len(tg):,} test variants, {int(tg['label'].sum())} positives")

    # What ships to the agent: variant IDs only.
    test = tg[["chrom", "pos", "ref", "alt"]].reset_index(drop=True)
    test.to_parquet(BUNDLE_DIR / "test.parquet", index=False)

    # Copy the prompt into bundle/ so it lands next to test.parquet.
    (BUNDLE_DIR / "prompt.md").write_bytes((TASK_DIR / "prompt.md").read_bytes())

    # Hidden answer: labels for the grader.
    answer = tg[["chrom", "pos", "ref", "alt", "label"]].reset_index(drop=True)
    answer.to_parquet(HIDDEN_DIR / "answer.parquet", index=False)

    stats = {
        "test_rows": int(len(test)),
        "test_positives_hidden": int(answer["label"].sum()),
        "test_positive_rate": float(answer["label"].mean()),
        "training_data_shipped": False,
        "features_shipped": False,
        "source_test": TG_URL,
    }
    (HIDDEN_DIR / "build_stats.json").write_text(json.dumps(stats, indent=2))

    print("done.")
    print(f"  bundle/test.parquet — {len(test):,} rows (labels hidden)")
    print(f"  bundle/prompt.md — agent prompt with allowlist + blacklist")
    print(f"  hidden/answer.parquet — {len(answer):,} rows (ground truth)")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"subprocess failed: {exc}", file=sys.stderr)
        sys.exit(1)
