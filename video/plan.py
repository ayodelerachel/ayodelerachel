# Shot planner: 100 BPM, eighth = 9 frames @30fps. 8 bars = 576 frames.
import json, sys
FPS=30
clean={'A':(0.2,7.35),'B':(8.75,17.35),'C':(18.65,27.4),'D':(28.7,37.95)}
busy=[9]*8; phr=[9,9,18,9,9,18]
bars=[busy,phr,busy,phr,busy,phr,busy,[9,9,9,9,36]]
durs=[d for b in bars for d in b]
order_cycle="ABDCBADCADBCDBAC"  # never repeats a room back-to-back
seq=[order_cycle[i%len(order_cycle)] for i in range(len(durs))]
seq[-1]='D'  # hero: face lamp close-up
assert all(seq[i]!=seq[i+1] for i in range(len(seq)-1))
# per clip: which shots, then spread them across the push-in, alternating wide/close
shots=[None]*len(durs)
for c,(a,b) in clean.items():
    idx=[i for i,s in enumerate(seq) if s==c]
    tot=sum(durs[i] for i in idx)/FPS
    gap=((b-a)-tot)/max(1,len(idx)-1) if len(idx)>1 else 0
    slots=[];t=a
    for i in idx:  # chronological slots, in order of need
        slots.append(t); t+=durs[i]/FPS+gap
    n=len(slots)
    # interleave: wide, close, mid-wide, mid-close ... (last shot of D stays the closest)
    perm=[];lo,hi=0,n-1
    while lo<=hi:
        perm.append(lo); lo+=1
        if lo<=hi: perm.append(hi); hi-=1
    if c=='D': perm.remove(n-1); perm.append(n-1)
    # slots sized by the shot that will use them: recompute with permuted durations
    ordered=[idx[k] for k in range(n)]
    sizes=[durs[i] for i in ordered]
    # assign shot ordered[k] -> slot rank perm[k]; rebuild times so sizes fit
    rank_dur=[0]*n
    for k,r in enumerate(perm): rank_dur[r]=sizes[k]
    tot=sum(rank_dur)/FPS; gap=((b-a)-tot)/max(1,n-1)
    starts=[];t=a
    for r in range(n): starts.append(t); t+=rank_dur[r]/FPS+gap
    for k,r in enumerate(perm): shots[ordered[k]]=(c,round(starts[r],3),sizes[k])
for s in shots: print(*s)
print(len(shots),sum(durs),file=sys.stderr)
