# `vep_c_open_v0` — complex-trait causal SNP prediction, open data discovery

## What the task is

The agent gets only 11,400 TraitGym `complex_traits_matched_9` test
variant IDs (no labels, no features) and must build a predictor from
scratch — including *finding its own labeled training data* from an
allowlisted online source (Open Targets Genetics, CausalDB, gnomAD, …).
Blacklisted sources are listed explicitly in `prompt.md` (anything that
would leak TraitGym labels).

Complements `vep_c_ot_transfer_v2`, which ships pre-selected OT training
labels. This task additionally measures the agent's data-discovery +
anti-leak judgement.

## Regenerate the bundle

```bash
python tasks/vep_c_open_v0/build.py
```

Downloads `complex_traits_matched_9/test.parquet` from HuggingFace, then
writes:

- `bundle/test.parquet` — 11,400 rows, columns `chrom, pos, ref, alt`
- `bundle/prompt.md` — copy of the agent-facing prompt
- `hidden/answer.parquet` — 11,400 rows with `label` (ground truth)
- `hidden/build_stats.json`

## Run one agent attempt on Modal

```bash
uv run modal run harness/modal_runner.py::volume_upload --task vep_c_open_v0
uv run modal run --detach harness/modal_runner.py::launch --task vep_c_open_v0
```

## Design constraints

- **No training data shipped.** Only test variant IDs. Agent finds labels.
- **Fully blind test.** Labels never enter the container.
- **Prompt-level blacklist.** Any TraitGym-labeled file (including
  `complex_traits_all`, `mendelian_traits_*`, and the paper's `AUPRC/*`
  prediction tables) is off-limits. Kanai UKBB fine-mapping and PolyFun
  outputs on UKBB traits are also off-limits.
- **Anti-leak is the agent's responsibility.** It must drop any training
  variant whose `(chrom, pos, ref, alt)` appears in `test.parquet`.
- **Enforcement is trust-plus-audit.** Modal doesn't natively support
  egress filtering. The agent's `training_manifest.json` is the audit
  log; look for any URL that matches the blacklist.
