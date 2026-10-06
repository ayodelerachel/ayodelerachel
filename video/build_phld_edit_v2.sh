#!/bin/bash
# Beat-synced PHLD edit: 100 BPM, cuts on eighth notes (9 frames @30fps), original synthesized score.
set -e
SRC=$1; OUT=$2; D=$(dirname "$0")
declare -A G=( [A]=1.05 [B]=0.98 [C]=0.98 [D]=1.16 )
declare -A DU=( [A]=-0.5 [B]=1 [C]=-0.7 [D]=0.5 )
declare -A DV=( [A]=1.3 [B]=-0.9 [C]=1.3 [D]=-0.8 )
GRADE="curves=all='0/0.02 0.25/0.22 0.5/0.5 0.75/0.79 1/0.97',colorbalance=rm=0.025:bm=-0.03:rh=0.01:bh=-0.015,eq=saturation=0.94"
W=$(mktemp -d); i=0
python3 -I "$D/plan.py" > $W/shots.txt
while read c ss n; do
  i=$((i+1)); o=$(printf "$W/%02d.mp4" $i)
  ffmpeg -nostdin -v error -y -ss $ss -i "$SRC" -frames:v $n -an \
    -vf "eq=gamma=${G[$c]},lutyuv=u='val+${DU[$c]}':v='val+${DV[$c]}',$GRADE,format=yuv420p" \
    -c:v libx264 -crf 8 -preset fast -r 30 "$o"
  echo "file '$o'" >> $W/list.txt
done < $W/shots.txt
python3 -I "$D/music.py" $W/music.wav
ffmpeg -nostdin -v error -y -f concat -safe 0 -i $W/list.txt -i $W/music.wav \
  -map 0:v -map 1:a -af "loudnorm=I=-14:TP=-1.5:LRA=7" -ar 48000 -c:a aac -b:a 256k \
  -c:v libx264 -crf 16 -preset slow -profile:v high -pix_fmt yuv420p -r 30 -shortest -movflags +faststart "$OUT"
rm -rf $W
