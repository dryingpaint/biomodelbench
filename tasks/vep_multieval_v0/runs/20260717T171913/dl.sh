set -e
base=https://hgdownload.soe.ucsc.edu/goldenPath/hg38
for f in \
  phyloP470way/hg38.phyloP470way.bw \
  phastCons470way/hg38.phastCons470way.bw \
  phyloP100way/hg38.phyloP100way.bw \
  phastCons100way/hg38.phastCons100way.bw ; do
  out=$(basename $f)
  echo "START $out $(date)"
  curl -s -o /task/$out $base/$f
  echo "DONE $out $(date) size=$(stat -c%s /task/$out)"
done
echo "ALL DONE"
