#!/usr/bin/env python3
"""Procedurally render a synthetic gospel-concert worship video synced to a music track.

Every pixel is generated in code (no stock footage, no real people or places):
a backlit female lead singer, a swaying choir, volumetric stage light, golden
dust, and a worshipping crowd whose motion follows the music's energy and beat.

Usage: python3 render.py MUSIC_FILE OUTPUT.mp4 [--w 1920 --h 1080 --fps 30]
"""
import argparse, math, os, shutil, subprocess, sys, tempfile
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# ----------------------------------------------------------------------------- audio
def analyse(path, fps):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "22050",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    hop = 22050 / fps
    n = int(len(a) / hop)
    env = np.array([np.sqrt(np.mean(a[int(i * hop):int((i + 1) * hop)] ** 2) + 1e-9) for i in range(n)])
    env = np.convolve(env, np.ones(3) / 3, "same")
    env = (env - env.min()) / (np.percentile(env, 95) - env.min() + 1e-9)
    onset = np.maximum(0, np.diff(env, prepend=env[0]))
    o = onset - onset.mean()
    ac = np.correlate(o, o, "full")[len(o) - 1:]
    lo, hi = int(fps * 60 / 160), int(fps * 60 / 60)
    period = lo + int(np.argmax(ac[lo:hi]))
    phase = max(range(period), key=lambda p: onset[p::period].sum())
    # scene cuts at the quietest points near the quarter marks
    cuts = [0]
    for q in (0.26, 0.52, 0.78):
        c = int(n * q)
        w = int(fps * 0.8)
        cuts.append(c - w + int(np.argmin(env[c - w:c + w])))
    cuts.append(n)
    return dict(env=np.clip(env, 0, 1.3), period=period, phase=phase, cuts=cuts, n=n)


# ----------------------------------------------------------------------------- helpers
G = {}  # per-process globals


def blur(img, r):
    return img.filter(ImageFilter.GaussianBlur(r))


def to_np(img):
    return np.asarray(img, np.float32) / 255.0


