# Original instrumental, 100 BPM, 8 bars (19.2s) + short tail. Warm minimal deep-house / lounge.
import numpy as np, sys
from scipy.signal import fftconvolve, butter, sosfilt
from scipy.io import wavfile
SR=48000; BPM=100; BEAT=60/BPM; BAR=4*BEAT; NB=8
L=int(SR*(NB*BAR+0.0)); rng=np.random.default_rng(7)
def t_(d): return np.arange(int(SR*d))/SR
def add(buf,sig,at,g=1.0):
    i=int(at*SR); j=min(len(buf),i+len(sig)); buf[i:j]+=g*sig[:j-i]
def lp(x,f,o=2): return sosfilt(butter(o,f,'low',fs=SR,output='sos'),x)
def hp(x,f,o=2): return sosfilt(butter(o,f,'high',fs=SR,output='sos'),x)
def bp(x,a,b): return sosfilt(butter(2,[a,b],'band',fs=SR,output='sos'),x)
mtof=lambda m:440*2**((m-69)/12)
kick=np.zeros(L); hats=np.zeros(L); clap=np.zeros(L); bass=np.zeros(L); keys=np.zeros(L); pad=np.zeros(L); perc=np.zeros(L)
# drum voices
tk=t_(0.45); ph=2*np.pi*np.cumsum(48+90*np.exp(-tk*30))/SR
K=np.sin(ph)*np.exp(-tk*7.5); K+=0.15*np.exp(-tk*400)*rng.standard_normal(len(tk)); K=np.tanh(1.6*K)
th=t_(0.09); H=lp(hp(rng.standard_normal(len(th)),7500),13000)*np.exp(-th*55)
tho=t_(0.3); HO=lp(hp(rng.standard_normal(len(tho)),6500),12000)*np.exp(-tho*14)
tc=t_(0.35); C=bp(rng.standard_normal(len(tc)),900,3500)*(np.exp(-tc*22)+0.4*np.exp(-np.maximum(tc-0.012,0)*22)*(tc>0.012))
tr=t_(0.12); RIM=bp(rng.standard_normal(len(tr)),1500,2500)*np.exp(-tr*60)+0.5*np.sin(2*np.pi*820*tr)*np.exp(-tr*50)
# harmony: Am9 | Fmaj9 | Cmaj9 | G6  (x2)
prog=[(45,[57,60,64,67,71]),(41,[57,60,64,65,67]),(36,[55,59,62,64,67]),(43,[55,59,62,64,67])]
def epiano(m,d):
    t=t_(d); f=mtof(m)
    s=np.sin(2*np.pi*f*t+0.8*np.exp(-t*6)*np.sin(2*np.pi*f*t))   # soft FM tine
    s+=0.25*np.sin(2*np.pi*2*f*t)*np.exp(-t*4)
    env=np.minimum(t/0.004,1)*np.exp(-t*1.6)
    return s*env*(1+0.15*np.sin(2*np.pi*4.5*t))
def padv(m,d):
    t=t_(d); s=np.zeros(len(t))
    for det in (-0.08,0.0,0.07):
        f=mtof(m+det); s+=2/np.pi*np.arcsin(np.sin(2*np.pi*f*t+rng.uniform(0,6)))
    env=np.minimum(t/0.6,1)*np.minimum((d-t)/0.4,1)
    return lp(s,1400)*env
total_beats=NB*4
for bar in range(NB):
    root,ch=prog[bar%4]; b0=bar*BAR
    last = bar==NB-1
    # pad: whole bar (and ring through the end)
    for m in ch[:4]: add(pad,padv(m,BAR+(1.2 if last else 0.25)),b0,0.05)
    # keys: syncopated stabs (on 1, and-of-2, and-of-3) — final bar: one held chord on beat 3
    hits=[0,1.5,2.5] if not last else [0,2]
    for h in hits:
        dur=1.6 if not last or h==0 else 3.0
        for m in ch: add(keys,epiano(m,dur),b0+h*BEAT,0.07 if h==0 else 0.055)
    # bass: offbeat pulses on root, octave bump in bar end
    for e in range(8):
        if last and e>=4: break
        if bar==0 and e<4: continue
        if e%2==1 or e==0:
            m=root+(12 if e==7 else 0); d=BEAT*0.45; t=t_(d)
            s=np.tanh(1.8*np.sin(2*np.pi*mtof(m)*t))*np.minimum(t/0.005,1)*np.exp(-t*5)
            add(bass,lp(s,500),b0+e*BEAT/2,0.33)
    # drums
    for bt in range(4):
        tb=b0+bt*BEAT
        if last and bt>=2:
            if bt==2: add(kick,K,tb,0.95)          # final hit lands with the hero shot
            continue
        add(kick,K,tb,0.9 if bar>0 or bt==0 else 0.75)
        if bar>=1:
            add(hats,HO,tb+BEAT/2,0.06)           # offbeat open hat
            for s16 in (0.25,0.75):
                add(hats,H,tb+s16*BEAT,0.03*(1+0.4*rng.random()))
        if bar>=2 and bt in (1,3): add(clap,C,tb,0.35)
        if bar>=4 and bt==3: add(perc,RIM,tb+0.75*BEAT,0.25)
    if bar>=2 and bar%2==1: add(perc,RIM,b0+2.25*BEAT,0.2)
# sidechain pump on pad/keys/bass from kick positions
pump=np.ones(L)
for k in range(total_beats):
    if k>=total_beats-1: break
    i=int(k*BEAT*SR); n=int(0.32*SR); tt=np.arange(n)/SR
    if k>=total_beats-2 and k!=total_beats-2: continue
    pump[i:i+n]=np.minimum(pump[i:i+n],1-0.55*np.exp(-tt*9))
def reverb(x,dec=1.8,mix=0.25):
    ti=t_(dec); ir=rng.standard_normal(len(ti))*np.exp(-ti*5/dec); ir=lp(ir,6000); ir/=np.sqrt(np.sum(ir**2))
    return x+mix*fftconvolve(x,ir)[:len(x)]
music=(kick+bass*pump+reverb(keys*pump,2.2,0.35)+reverb(pad*pump,3,0.4)+reverb(clap,1.2,0.25)+reverb(hats,0.8,0.15)+reverb(perc,1.5,0.3))
music=hp(music,30)
# gentle fade-in and outro fade over the hero hold
t=np.arange(L)/SR; music*=np.minimum(t/0.05,1)
fo=NB*BAR-0.9; music*=np.where(t>fo,np.clip(1-(t-fo)/0.9,0,1)**1.5,1)
music=np.tanh(1.2*music/np.max(np.abs(music)))
music/=np.max(np.abs(music))/0.89
st=np.stack([music,music],1)
wavfile.write(sys.argv[1],SR,(st*32767).astype(np.int16))
