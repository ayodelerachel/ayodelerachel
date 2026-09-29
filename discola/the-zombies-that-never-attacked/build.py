import subprocess, sys
FPS=30
# (timeline_start, src_in, speed, note, dissolve_in_seconds)
EDL=[
(0.00,  0.00,1,"A street 2:13AM - government called them infected",0),
(2.20,  4.60,1,"B silhouettes - media called them zombies",0),
(3.10, 12.55,1,"F faces",0),
(4.00,  6.00,1,"C onlookers - nobody could explain",0),
(5.40, 15.15,1,"H officer",0),
(6.70, 13.48,1,"G walking past police - didn't chase anyone",0),
(8.30,  8.48,1,"D police car - didn't attack",0),
(9.80, 16.74,1,"I group walking - simply started walking",0),
(11.48,18.45,1,"J hood POV - by sunrise",0),
(12.95,22.03,1,"L aerial crosswalk - THOUSANDS of them",0),
(14.42,27.00,1,"O bridge - all moving same direction",0),
(15.95,28.54,1,"P road out of city",0),
(17.09,30.04,1,"Q control room - authorities / evacuation",0),
(18.40,33.50,1,"S CCTV",0),
(20.05,35.18,1,"T silhouettes - realized something wrong",0),
(21.00,38.52,1,"V red alert map",0),
(22.30,31.43,1,"R map converge - every group same place",0),
(24.35,40.04,1,"W field on screen",0),
(25.44,45.47,1,"Z field map marker - abandoned field 12km",0),
(27.38,47.40,1,"AA silhouettes",0),
(29.10,50.05,1,"AB Elias ops - investigator Elias Ward",0),
(32.30,60.30,1,"AE SUV field - when he arrived",0.4),
(33.40,65.05,1,"AH Elias back, infected in fog",0),
(34.45,68.50,1,"AJ aerial SUV + hundreds",0),
(35.63,70.08,1,"AK digging hold - then they started digging",0),
(39.73,75.42,1,"AL Elias watches - six hours",0),
(41.74,80.08,1,"AN daylight digging - never stopped",0.5),
(43.07,85.50,1,"AP close shovels - never spoke",0),
(44.28,82.98,1,"AO Elias tablet - Ward noticed",0),
(46.78,92.98,1,"AS satellite - holes weren't random",0),
(49.00,96.70,1,"AT pattern on tablet - forming a pattern",0),
(50.82,98.55,1,"AU Elias in car",0),
(51.49,100.08,1,"AV Elias computers - geological scans",0),
(53.25,104.37,1,"AW scan ring",0),
(54.94,106.08,1,"AX Elias close - not on any modern map",0),
(56.93,108.08,1,"AY Elias computers",0),
(58.92,110.08,1,"AZ reading record - documented once before",0),
(61.34,112.51,1,"BA 1968 aerial photo",0),
(63.83,116.02,1,"BB tablet compare - record disappeared",0),
(65.50,118.08,1,"BC Elias lamp",0),
(67.48,74.19,1,"AK tail digging - then... without warning",0),
(68.68,81.93,0.96,"AN tail digging",0),
(69.77,120.07,1,"BD standing still - they stopped",0),
(71.72,124.04,0.74,"BF Elias at hole - looked into the hole",0),
(73.86,127.75,0.80,"BG Elias descends - found something underneath",0),
(75.86,87.44,0.62,"AQ Elias looking down - buried for decades",0),
(80.08,23.52,0.78,"M infected faces - not looking for food",0),
(82.55,67.01,0.74,"AI fog walkers - not trying to escape",0),
(84.50,122.04,0.71,"BE dust hole - looking for something",0),
(87.30,129.35,0.61,"BG walkers -> aerial pattern - whatever was buried / find it",0),
(95.10,None,1,"black - final line",0),
(98.40,135.70,1,"source DISCOLA logo",0),
(105.30,None,1,"END",0),
]
fr=lambda t: round(t*FPS)
parts=[];labels=[]
for i,(t,src,sp,note,d) in enumerate(EDL[:-1]):
    n=fr(EDL[i+1][0])-fr(t)
    if src is None:
        parts.append(f"color=c=black:s=1920x1080:r=30,trim=end_frame={n},setsar=1,format=yuv420p,fps=30,settb=1/30[v{i}]");continue
    pre=round(d*FPS)  # extra head frames for dissolve overlap
    s=src
    dur=(n+pre)/FPS*sp+0.2
    f=f"[0:v]trim=start={s:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS"
    if sp!=1: f+=f",setpts=PTS/{sp},minterpolate=fps=30:mi_mode=blend"
    else: f+=",fps=30"
    f+=f",trim=end_frame={n+pre},setpts=PTS-STARTPTS,setsar=1,format=yuv420p,fps=30,settb=1/30[v{i}]"
    parts.append(f)
# chain
cur="v0"; curlen=fr(EDL[1][0])
for i in range(1,len(EDL)-1):
    d=EDL[i][4]; pre=round(d*FPS)
    if pre:
        parts.append(f"[{cur}][v{i}]xfade=transition=fade:duration={pre/FPS:.4f}:offset={(curlen-pre)/FPS:.4f},settb=1/30[c{i}]")
    else:
        parts.append(f"[{cur}][v{i}]concat=n=2:v=1:a=0,fps=30,settb=1/30[c{i}]")
    cur=f"c{i}"; curlen=fr(EDL[i+1][0])
grade=("eq=contrast=1.05:saturation=0.88:gamma=1.02,"
       "colorbalance=rs=-0.02:gs=0:bs=0.035:rm=-0.015:bm=0.02:rh=-0.01:bh=0.01,"
       "vignette=angle=PI/7")
fade=f"fade=t=in:st=0:d=0.25,fade=t=out:st=93.90:d=1.2:color=black"
# logo segment must not be faded by out-fade -> apply fade only to first 95.1s via split
parts.append(f"[{cur}]{grade}[g]")
parts.append("[g]split[g1][g2]")
parts.append(f"[g1]trim=end=98.4,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.25,fade=t=out:st=93.9:d=1.2[pa]")
parts.append("[g2]trim=start=98.4,setpts=PTS-STARTPTS[pb]")
parts.append("[pa][pb]concat=n=2:v=1:a=0,ass=labels.ass,format=yuv420p[vout]")
aud=("[1:a]aresample=48000,highpass=f=70,afftdn=nf=-48:nr=8,"
     "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=180:makeup=2,"
     "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=-21.27:measured_TP=-2.56:measured_LRA=4.60:measured_thresh=-31.93:offset=0.48:linear=true,aresample=48000,pan=stereo|c0=0.7071*c0|c1=0.7071*c0,apad,atrim=end=105.3[aout]")
parts.append(aud)
open("graph.txt","w").write(";\n".join(parts))
cmd=["ffmpeg","-hide_banner","-y","-i","src.mp4","-i","narr.mp3","-filter_complex_script","graph.txt",
 "-map","[vout]","-map","[aout]","-c:v","libx264","-profile:v","high","-pix_fmt","yuv420p","-preset","slow","-crf","17",
 "-r","30","-fps_mode","cfr","-g","60","-bf","2","-movflags","+faststart",
 "-c:a","aac","-b:a","224k","-ar","48000","-ac","2","-t","105.3",
 "-color_primaries","bt709","-color_trc","bt709","-colorspace","bt709",sys.argv[1] if len(sys.argv)>1 else "out.mp4"]
subprocess.run(cmd,check=True)
