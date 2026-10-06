#!/bin/bash
set -e
SRC=/root/.claude/uploads/926d8bad-352d-5e27-80fd-f1c2dfc0368a/866dbe8d-PHLD_6_1.mp4
S=/tmp/claude-0/-home-user-ayodelerachel/926d8bad-352d-5e27-80fd-f1c2dfc0368a/scratchpad
# per-clip match (gamma, U offset, V offset) toward a common look
declare -A G=( [A]=1.05 [B]=0.98 [C]=0.98 [D]=1.16 )
declare -A DU=( [A]=-0.5 [B]=1 [C]=-0.7 [D]=0.5 )
declare -A DV=( [A]=1.3 [B]=-0.9 [C]=1.3 [D]=-0.8 )
# unified cinematic grade: gentle S-curve, soft warm mids, slightly restrained saturation
GRADE="curves=all='0/0.02 0.25/0.22 0.5/0.5 0.75/0.79 1/0.97',colorbalance=rm=0.025:bm=-0.03:rh=0.01:bh=-0.015,eq=saturation=0.94"
# clip start(s) frames
SHOTS="A 0.2 21
B 9.0 15
D 29.0 15
C 18.8 15
A 3.6 18
B 13.0 18
D 33.0 18
C 23.0 18
A 6.6 24
B 10.6 18
C 20.6 18
D 30.8 18
B 16.4 24
A 1.6 18
D 35.2 21
C 25.6 24
B 11.8 15
D 36.9 30"
rm -f $S/shots/*.mp4 $S/list.txt; i=0
while read c ss n; do
  i=$((i+1)); o=$(printf "$S/shots/%02d.mp4" $i)
  ffmpeg -nostdin -v error -y -ss $ss -i "$SRC" -frames:v $n -an \
    -vf "eq=gamma=${G[$c]},lutyuv=u='val+${DU[$c]}':v='val+${DV[$c]}',$GRADE,format=yuv420p" \
    -c:v libx264 -crf 8 -preset fast -r 30 "$o"
  echo "file '$o'" >> $S/list.txt
done <<< "$SHOTS"
ffmpeg -v error -y -f concat -safe 0 -i $S/list.txt -c:v libx264 -crf 16 -preset slow -profile:v high -pix_fmt yuv420p -r 30 -movflags +faststart "$1"
