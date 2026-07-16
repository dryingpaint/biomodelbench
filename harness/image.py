"""Shared Modal container image for BioModelBench agent runs.

Tasks get a container with:
  - Python 3.11
  - claude-code CLI (npm) — the agent
  - torch / transformers / peft — for FM inference the agent might do
  - xgboost / lightgbm / scikit-learn — supervised heads
  - pandas / pyarrow / numpy — data
  - pyBigWig / pysam / biopython — genomics I/O
  - tabix / bcftools / wget / curl — command-line helpers
  - internet outbound (Modal default)
"""
from __future__ import annotations

import modal


def build_image() -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install(
            "curl", "git", "nodejs", "npm", "ripgrep", "jq", "ca-certificates",
            "tabix", "bcftools", "wget",
        )
        .pip_install(
            "torch==2.3.0",
            "transformers==4.41.2",
            "scikit-learn>=1.4",
            "pandas>=2",
            "pyarrow>=14",
            "numpy>=1.26",
            "peft>=0.11",
            "xgboost>=2.0",
            "lightgbm>=4.3",
            "tqdm",
            "requests",
            "matplotlib",
            "pyBigWig>=0.3",
            "pysam>=0.22",
            "biopython>=1.83",
        )
        .run_commands("npm install -g @anthropic-ai/claude-code")
    )
