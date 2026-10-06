import sys, subprocess, numpy as np
src, out, mode = sys.argv[1], sys.argv[2], sys.argv[3]  # mode: full | stills
W,H,FPS=1080,1920,30
segs=[(0,7.8),(9.0,17.5),(18.9,27.7),(29.0,38.0)]
# dissolve windows (start,end) between consecutive segments
dis=[(7.8,9.0),(17.5,18.9),(27.7,29.0)]
LUM=np.array([0.2126,0.7152,0.0722])
# ---- analysis on a small proxy
proxy=subprocess.run(['ffmpeg','-v','error','-i',src,'-vf','scale=108:192','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True).stdout
a=np.frombuffer(proxy,np.uint8).reshape(-1,192,108,3).astype(np.float32)/255
T=dict(rg=1.15,bg=0.83,med=0.505,std=0.180,sat=0.145)
params=[]
for s,e in segs:
    x=a[int(s*FPS):int(e*FPS)]
    m=x.reshape(-1,3).mean(0)
    k=0.85
    gR=(T['rg']/(m[0]/m[1]))**k; gB=(T['bg']/(m[2]/m[1]))**k
    xb=np.clip(x*np.array([gR,1,gB]),0,1)
    y=xb@LUM
    med=np.median(y)
    gam=(np.log(T['med'])/np.log(med))
    gam=gam**0.75
    y2=y**gam
    sd=y2.std()
    con=(T['std']/sd)**0.6
    sat=((xb.max(-1)-xb.min(-1)).mean())
    sg=(T['sat']/sat)**0.7
    params.append(np.array([gR,gB,gam,con,sg],np.float32))
    print('seg',s,e,'gR %.3f gB %.3f gamma %.3f con %.3f sat %.3f'%tuple(params[-1]),file=sys.stderr)
P=np.stack(params)
def weights(t):
    w=np.zeros(4,np.float32)
    for i,(d0,d1) in enumerate(dis):
        if t<d0: w[i]=1; return w
        if t<d1:
            u=(t-d0)/(d1-d0); u=u*u*(3-2*u)
            w[i]=1-u; w[i+1]=u; return w
    w[3]=1; return w
# ---- shared cinematic look (applied after matching)
def look(rgb):
    # soft filmic tone curve: gentle toe lift, smooth shoulder to protect fixture glow
    y=rgb@LUM
    def curve(v):
        v=np.clip(v,0,1)
        s=v+0.10*v*(1-v)*(v-0.5)*4*(-1)*-1  # mild S around mid
        s=0.018+(1-0.018-0.012)*s          # lifted blacks, softened whites
        return s
    yc=curve(y)
    out=rgb*((yc+1e-4)/(y+1e-4))[...,None]
    # split warmth: amber in highlights, neutral-warm shadows
    hi=np.clip((yc-0.45)/0.55,0,1)[...,None]; lo=np.clip((0.40-yc)/0.40,0,1)[...,None]
    out=out*(1+hi*np.array([0.018,0.004,-0.022],np.float32))+lo*np.array([0.006,0.002,-0.004],np.float32)
    return np.clip(out,0,1)
def grade(f,t):
    p=weights(t)@P
    gR,gB,gam,con,sg=p
    x=f*np.array([gR,1,gB],np.float32)
    x=np.clip(x,0,1)
    y=x@LUM
    y2=np.power(np.clip(y,1e-5,1),gam)
    m=0.5
    y3=np.clip(m+(y2-m)*con,0,1)
    # soft highlight protection: blend back toward y2 near the top to avoid clipping lamps
    hp=np.clip((y2-0.85)/0.15,0,1); y3=y3*(1-hp)+np.maximum(y3,y2)*hp
    x=x*((y3+1e-4)/(y+1e-4))[...,None]
    yy=(x@LUM)[...,None]
    x=yy+(x-yy)*sg
    return look(np.clip(x,0,1))
if mode=='stills':
    for t in [float(v) for v in sys.argv[4].split(',')]:
        raw=subprocess.run(['ffmpeg','-v','error','-ss',str(t),'-i',src,'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True).stdout
        f=np.frombuffer(raw,np.uint8).reshape(H,W,3).astype(np.float32)/255
        g=(grade(f,t)*255+0.5).astype(np.uint8)
        np.concatenate([f*255,g],1).astype(np.uint8).tofile(f'{out}_{t}.rgb')
    sys.exit()
dec=subprocess.Popen(['ffmpeg','-v','error','-i',src,'-pix_fmt','rgb48le','-f','rawvideo','-'],stdout=subprocess.PIPE)
enc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb48le','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
 '-c:v','libx264','-preset','slow','-crf','14','-pix_fmt','yuv420p','-profile:v','high','-tune','film',
 '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',out],stdin=subprocess.PIPE)
n=0; fs=W*H*3*2
rng=np.random.default_rng(0)
while True:
    b=dec.stdout.read(fs)
    if len(b)<fs: break
    f=np.frombuffer(b,np.uint16).reshape(H,W,3).astype(np.float32)/65535
    g=grade(f,n/FPS)
    enc.stdin.write((g*65535+0.5).astype(np.uint16).tobytes()); n+=1
enc.stdin.close(); enc.wait(); print('frames',n,file=sys.stderr)
