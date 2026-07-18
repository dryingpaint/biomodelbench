#!/bin/bash
cd /task
# Branch A: wait for VEP -> parse -> ESM (GPU)
(
  until grep -q "DONE collected" /task/data/vep_run.log 2>/dev/null; do sleep 15; done
  echo "[A] VEP done, parsing" > /task/data/orch_A.log
  python3 parse_vep.py >> /task/data/orch_A.log 2>&1
  echo "[A] running ESM" >> /task/data/orch_A.log
  python3 esm_score.py >> /task/data/orch_A.log 2>&1
  echo "[A] DONE" >> /task/data/orch_A.log
) &
PIDA=$!
# Branch B: wait for 241m download -> extract conservation (CPU)
(
  until [ "$(stat -c%s /task/cons/phyloP241m.bw 2>/dev/null)" -ge 21880000000 ]; do sleep 20; done
  echo "[B] 241m done, extracting conservation" > /task/data/orch_B.log
  python3 extract_cons.py >> /task/data/orch_B.log 2>&1
  echo "[B] DONE" >> /task/data/orch_B.log
) &
PIDB=$!
wait $PIDA $PIDB
echo "[ALL] branches done, combining" > /task/data/orch_final.log
python3 combine.py >> /task/data/orch_final.log 2>&1
echo "[ALL] DONE" >> /task/data/orch_final.log
