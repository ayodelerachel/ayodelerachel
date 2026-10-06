# Clean clip sections (dissolves removed), natural speed, joined by a soft focus-pull transition:
# outgoing room defocuses, incoming room comes into focus, swap happens while both are soft.
import sys, subprocess, numpy as np, cv2
src, lutdir, out = sys.argv[1:4]
W,H,FPS=1080,1920,30
clean=[(0,222),(290,508),(588,812),(890,1139)]
N=24; PEAK=26.0
def ss(e0,e1,v):
    u=min(max((v-e0)/(e1-e0),0),1); return u*u*(3-2*u)
def blur(f,s): return f if s<0.3 else cv2.GaussianBlur(f,(0,0),s)
enc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb48le','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
 '-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p','-tune','film',
 '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',out],stdin=subprocess.PIPE)
fs=W*H*3*2; total=0; tail=[]
def emit(f):
    global total; enc.stdin.write(np.clip(f,0,65535).astype(np.uint16).tobytes()); total+=1
for k,(s,e) in enumerate(clean):
    dec=subprocess.Popen(['ffmpeg','-v','error','-i',src,'-vf',
        f"select='between(n,{s},{e})',setpts=N/{FPS}/TB,format=gbrp16le,lut3d={lutdir}/clip{k+1}.cube:interp=tetrahedral",
        '-pix_fmt','rgb48le','-f','rawvideo','-'],stdout=subprocess.PIPE)
    frames=iter(lambda: dec.stdout.read(fs),b'')
    n=e-s+1; i=0; newtail=[]
    for b in frames:
        if len(b)<fs: break
        f=np.frombuffer(b,np.uint16).reshape(H,W,3).astype(np.float32)
        if k>0 and i<N:                       # transition: blend with held tail of previous clip
            u=(i+0.5)/N
            fo=blur(tail[i],PEAK*ss(0.0,0.5,u)); fi=blur(f,PEAK*(1-ss(0.5,1.0,u)))
            w=ss(0.3,0.7,u); g=1+0.05*np.sin(np.pi*u)
            emit((fo*(1-w)+fi*w)*g)
        elif k<3 and i>=n-N: newtail.append(f)
        else: emit(f)
        i+=1
    dec.wait(); tail=newtail
enc.stdin.close(); enc.wait(); print('frames',total,'seconds',total/FPS,file=sys.stderr)