def noise_tex(w, h, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    for k, amp in ((8, 1.0), (16, 0.5), (32, 0.25), (64, 0.12)):
        small = Image.fromarray((rng.random((max(2, h * k // w), k)) * 255).astype(np.uint8))
        out += amp * to_np(small.resize((w, h), Image.BICUBIC))
    return (out - out.min()) / (out.max() - out.min())


def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def arm(d, sx, sy, ang, ln, wd, fill, bend=0.25, hand=True):
    """Draw an arm from shoulder (sx,sy); ang = degrees from straight up (+ = outward right)."""
    a1 = math.radians(ang)
    ex, ey = sx + math.sin(a1) * ln, sy - math.cos(a1) * ln
    a2 = math.radians(ang * (1 - bend))
    hx, hy = ex + math.sin(a2) * ln * 0.95, ey - math.cos(a2) * ln * 0.95
    d.line([(sx, sy), (ex, ey)], fill=fill, width=int(wd))
    d.line([(ex, ey), (hx, hy)], fill=fill, width=int(wd * 0.85))
    r = wd * 0.5
    for p in ((sx, sy), (ex, ey)):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=fill)
    if hand:  # open palm with spread fingers
        pr = wd * 0.62
        d.ellipse([hx - pr, hy - pr * 1.2, hx + pr, hy + pr * 0.9], fill=fill)
        for f in (-30, -12, 5, 22):
            fa = a2 + math.radians(f)
            d.line([(hx, hy), (hx + math.sin(fa) * wd * 1.3, hy - math.cos(fa) * wd * 1.3)],
                   fill=fill, width=max(1, int(wd * 0.22)))
        ta = a2 + math.radians(-70 if ang >= 0 else 70)
        d.line([(hx, hy), (hx + math.sin(ta) * wd * 0.9, hy - math.cos(ta) * wd * 0.9)],
               fill=fill, width=max(1, int(wd * 0.25)))


def crowd_person(d, x, y, s, sway, arms, raise_amt, tilt, long_hair, bottom, fill=255):
    """Back view of a worshipper: head + shoulders, arms rising. y = shoulder line, s = half-shoulder."""
    x += sway
    hx, hy = x + sway * 0.3 + tilt * s * 0.3, y - 1.05 * s + abs(tilt) * 0.05 * s
    if long_hair:
        d.polygon([(hx - 0.42 * s, hy - 0.1 * s), (hx + 0.42 * s, hy - 0.1 * s), (hx + 0.55 * s, y + 0.1 * s),
                   (hx + 0.3 * s, y + 0.3 * s), (hx - 0.3 * s, y + 0.3 * s), (hx - 0.55 * s, y + 0.1 * s)], fill=fill)
    d.ellipse([hx - 0.42 * s, hy - 0.52 * s, hx + 0.42 * s, hy + 0.5 * s], fill=fill)
    d.rectangle([x - 0.2 * s, hy, x + 0.2 * s, y], fill=fill)
    d.polygon([(x - 1.05 * s, y + 0.35 * s), (x - 0.8 * s, y - 0.05 * s), (x - 0.25 * s, y - 0.22 * s),
               (x + 0.25 * s, y - 0.22 * s), (x + 0.8 * s, y - 0.05 * s), (x + 1.05 * s, y + 0.35 * s),
               (x + 1.15 * s, bottom), (x - 1.15 * s, bottom)], fill=fill)
    up = raise_amt
    for side, on in ((-1, arms in ("both", "left")), (1, arms in ("both", "right"))):
        if not on:
            continue
        ang = side * (175 - up * (160 - sway / s * 8)) if up < 1 else side * (15 + side * sway / s * 6)
        arm(d, x + side * 0.82 * s, y + 0.05 * s, ang, 1.25 * s, 0.34 * s, fill, bend=0.3)


def lead_singer(d, x, feet, h, t, sway, lift, tilt, fill=255):
    """Front-facing female lead, long braids, flowing gown, mic to lips, free hand lifted."""
    hw = h * 0.065
    shy = feet - 0.82 * h
    hx, hy = x + sway * 0.4, feet - 0.92 * h - tilt * 0.01 * h
    wave = math.sin(t * 2.1) * h * 0.012
    # hair falls past the shoulders
    for side in (-1, 1):  # braids falling over the shoulders
        for j in range(5):
            x0 = hx + side * hw * (0.45 + 0.12 * j)
            y0 = hy - hw * (0.9 - 0.25 * j)
            pts = [(x0, y0)]
            for u in (0.33, 0.66, 1.0):
                pts.append((x0 + side * hw * (0.35 + 0.1 * j) * u + wave * u * (1 + 0.3 * j),
                            y0 + (shy + (0.16 - 0.015 * j) * h - y0) * u))
            d.line(pts, fill=fill, width=max(1, int(h * 0.011)), joint="curve")
    d.ellipse([hx - hw * 0.88, hy - hw * 1.25, hx + hw * 0.88, hy + hw * 1.1], fill=fill)
    d.ellipse([hx - hw * 0.6, hy - hw * 1.95, hx + hw * 0.6, hy - hw * 0.85], fill=fill)  # bun
    d.rectangle([x - hw * 0.3, hy, x + hw * 0.3, shy], fill=fill)
    waist = feet - 0.58 * h
    d.polygon([(x - 0.03 * h, shy - 0.015 * h), (x + 0.03 * h, shy - 0.015 * h), (x + 0.1 * h, shy),
               (x + 0.115 * h, shy + 0.03 * h), (x + 0.075 * h, waist), (x - 0.075 * h, waist),
               (x - 0.115 * h, shy + 0.03 * h), (x - 0.1 * h, shy)], fill=fill)
    # gown flares to the floor with a breathing hem
    pts = [(x - 0.07 * h, waist)]
    for i in range(13):
        u = i / 12
        px = x - 0.07 * h - 0.2 * h * u ** 1.4 - math.sin(t * 1.3 + u * 4) * 0.015 * h * u + sway * 0.5 * u
        pts.append((px, waist + (feet - waist) * u))
    for i in range(17):
        u = i / 16
        hem = x - 0.27 * h + 0.54 * h * u + sway * 0.5
        pts.append((hem, feet + math.sin(t * 2.4 + u * 9) * 0.008 * h))
    for i in range(12, -1, -1):
        u = i / 12
        px = x + 0.07 * h + 0.2 * h * u ** 1.4 + math.sin(t * 1.1 + u * 4) * 0.015 * h * u + sway * 0.5 * u
        pts.append((px, waist + (feet - waist) * u))
    d.polygon(pts, fill=fill)
    w = 0.035 * h
    # mic arm: elbow down, hand at lips
    sx, sy = x - 0.11 * h, shy + 0.01 * h
    ex, ey = sx - 0.04 * h, sy + 0.15 * h
    mx, my = hx - hw * 0.6, hy + hw * 1.3
    d.line([(sx, sy), (ex, ey), (mx, my)], fill=fill, width=int(w), joint="curve")
    d.ellipse([mx - w * 0.7, my - w * 0.7, mx + w * 0.7, my + w * 0.7], fill=fill)
    d.line([(mx, my), (mx + hw * 0.5, my - hw * 0.9)], fill=fill, width=int(w * 0.55))
    # free arm lifts toward heaven
    ang = 165 - lift * 130 + math.sin(t * 1.7) * 6 * lift
    arm(d, x + 0.11 * h, sy, ang, 0.17 * h, w, fill, bend=0.2)


def choir_member(d, x, base, h, sway, fill):
    hw = h * 0.075
    hx = x + sway
    top = base - h
    d.ellipse([hx - hw, top, hx + hw, top + 2.3 * hw], fill=fill)
    sy = top + 2.6 * hw
    d.rectangle([hx - hw * 0.4, top + 2 * hw, hx + hw * 0.4, sy], fill=fill)
    d.polygon([(hx - 0.06 * h, sy - 0.02 * h), (hx + 0.06 * h, sy - 0.02 * h), (hx + 0.17 * h, sy + 0.05 * h),
               (x + 0.2 * h, base), (x - 0.2 * h, base), (hx - 0.17 * h, sy + 0.05 * h)], fill=fill)


# ----------------------------------------------------------------------------- frame
def lighting(W, H, t, e, beat, srcs, beam_count, spread, tint):
    """Volumetric beams from stage sources, modulated by haze and music."""
    lw, lh = W // 3, H // 3
    m = Image.new("L", (lw, lh), 0)
    d = ImageDraw.Draw(m)
    for si, (sx, sy) in enumerate(srcs):
        for b in range(beam_count):
            base = (b - (beam_count - 1) / 2) * spread
            ang = math.radians(base + math.sin(t * 0.6 + si * 1.7 + b) * 9)
            L = lh * 2.2
            wdt = math.radians(2.2 + 1.2 * e)
            x0, y0 = sx * lw, sy * lh
            p1 = (x0 + math.sin(ang - wdt) * L, y0 + math.cos(ang - wdt) * L)
            p2 = (x0 + math.sin(ang + wdt) * L, y0 + math.cos(ang + wdt) * L)
            d.polygon([(x0, y0), p1, p2], fill=int(40 + 60 * e + 70 * beat))
    m = blur(m, lw / 90).resize((W, H), Image.BILINEAR)
    beams = to_np(m)
    haze = G["haze"]
    ox = int((t * 18) % (haze.shape[1] - W))
    hz = haze[:H, ox:ox + W]
    beams = beams * (0.45 + 0.9 * hz)
    return beams[..., None] * np.array(tint, np.float32)


def glow(W, H, cx, cy, rx, ry, strength):
    yy, xx = G["grid"]
    d2 = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    return strength * np.exp(-d2)


def composite_sil(frame, mask_img, rim_col, rim_r, body_col=(0.012, 0.01, 0.02)):
    m = to_np(mask_img)[..., None]
    rim = np.clip(to_np(blur(mask_img, rim_r))[..., None] - m * 0.6, 0, 1)
    frame = frame + rim * np.array(rim_col, np.float32)
    return frame * (1 - m) + np.array(body_col, np.float32) * m


def particles(frame, W, H, t, n, seed, col, e, rise=40):
    rng = np.random.default_rng(seed)
    px, py0, sp, sz, ph = (rng.random(n) for _ in range(5))
    layer = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(layer)
    for i in range(n):
        y = (py0[i] * H * 1.2 - t * (rise + sp[i] * rise * 2) * W / 1280) % (H * 1.2) - H * 0.1
        x = px[i] * W + math.sin(t * (0.5 + sp[i]) + ph[i] * 6) * 25 * W / 1280
        r = (0.8 + sz[i] * 2.4) * W / 1280
        a = int(120 + 135 * (0.5 + 0.5 * math.sin(t * 3 + ph[i] * 9)) * min(1, 0.4 + e))
        d.ellipse([x - r, y - r, x + r, y + r], fill=a)
    p = to_np(layer)
    p = p + to_np(blur(layer, 4 * W / 1280)) * 1.5
    return frame + p[..., None] * np.array(col, np.float32)


def grade(frame, W, H, t, fi, fade):
    # bloom
    lum = frame.mean(-1)
    bright = np.clip(frame - 0.7, 0, None)
    small = Image.fromarray((np.clip(bright, 0, 1) * 255).astype(np.uint8)).resize((W // 8, H // 8), Image.BILINEAR)
    bl = to_np(blur(small, 6).resize((W, H), Image.BILINEAR))
    frame = frame + bl * 1.4
    # filmic tone map + warm split-tone
    frame = frame / (1 + frame * 0.55) * 1.35
    shadows = np.clip(1 - lum * 2, 0, 1)[..., None]
    frame = frame + shadows * np.array([0.008, 0.0, 0.025], np.float32)
    frame = frame * G["vignette"][..., None]
    grain = G["grain"][fi % len(G["grain"])]
    frame = frame + grain[..., None] * 0.035
    frame = frame * fade
    return (np.clip(frame, 0, 1) ** (1 / 1.05) * 255).astype(np.uint8)


def scene_wide(W, H, t, lt, e, beat, k):
    """Wide establishing shot: stage, choir, lead, crowd silhouettes with hands rising."""
    z = 1.0 + lt * 0.025  # slow push-in
    cx, cy = W / 2, H * 0.55

    def P(x, y):
        return cx + (x * k - cx) * z, cy + (y * k - cy) * z

    frame = np.zeros((H, W, 3), np.float32)
    frame += glow(W, H, *P(640, 300), 520 * k * z, 260 * k * z, 1)[..., None] * np.array([0.55, 0.32, 0.12])
    frame += glow(W, H, *P(640, 330), 160 * k * z, 120 * k * z, 0.9 + 0.4 * beat)[..., None] * np.array([1.0, 0.85, 0.55])
    frame += glow(W, H, *P(200, 200), 260 * k, 200 * k, 0.35)[..., None] * np.array([0.35, 0.15, 0.6])
    frame += glow(W, H, *P(1080, 200), 260 * k, 200 * k, 0.35)[..., None] * np.array([0.35, 0.15, 0.6])
    # luminous cross on the back wall
    cr = Image.new("L", (W, H), 0)
    dc = ImageDraw.Draw(cr)
    a, b = P(632, 150), P(648, 360)
    dc.rectangle([a[0], a[1], b[0], b[1]], fill=255)
    a, b = P(585, 205), P(695, 221)
    dc.rectangle([a[0], a[1], b[0], b[1]], fill=255)
    crn = to_np(blur(cr, 2 * k)) + to_np(blur(cr, 25 * k)) * 1.2
    frame += crn[..., None] * np.array([1.0, 0.9, 0.7]) * (0.55 + 0.25 * e)
    # stage floor reflection
    yy = G["grid"][0]
    sy = P(0, 470)[1]
    floor = np.clip((yy - sy) / (60 * k), 0, 1) * np.exp(-((yy - sy) / (120 * k)))
    frame += floor[..., None] * np.array([0.5, 0.35, 0.2]) * 0.6

    stage = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(stage)
    sway2 = math.sin(2 * math.pi * G["beat_t"](t) / 2)
    for row, (base, hh, n) in enumerate(((420, 70, 13), (440, 78, 12))):
        for i in range(n):
            x = 300 + (680 / (n - 1)) * i + (row * 26)
            if abs(x - 640) < 70:
                continue
            bx, by = P(x, base)
            choir_member(d, bx, by, hh * k * z, sway2 * 7 * k * z * (0.5 + e), 255)
    lx, ly = P(640, 472)
    lead_singer(d, lx, ly, 200 * k * z, t, math.sin(t * 1.2) * 4 * k, smooth(lt / 3.5), 1)
    d.rectangle([0, ly, W, H], fill=255)
    frame = composite_sil(frame, stage, (1.0, 0.75, 0.4), 3 * k, body_col=(0.02, 0.015, 0.03))
    frame += lighting(W, H, t, e, beat, [(0.25, 0.08), (0.5, 0.02), (0.75, 0.08)], 3, 22, (1.0, 0.82, 0.55)) * 0.55
    crowd = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(crowd)
    rng = np.random.default_rng(7)
    for row, (y, s, n) in enumerate(((600, 26, 16), (650, 34, 12), (705, 46, 9))):
        for i in range(n):
            x = (i + 0.5 + rng.uniform(-0.3, 0.3)) * 1280 / n + row * 20
            ph = rng.uniform(0, 6.28)
            arms = rng.choice(["both", "both", "right", "left", "none"])
            delay = rng.uniform(0, 2.5)
            sway = math.sin(2 * math.pi * G["beat_t"](t) / 2 + ph * 0.3) * s * 0.25 * (0.4 + e)
            px, py = P(x, y)
            crowd_person(d, px, py, s * k * z, sway * k, arms, smooth((lt - delay) / 1.5),
                         math.sin(ph) * 0.6, rng.random() < 0.55, H)
    frame = composite_sil(frame, crowd, (0.9, 0.6, 0.3), 2.5 * k)
    return particles(frame, W, H, t, 140, 3, (1.0, 0.8, 0.45), e)


def scene_singer(W, H, t, lt, e, beat, k):
    """Close shot of the lead singer, head lifted, hand rising in surrender."""
    z = 1.0 + lt * 0.035
    frame = np.zeros((H, W, 3), np.float32)
    cx = W * 0.5
    frame += glow(W, H, cx, H * 0.3, 700 * k, 520 * k, 1.0)[..., None] * np.array([0.55, 0.3, 0.12])
    frame += glow(W, H, cx + 40 * k, H * 0.2, 240 * k, 240 * k, 1.1 + 0.5 * beat)[..., None] * np.array([1.0, 0.88, 0.62])
    frame += glow(W, H, W * 0.1, H * 0.4, 400 * k, 400 * k, 0.45)[..., None] * np.array([0.4, 0.15, 0.55])
    frame += lighting(W, H, t, e, beat, [(0.52, -0.05)], 7, 9, (1.0, 0.85, 0.6)) * 0.7
    sil = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(sil)
    h = 900 * k * z
    lead_singer(d, cx - 30 * k, H * 0.3 + h * 0.92 - lt * 6 * k, h, t, math.sin(t * 0.9) * 10 * k,
                0.25 + 0.75 * smooth(lt / 3.0), 1)
    # round off hard polygon corners so the figure reads as organic at this size
    sil = blur(sil, 5 * k).point(lambda v: 255 if v > 110 else 0)
    sil = blur(sil, 1.2 * k)
    frame = composite_sil(frame, sil, (1.0, 0.78, 0.45), 6 * k)
    return particles(frame, W, H, t, 220, 11, (1.0, 0.82, 0.5), e, rise=25)


def scene_crowd(W, H, t, lt, e, beat, k):
    """Inside the congregation: big silhouettes, hands lifted, heads tilted back, one kneeling."""
    pan = lt * 22
    frame = np.zeros((H, W, 3), np.float32)
    frame += glow(W, H, W * 0.6 - pan * k, H * 0.25, 600 * k, 300 * k, 1.0 + 0.35 * beat)[..., None] * np.array([1.0, 0.8, 0.5])
    frame += glow(W, H, W * 0.15 - pan * k, H * 0.3, 380 * k, 260 * k, 0.6)[..., None] * np.array([0.45, 0.2, 0.7])
    frame += glow(W, H, W * 0.95 - pan * k, H * 0.2, 300 * k, 260 * k, 0.5)[..., None] * np.array([0.25, 0.3, 0.8])
    frame += lighting(W, H, t, e, beat, [(0.6 - pan / 1280, -0.1), (0.2 - pan / 1280, -0.1)], 4, 14, (1.0, 0.85, 0.65)) * 0.8
    frame = particles(frame, W, H, t, 160, 21, (1.0, 0.85, 0.55), e, rise=18)
    rng = np.random.default_rng(5)
    for layer_i, (y, s, n, rim) in enumerate(((420, 40, 9, 2.5), (560, 75, 6, 4), (760, 140, 3, 7))):
        sil = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(sil)
        par = (layer_i + 1) * 0.6
        for i in range(n):
            x = (i + 0.5 + rng.uniform(-0.25, 0.25)) * 1400 / n - 60 - pan * par
            ph = rng.uniform(0, 6.28)
            arms = rng.choice(["both", "both", "right", "left"]) if layer_i < 2 else ["both", "right", "both"][i]
            sway = math.sin(2 * math.pi * G["beat_t"](t) / 2 + ph * 0.4) * s * 0.18 * (0.5 + e)
            crowd_person(d, x * k, y * k, s * k, sway * k, arms, smooth((lt - rng.uniform(0, 1.2)) / 1.2),
                         -0.8 + math.sin(ph) * 0.3, rng.random() < 0.6, H)
        if layer_i == 1:  # a worshipper kneeling, head bowed
            kx, ky = (980 - pan * par) * k, 640 * k
            d.ellipse([kx - 24 * k, ky - 70 * k, kx + 24 * k, ky - 22 * k], fill=255)
            d.polygon([(kx - 55 * k, ky - 20 * k), (kx + 55 * k, ky - 20 * k), (kx + 85 * k, H), (kx - 85 * k, H)], fill=255)
        frame = composite_sil(frame, sil, (1.0, 0.75, 0.42), rim * k, body_col=(0.015 + 0.02 * (2 - layer_i), 0.01, 0.03))
    return frame


def scene_finale(W, H, t, lt, e, beat, k, dur):
    """Wide finale: light bursts open, everyone's hands are up, lead's arms wide."""
    burst = smooth(lt / 1.2)
    frame = scene_wide(W, H, t, 6 + lt, e, beat, k)
    frame += glow(W, H, W / 2, H * 0.42, 500 * k * (0.6 + burst), 300 * k * (0.6 + burst), 0.3 * burst + 0.2 * beat)[..., None] * np.array([1.0, 0.85, 0.55])
    rays = lighting(W, H, t * 0.5, e, beat, [(0.5, 0.42)], 16, 22, (1.0, 0.9, 0.7))
    frame += rays * 0.2 * burst
    return particles(frame, W, H, t, 200, 31, (1.0, 0.9, 0.6), e, rise=55)


SCENES = [scene_wide, scene_singer, scene_crowd, scene_finale]


def render_frame(args):
    fi, out = args
    a, W, H, fps = G["a"], G["W"], G["H"], G["fps"]
    k = W / 1280
    t = fi / fps
    e = float(a["env"][min(fi, len(a["env"]) - 1)])
    bt = G["beat_t"](t)
    beat = math.exp(-((bt - round(bt)) * a["period"] / fps / 0.07) ** 2)
    cuts = a["cuts"]
    si = max(i for i in range(4) if cuts[i] <= fi)
    lt = (fi - cuts[si]) / fps
    dur = (cuts[si + 1] - cuts[si]) / fps
    fn = SCENES[si]
    frame = fn(W, H, t, lt, e, beat, k, dur) if fn is scene_finale else fn(W, H, t, lt, e, beat, k)
    # light-flash dissolve at each cut
    flash = 0.0
    for c in cuts[1:-1]:
        flash = max(flash, math.exp(-((fi - c) / (fps * 0.12)) ** 2))
    frame = frame + flash * 0.9 * np.array([1.0, 0.9, 0.75], np.float32)
    total = a["n"]
    fade = smooth(fi / (fps * 0.8)) * smooth((total - fi) / (fps * 1.0))
    Image.fromarray(grade(frame, W, H, t, fi, fade)).save(os.path.join(out, f"f{fi:05d}.png"), compress_level=1)
    return fi


def init(a, W, H, fps):
    G.update(a=a, W=W, H=H, fps=fps)
    G["beat_t"] = lambda t: (t * fps - a["phase"]) / a["period"]
    G["grid"] = np.mgrid[0:H, 0:W].astype(np.float32)
    yy, xx = G["grid"]
    G["vignette"] = np.clip(1.15 - 0.55 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2), 0.25, 1)
    G["haze"] = noise_tex(W * 2, H, 1)
    rng = np.random.default_rng(2)
    G["grain"] = [(rng.random((H, W), np.float32) - 0.5) for _ in range(6)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("music")
    ap.add_argument("output")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--frames", default="", help="only render these comma-separated frames (preview)")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    o = ap.parse_args()
    a = analyse(o.music, o.fps)
    print(f"{a['n']} frames, beat period {a['period']} frames, cuts {a['cuts']}", file=sys.stderr)
    tmp = tempfile.mkdtemp()
    frames = [int(x) for x in o.frames.split(",")] if o.frames else list(range(a["n"]))
    with Pool(o.workers, initializer=init, initargs=(a, o.w, o.h, o.fps)) as p:
        for i, _ in enumerate(p.imap_unordered(render_frame, [(f, tmp) for f in frames])):
            if i % 50 == 0:
                print(f"  {i}/{len(frames)}", file=sys.stderr)
    if o.frames:
        os.makedirs(o.output, exist_ok=True)
        for f in frames:
            shutil.move(os.path.join(tmp, f"f{f:05d}.png"), os.path.join(o.output, f"f{f:05d}.png"))
    else:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(o.fps), "-i", os.path.join(tmp, "f%05d.png"),
                        "-i", o.music, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow",
                        "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", o.output], check=True)
    shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
