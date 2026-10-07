#!/usr/bin/env python3
"""Re-cut user footage to the rhythm of the "MOON - A New Mood" reference reel.

Reference pattern (measured from the sample, 30 fps, 9:16, ~7.43 s):
  flash burst (cuts every 3-4 frames) -> hold on one hero shot, repeated 4x.
Uses ONLY the supplied clips. No text, no logos, no added footage.
An original instrumental is synthesized and synced so a soft tick lands on
every flash cut and a warm pad swells under each hold.

Usage: python3 moon_edit.py OUT.mp4 clip1.mp4 clip2.mp4 ... [--loops N]
"""
import math, os, struct, subprocess, sys, tempfile, wave

import numpy as np

FPS = 30
W, H = 1080, 1920
# Cut points in frames, taken from scene detection on the reference.
CUTS = [0, 3, 6, 9, 13, 17, 20, 23, 27, 30, 34,          # burst 1
        59, 62, 66, 69, 72, 75,                          # hold 34-59, burst 2
        113, 117, 120, 124, 127, 131, 134, 138, 141, 144,  # hold 75-113, burst 3
        169, 172, 175, 179, 183, 186,                    # hold 144-169, burst 4
        223]                                             # hold 186-223 (end)
HOLD_STARTS = {34, 75, 144, 186}


def probe_duration(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path])
    return float(out)


def build_shots(clips, loops):
    """Return list of (clip, start_sec, frames, is_hold)."""
    durs = [probe_duration(c) for c in clips]
    cuts = []
    for k in range(loops):
        off = k * CUTS[-1]
        cuts += [c + off for c in (CUTS if k == 0 else CUTS[1:])]
    holds = {h + k * CUTS[-1] for k in range(loops) for h in HOLD_STARTS}
    # Holds go to the longest clips; bursts cycle through all clips,
    # sampling a different moment each time they recur.
    by_len = sorted(range(len(clips)), key=lambda i: -durs[i])
    use_count = [0] * len(clips)
    shots, hold_i, burst_i = [], 0, 0
    for a, b in zip(cuts, cuts[1:]):
        n = b - a
        is_hold = a in holds
        if is_hold:
            i = by_len[hold_i % len(by_len)]; hold_i += 1
        else:
            i = burst_i % len(clips); burst_i += 1
        need = n / FPS
        span = max(durs[i] - need - 0.05, 0)
        # spread successive picks across the clip (golden-ratio stepping)
        frac = (0.5 if is_hold and use_count[i] == 0
                else (0.15 + 0.618 * use_count[i]) % 1.0)
        use_count[i] += 1
        shots.append((clips[i], span * frac, n, is_hold))
    return shots


def render_video(shots, out_path, tmp):
    parts = []
    for k, (clip, ss, n, is_hold) in enumerate(shots):
        p = os.path.join(tmp, f"s{k:03d}.mp4")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H},fps={FPS},setsar=1")
        if is_hold:  # gentle push-in like the reference holds
            vf += (f",scale={W*2}:{H*2},zoompan=z='1+0.04*on/{n}':"
                   f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{ss:.3f}", "-i", clip,
                        "-vf", vf, "-frames:v", str(n), "-an",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                        "-pix_fmt", "yuv420p", p], check=True)
        parts.append(p)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", lst, "-c", "copy", out_path], check=True)


def synth_music(shots, wav_path, sr=44100):
    total = sum(s[2] for s in shots) / FPS
    t = np.arange(int(total * sr)) / sr
    mix = np.zeros_like(t)
    # Warm, airy pad: Dmaj9 -> Bm9, soft detuned sines with slow swell.
    chords = [[146.83, 220.0, 277.18, 329.63, 440.0],
              [123.47, 185.0, 246.94, 293.66, 369.99]]
    half = len(t) // 2
    for ci, chord in enumerate(chords):
        seg = slice(0, half) if ci == 0 else slice(half, len(t))
        tt = t[seg]
        for f in chord:
            for det in (-0.6, 0.6):
                mix[seg] += 0.05 * np.sin(2 * np.pi * (f + det) * tt)
    env = np.minimum(1, t / 0.4) * np.minimum(1, (total - t) / 0.6)
    mix *= env * (0.85 + 0.15 * np.sin(2 * np.pi * 0.5 * t))
    # Soft sub pulse + ticks synced to every cut.
    pos = 0
    for clip, ss, n, is_hold in shots:
        start = int(pos / FPS * sr)
        if is_hold:
            L = int(0.6 * sr); tt = np.arange(L) / sr
            hit = 0.35 * np.sin(2 * np.pi * 55 * tt) * np.exp(-tt * 6)
        else:
            L = int(0.08 * sr); tt = np.arange(L) / sr
            noise = np.random.default_rng(pos).standard_normal(L)
            hit = (0.18 * np.sin(2 * np.pi * 1760 * tt) + 0.12 * noise) * np.exp(-tt * 70)
        end = min(start + L, len(mix))
        mix[start:end] += hit[:end - start]
        pos += n
    mix /= np.max(np.abs(mix)) + 1e-9
    mix *= 0.89
    stereo = np.stack([mix, np.roll(mix, int(0.012 * sr))], axis=1)
    data = (stereo * 32767).astype(np.int16)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(data.tobytes())


def main():
    args = sys.argv[1:]
    loops = 1
    if "--loops" in args:
        i = args.index("--loops"); loops = int(args[i + 1]); del args[i:i + 2]
    out, clips = args[0], args[1:]
    if not clips:
        sys.exit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        shots = build_shots(clips, loops)
        silent = os.path.join(tmp, "video.mp4")
        render_video(shots, silent, tmp)
        wav = os.path.join(tmp, "music.wav")
        synth_music(shots, wav)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", silent, "-i", wav,
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-shortest", "-movflags", "+faststart", out], check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
