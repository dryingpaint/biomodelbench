#!/bin/bash
cd /task/cons
dl(){ echo "START $2 $(date +%T)"; curl -s -o "$2" "$1" && echo "DONE $2 $(date +%T) size=$(stat -c%s $2)"; }
dl "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP470way/hg38.phyloP470way.bw" phyloP470way.bw
dl "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phyloP100way/hg38.phyloP100way.bw" phyloP100way.bw
dl "https://hgdownload.soe.ucsc.edu/goldenPath/hg38/phastCons100way/hg38.phastCons100way.bw" phastCons100way.bw
echo "ALL DONE $(date +%T)"
