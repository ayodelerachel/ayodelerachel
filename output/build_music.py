# Original ambient piano + warm pad score, chord changes aligned to the room transitions.
import sys, numpy as np, wave
from scipy.signal import fftconvolve, butter, sosfilt
SR=48000; DUR=28.17
out=sys.argv[1]
rng=np.random.default_rng(7)
def hz(m): return 440*2**((m-69)/12)
# sections: (start, end, chord midi notes, bass root)
D,Fs,A,Cs,E,B,G=62,66,69,73,76,59,67
secs=[(0.0,7.02,[62,66,69,73,76],38),            # Dmaj9
      (7.02,13.52,[59,62,66,69,73],35),          # Bm9
      (13.52,20.22,[55,59,62,66,69],43),         # Gmaj9
      (20.22,24.6,[52,55,59,62,66],40),          # Em9
      (24.6,DUR,[57,61,64,66,71],45)]            # A6/9 -> soft lift, resolves on fade
t=np.arange(int(SR*DUR))/SR
L=np.zeros_like(t); R=np.zeros_like(t)
def env_adsr(n,a,r):
    e=np.ones(n); na=int(a*SR); nr=int(r*SR)
    e[:na]=np.linspace(0,1,na)**2; e[-nr:]*=np.linspace(1,0,nr)**2; return e
# warm pad: detuned soft partials, slow swell, crossfaded chords
for s,e,ch,_ in secs:
    i0=max(0,int((s-0.8)*SR)); i1=min(len(t),int((e+0.8)*SR)); n=i1-i0; tt=t[i0:i1]
    env=env_adsr(n,1.6,1.6)
    for m in ch[:4]:
        for det,pan in ((-0.07,0.3),(0.07,0.7)):
            f=hz(m-12)*2**(det/12)
            w=np.sin(2*np.pi*f*tt+rng.uniform(0,6))+0.25*np.sin(4*np.pi*f*tt)+0.08*np.sin(6*np.pi*f*tt)
            w*=env*(1+0.15*np.sin(2*np.pi*0.13*tt+rng.uniform(0,6)))*0.018
            L[i0:i1]+=w*(1-pan); R[i0:i1]+=w*pan
# soft sub bass
for s,e,_,root in secs:
    i0=int(s*SR); i1=min(len(t),int((e+0.5)*SR)); n=i1-i0; tt=t[i0:i1]
    w=np.sin(2*np.pi*hz(root)*tt)*env_adsr(n,0.8,1.2)*0.05
    L[i0:i1]+=w; R[i0:i1]+=w
# felt-piano voice
def piano(m,start,vel,pan):
    f0=hz(m); n=int(4.5*SR); i0=int(start*SR); n=min(n,len(t)-i0)
    if n<=0: return
    tt=np.arange(n)/SR; w=np.zeros(n)
    for k in range(1,9):
        fk=f0*k*np.sqrt(1+0.0004*k*k)
        w+=np.sin(2*np.pi*fk*tt)*(1/k**1.6)*np.exp(-tt*(0.9+0.55*k))
    att=np.minimum(1,tt/0.006); w*=att*vel*0.07
    L[i0:i0+n]+=w*(1-pan); R[i0:i0+n]+=w*pan
# sparse arpeggio, gentle rubato
for si,(s,e,ch,_) in enumerate(secs):
    pattern=[0,2,4,3,1,2,4,3] if si%2==0 else [1,3,4,2,0,3,4,2]
    step=0.82; x=s+0.15 if si else 0.6; j=0
    while x<e-0.3 and x<DUR-2.4:
        m=ch[pattern[j%8]]+(12 if j%8 in (2,6) else 0)
        piano(m,x+rng.normal(0,0.012),0.75+0.25*rng.random()-(0.15 if j%2 else 0),0.35+0.3*rng.random())
        x+=step; j+=1
piano(62,DUR-2.4,0.8,0.5); piano(69,DUR-2.38,0.6,0.45); piano(74,DUR-2.35,0.55,0.55)   # final resolve on D
# stereo hall reverb
irn=int(3.2*SR); it=np.arange(irn)/SR
sos=butter(2,4500,fs=SR,output='sos')
irL=sosfilt(sos,rng.normal(0,1,irn))*np.exp(-it*2.1); irR=sosfilt(sos,rng.normal(0,1,irn))*np.exp(-it*2.1)
irL[:int(0.02*SR)]=0; irR[:int(0.025*SR)]=0
wetL=fftconvolve(L,irL)[:len(t)]; wetR=fftconvolve(R,irR)[:len(t)]
wetL/=np.abs(wetL).max(); wetR/=np.abs(wetR).max()
dry=max(np.abs(L).max(),np.abs(R).max())
L=L/dry*0.7+wetL*0.45; R=R/dry*0.7+wetR*0.45
# gentle warmth (low-pass), fades, normalize to -1 dBFS peak
lp=butter(1,9000,fs=SR,output='sos'); L=sosfilt(lp,L); R=sosfilt(lp,R)
fade=np.ones_like(t); fi=int(1.2*SR); fo=int(2.6*SR)
fade[:fi]=np.linspace(0,1,fi)**2; fade[-fo:]=np.linspace(1,0,fo)**1.5
L*=fade; R*=fade
pk=max(np.abs(L).max(),np.abs(R).max()); g=10**(-1/20)/pk
st=(np.stack([L,R],1)*g*32767).astype(np.int16)
with wave.open(out,'wb') as wf:
    wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(st.tobytes())
