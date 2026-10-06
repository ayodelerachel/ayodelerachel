# Removes the baked-in dissolves and joins the clean clip sections with hidden speed-ramp cuts:
# each clip's forward camera push accelerates into the cut, the next clip enters at the same
# speed and settles back to normal, with natural motion blur from frame averaging.
import sys, subprocess, math, numpy as np
src, lutdir, out = sys.argv[1:4]
W,H,FPS=1080,1920,30
clean=[(0,222),(290,508),(588,812),(890,1139)]   # inclusive clean frame ranges (dissolves excluded)
R=12; VMAX=4.0
def ss(u): return u*u*(3-2*u)
def schedule(n, head, tail):
    hv=[VMAX-(VMAX-1)*ss((j+0.5)/R) for j in range(R)] if head else []
    tv=[1+(VMAX-1)*ss((j+0.5)/R) for j in range(R)] if tail else []
    mid=n-sum(hv)-sum(tv); speeds=hv+[1.0]*int(round(mid))+tv
    scale=n/sum(speeds); pos=0.0; sch=[]
    for v in speeds:
        v*=scale; a,b=pos,pos+v
        idx=list(range(math.ceil(a-1e-6),math.ceil(b-1e-6))) or [min(int(round(a)),n-1)]
        sch.append([min(i,n-1) for i in idx]); pos=b
    return sch
enc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb48le','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
 '-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p','-tune','film',
 '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',out],stdin=subprocess.PIPE)
fs=W*H*3*2; total=0
for k,(s,e) in enumerate(clean):
    n=e-s+1; sch=schedule(n,k>0,k<3)
    dec=subprocess.Popen(['ffmpeg','-v','error','-i',src,'-vf',
        f"select='between(n,{s},{e})',setpts=N/{FPS}/TB,format=gbrp16le,lut3d={lutdir}/clip{k+1}.cube:interp=tetrahedral",
        '-pix_fmt','rgb48le','-f','rawvideo','-'],stdout=subprocess.PIPE)
    buf={}; nxt=0
    for idx in sch:
        while nxt<=max(idx):
            b=dec.stdout.read(fs)
            if len(b)<fs: break
            buf[nxt]=np.frombuffer(b,np.uint16).reshape(H,W,3); nxt+=1
        avail=[i for i in idx if i in buf] or [max(buf)]
        f=buf[avail[0]] if len(avail)==1 else np.mean([buf[i].astype(np.float32) for i in avail],0).round().astype(np.uint16)
        enc.stdin.write(f.tobytes()); total+=1
        for i in [i for i in buf if i<min(idx)]: del buf[i]
    dec.stdout.close(); dec.wait()
    print('clip',k+1,'src frames',n,'-> out',len(sch),file=sys.stderr)
enc.stdin.close(); enc.wait(); print('total out frames',total,file=sys.stderr)
