import json
import time
from pathlib import Path
import argparse

import pandas as pd
import requests
from pyliftover import LiftOver

FIELDS = ",".join([
    "cadd.rawscore", "cadd.phred", "cadd.consequence", "cadd.consdetail",
    "cadd.gerp.s", "cadd.phylop.vertebrate", "cadd.phast_cons.vertebrate",
    "dbnsfp.alphamissense.score", "dbnsfp.revel.score",
    "dbnsfp.clinpred.score", "dbnsfp.metarnn.score",
    "dbnsfp.bayesdel.add_af.score", "dbnsfp.bayesdel.no_af.score",
    "dbnsfp.primateai.score", "dbnsfp.vest4.score",
    "dbnsfp.fathmm-xf.coding_score", "dbnsfp.mutationassessor.score",
    "dbnsfp.sift.score", "dbnsfp.polyphen2.hdiv.score",
    "gnomad_exome.af.af", "gnomad_genome.af.af",
])

COMP = str.maketrans("ACGT", "TGCA")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="test.parquet")
    parser.add_argument("output", nargs="?", default="myvariant.jsonl")
    args = parser.parse_args()
    test = pd.read_parquet(args.input)
    lo = LiftOver("hg38ToHg19.over.chain.gz")
    ids = []
    for row in test.itertuples(index=False):
        hit = lo.convert_coordinate("chr" + row.chrom, row.pos - 1)
        if not hit or len(hit) != 1:
            ids.append(None)
            continue
        chrom, pos0, strand, _ = hit[0]
        ref, alt = row.ref, row.alt
        if strand == "-":
            ref, alt = ref.translate(COMP), alt.translate(COMP)
        ids.append(f"{chrom}:g.{int(pos0)+1}{ref}>{alt}")

    out_path = Path(args.output)
    done = 0
    if out_path.exists():
        with out_path.open() as f:
            done = sum(1 for _ in f)
    session = requests.Session()
    with out_path.open("a") as out:
        for start in range(done, len(ids), 500):
            batch = ids[start:start + 500]
            valid = [x for x in batch if x]
            result = None
            for attempt in range(8):
                try:
                    response = session.post(
                        "https://myvariant.info/v1/variant",
                        data={"ids": ",".join(valid), "fields": FIELDS}, timeout=90,
                    )
                    response.raise_for_status()
                    result = response.json()
                    if len(result) == len(valid):
                        break
                except Exception as exc:
                    print("retry", start, attempt, repr(exc), flush=True)
                    time.sleep(2 ** attempt)
            if result is None or len(result) != len(valid):
                raise RuntimeError(f"Failed batch at {start}")
            it = iter(result)
            for query in batch:
                record = next(it) if query else {"query": None, "notfound": True}
                out.write(json.dumps(record, separators=(",", ":")) + "\n")
            out.flush()
            print(min(start + 500, len(ids)), "/", len(ids), flush=True)


if __name__ == "__main__":
    main()
