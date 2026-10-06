# Builds one 3D LUT per clip: full match to a shared target + a stronger shared cinematic look.
import sys, subprocess, numpy as np
src, outdir = sys.argv[1], sys.argv[2]
FPS=30
segs=[(0,7.8),(9.0,17.5),(18.9,27.7),(29.0,38.0)]
LUM=np.array([0.2126,0.7152,0.0722],np.float32)
proxy=subprocess.run(['ffmpeg','-v','error','-i',src,'-vf','scale=108:192','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True).stdout
a=np.frombuffer(proxy,np.uint8).reshape(-1,192,108,3).astype(np.float32)/255
T=dict(rg=1.14,bg=0.82,med=0.50,std=0.185,sat=0.145)
def match_params(x):
    m=x.reshape(-1,3).mean(0)
    gR=T['rg']/(m[0]/m[1]); gB=T['bg']/(m[2]/m[1])
    xb=np.clip(x*np.array([gR,1,gB]),0,1); y=xb@LUM
    gam=np.log(T['med'])/np.log(np.median(y))
    y2=y**gam; con=T['std']/y2.std()
    sg=T['sat']/(xb.max(-1)-xb.min(-1)).mean()
    return gR,gB,gam,con,sg
def smooth(e0,e1,v):
    u=np.clip((v-e0)/(e1-e0),0,1); return u*u*(3-2*u)
def look(x):
    y=x@LUM
    # filmic S-curve: richer contrast, matte black floor, soft highlight shoulder
    yc=np.clip(y,0,1)
    s=yc+1.0*yc*(1-yc)*(yc-0.5)          # S-curve
    s=np.where(s>0.82,0.82+(s-0.82)*0.75,s) # shoulder roll-off (protect lamp glow)
    s=0.030+s*(0.985-0.025)/ (0.82+0.18*0.75)
    out=x*((s+1e-4)/(y+1e-4))[...,None]
    yo=out@LUM
    hi=smooth(0.45,0.95,yo)[...,None]; mid=(1-np.abs(yo-0.45)/0.45).clip(0,1)[...,None]; lo=smooth(0.40,0.0,yo)[...,None]
    out=out*(1+hi*np.array([0.075,0.020,-0.085]))          # amber highlights
    out=out*(1+mid*np.array([0.035,0.006,-0.050]))         # warm mids
    out=out+lo*np.array([0.012,0.004,-0.010])              # warm-brown shadows, never teal
    yy=(out@LUM)[...,None]
    return np.clip(yy+(out-yy)*0.94,0,1)                   # refined, slightly restrained saturation
def grade(x,p):
    gR,gB,gam,con,sg=p
    x=np.clip(x*np.array([gR,1,gB],np.float32),0,1); y=x@LUM
    y2=np.power(np.clip(y,1e-5,1),gam)
    y3=np.clip(0.5+(y2-0.5)*con,0,1)
    hp=np.clip((y2-0.85)/0.15,0,1); y3=y3*(1-hp)+np.maximum(y3,y2)*hp
    x=x*((y3+1e-4)/(y+1e-4))[...,None]
    yy=(x@LUM)[...,None]; x=yy+(x-yy)*sg
    return look(np.clip(x,0,1))
N=33; g=np.linspace(0,1,N,dtype=np.float32)
b,gg,r=np.meshgrid(g,g,g,indexing='ij')   # R varies fastest in .cube
cube=np.stack([r,gg,b],-1).reshape(-1,3)
for i,(s,e) in enumerate(segs):
    p=match_params(a[int(s*FPS):int(e*FPS)])
    print('clip',i+1,'gR %.3f gB %.3f gamma %.3f con %.3f sat %.3f'%p)
    o=grade(cube,p)
    with open(f'{outdir}/clip{i+1}.cube','w') as f:
        f.write(f'LUT_3D_SIZE {N}\n'); f.writelines('%.6f %.6f %.6f\n'%tuple(v) for v in o)
