#!/usr/bin/env python3
"""
Colonna sonora originale per il logo reveal 3D Target (15,0 s), sintetizzata
interamente in codice: nessun campione esterno, nessun problema di licenza.

Ogni suono è posizionato sui timestamp della timeline dell'animazione
(animation/3dtarget-logo-animation.html); dove un elemento visivo si muove con
l'easing cubic-bezier(0.16, 1, 0.3, 1), il suono segue la stessa curva
(es. il filtro dei whoosh del mirino si apre esattamente come le linee crescono).

Musica: 120 BPM (i momenti chiave 2,0 · 4,0 · 7,0 · 9,5 · 12,0 · 13,5 s cadono sul beat),
tonalità di Re: pedale di Re → Si♭maj7 → Solm9 → La7sus4 → risoluzione in Re maggiore
(add9) sul match-cut chiaro a 12,0 s.

Output (cartella audio/):
  3dtarget-logo-audio-mix.wav      master stereo 48 kHz / 24 bit, -16 LUFS, true peak ≤ -1 dBTP
  stems/music.wav, stems/sfx.wav   stem per il montaggio (stesso guadagno del master, pre-limiter)
  3dtarget-logo-audio.m4a / .webm  AAC 192 kbps e Opus 160 kbps, incorporati nell'HTML
  audio-sync-check.png             forma d'onda + spettrogramma con i punti di sync
e aggiorna il blocco AUDIO_DATA nell'HTML.

Uso:  python3 audio/sound_design.py
Dipendenze: pip install numpy scipy matplotlib ; ffmpeg (FFMPEG, ffmpeg-static o PATH) per l'AAC.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import scipy.signal as sg
from scipy.ndimage import minimum_filter1d

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audio"
HTML = ROOT / "animation" / "3dtarget-logo-animation.html"

SR = 48000
DUR = 15.0
N = int(round(SR * DUR))
T = np.arange(N) / SR
TARGET_LUFS = -16.0
CEILING_DBTP = -1.0

# ---------------------------------------------------------------------------
# Punti di sincronizzazione (secondi) — identici alla timeline dell'HTML
# ---------------------------------------------------------------------------
CUES = {
    "dot_birth": 0.25, "dot_pulse": 1.44,
    "lines_h": 2.00, "lines_v": 2.12, "flare": (2.0, 2.7, 3.5, 4.4),
    "brackets": [4.00 + i * 0.11 for i in range(4)], "brackets_lock": 5.25,
    "three": [7.00, 7.12, 7.24],
    "divider": 9.5,
    "letters": [10.05 + i * 0.09 for i in range(8)],
    "color": 10.75,
    "hit": 12.0, "light_full": 12.40, "light_back": 12.80,
    "sweep": (12.72, 13.62), "hold": 13.5, "fx_zero": 14.7,
}


# ---------------------------------------------------------------------------
# Utilità
# ---------------------------------------------------------------------------
def db(x):
    return 10 ** (x / 20)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tt(n):
    return np.arange(n) / SR


def clamp01(x):
    return np.clip(x, 0.0, 1.0)


def sine(x):
    return 0.5 - 0.5 * np.cos(np.pi * clamp01(x))


def bezier(x1, y1, x2, y2):
    def f(x):
        x = clamp01(np.asarray(x, dtype=float))
        lo, hi = np.zeros_like(x), np.ones_like(x)
        for _ in range(42):
            m = (lo + hi) / 2
            bx = ((1 - 3 * x2 + 3 * x1) * m + (3 * x2 - 6 * x1)) * m * m + 3 * x1 * m
            lo, hi = np.where(bx < x, m, lo), np.where(bx < x, hi, m)
        m = (lo + hi) / 2
        return ((1 - 3 * y2 + 3 * y1) * m + (3 * y2 - 6 * y1)) * m * m + 3 * y1 * m
    return f


E = bezier(0.16, 1, 0.3, 1)  # stesso easing dell'animazione


def env4(t, a, b, c, d):
    """0 → 1 (a..b), 1 (b..c), 1 → 0 (c..d), transizioni sinusoidali."""
    return np.where(t < b, sine((t - a) / (b - a)), 1 - sine((t - c) / (d - c))) * (t > a) * (t < d)


def env_ad(n, attack, decay):
    t = tt(n)
    a = sine(t / attack) if attack > 0 else np.ones(n)
    return a * np.exp(-np.maximum(t - attack, 0) / decay)


def pk(x):
    return x / (np.max(np.abs(x)) + 1e-12)


def rms_norm(x):
    return x / (np.sqrt(np.mean(x ** 2)) + 1e-12)


def lp(x, fc, order=2):
    return sg.sosfilt(sg.butter(order, fc, "low", fs=SR, output="sos"), x, axis=-1)


def hp(x, fc, order=2):
    return sg.sosfilt(sg.butter(order, fc, "high", fs=SR, output="sos"), x, axis=-1)


def rng(seed):
    return np.random.default_rng(seed)


# ---------------------------------------------------------------------------
# Generatori
# ---------------------------------------------------------------------------
def pink(n, seed):
    x = rng(seed).standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    X /= np.sqrt(np.maximum(f, 20.0))
    return rms_norm(np.fft.irfft(X, n))


def band_noise(dur, fc_fn, bw_oct, seed, nper=2048):
    """Rumore filtrato da una campana (in ottave) centrata su fc_fn(u), u∈[0,1] = tempo normalizzato.
    Energia costante per frame: il volume lo decide l'inviluppo esterno."""
    n = int(round(dur * SR))
    x = rng(seed).standard_normal(n + nper)
    f, fr, Z = sg.stft(x, SR, nperseg=nper, noverlap=nper * 3 // 4)
    fc = np.maximum(fc_fn(clamp01(fr / dur)), 20.0)
    g = np.exp(-0.5 * (np.log2(np.maximum(f, 1.0)[:, None] / fc[None, :]) / bw_oct) ** 2)
    g /= np.sqrt(np.sum(g ** 2, axis=0, keepdims=True)) + 1e-12
    _, y = sg.istft(Z * g, SR, nperseg=nper, noverlap=nper * 3 // 4)
    return rms_norm(y[:n])


def sub(dur, f0, f1, glide, attack, decay):
    """Sub con discesa di pitch; 2ª e 3ª armonica leggere per udibilità su speaker piccoli."""
    n = int(round(dur * SR))
    t = tt(n)
    f = f1 + (f0 - f1) * np.exp(-t / glide)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) + 0.22 * np.sin(2 * ph) + 0.07 * np.sin(3 * ph)
    return pk(y * env_ad(n, attack, decay))


def fm(dur, f, ratio, index, idecay, attack, decay, seed=0):
    n = int(round(dur * SR))
    t = tt(n)
    ph0 = rng(seed).uniform(0, 2 * np.pi)
    I = index * np.exp(-t / idecay)
    y = np.sin(2 * np.pi * f * t + ph0 + I * np.sin(2 * np.pi * f * ratio * t))
    return y * env_ad(n, attack, decay)


def piano(f, dur=4.0, seed=0):
    """Timbro 'keynote piano' in FM: corpo + seconda armonica + martelletto."""
    y = fm(dur, f, 1.0, 1.9, 0.22, 0.002, 1.6, seed)
    y += 0.30 * fm(dur, 2 * f, 1.0, 0.8, 0.12, 0.002, 0.7, seed + 1)
    y += 0.12 * fm(dur, 4 * f, 1.0, 0.4, 0.05, 0.001, 0.25, seed + 2)
    n = len(y)
    ham = lp(rng(seed + 9).standard_normal(n) * np.exp(-tt(n) / 0.004), 3000)
    return y + 0.15 * ham


def glass(f, dur=1.8, seed=0):
    y = fm(dur, f, 2.0, 1.1, 0.35, 0.002, 0.55, seed)
    y += 0.25 * fm(dur, 3 * f, 1.0, 0.3, 0.1, 0.002, 0.25, seed + 3)
    return y


def pluck(f, seed=0):
    y = fm(0.7, f, 1.0, 1.3, 0.05, 0.002, 0.16, seed)
    return lp(y, 3800)


def tick(ratio, seed):
    """Click meccanico di precisione: transiente + ping metallico + 'thock'."""
    n = int(round(0.35 * SR))
    t = tt(n)
    click = hp(rng(seed).standard_normal(n) * np.exp(-t / 0.0012), 2500)
    ping = sum(a * np.sin(2 * np.pi * fq * ratio * t) * np.exp(-t / d)
               for fq, a, d in ((1870, 1.0, 0.05), (2790, 0.55, 0.032), (4130, 0.3, 0.02)))
    body = np.sin(2 * np.pi * 150 * ratio * t) * np.exp(-t / 0.018)
    return pk(0.55 * click + 0.45 * ping + 0.6 * body)


def impact(f_body, seed):
    n = int(round(1.2 * SR))
    t = tt(n)
    body = sub(1.2, f_body * 2.3, f_body, 0.025, 0.002, 0.22)
    tr = lp(rng(seed).standard_normal(n) * np.exp(-t / 0.02), 1800)
    return pk(body + 0.45 * pk(tr))


def pad(notes, dur, attack, release, cutoff, seed, voices=3, detune=8.0, spread=0.6, hmax=16):
    """Pad additivo (tipo saw morbido) con cutoff variabile nel tempo, stereo."""
    n = int(round(dur * SR))
    t = tt(n)
    cut = np.asarray(cutoff(t), dtype=float) * np.ones(n)
    r = rng(seed)
    out = np.zeros((2, n))
    for m in notes:
        f0 = mtof(m)
        for v in range(voices):
            k = (v - (voices - 1) / 2) / max((voices - 1) / 2, 1)
            fv = f0 * 2 ** (k * detune / 1200)
            pan = k * spread
            th = (pan + 1) * np.pi / 4
            lfo = 1 + 0.07 * np.sin(2 * np.pi * r.uniform(0.08, 0.2) * t + r.uniform(0, 6.28))
            y = np.zeros(n)
            for h in range(1, hmax + 1):
                fh = fv * h
                if fh > 15000:
                    break
                amp = h ** -1.25 / np.sqrt(1 + (fh / cut) ** 4)
                y += amp * np.sin(2 * np.pi * fh * t + r.uniform(0, 6.28))
            y *= lfo
            out[0] += y * np.cos(th)
            out[1] += y * np.sin(th)
    e = sine(t / attack) * (1 - sine((t - (dur - release)) / release))
    return out * e


def pingpong(x, delay, fb, taps, fc=3000):
    """Delay ping-pong con ripetizioni sempre più scure."""
    out = np.zeros((2, len(x)))
    y = x.copy()
    for k in range(1, taps + 1):
        y = lp(y, fc)
        s = int(round(k * delay * SR))
        if s >= len(x):
            break
        out[k % 2, s:] += (fb ** (k - 1)) * y[: len(x) - s]
    return out


def make_ir(rt60=2.6, length=3.6, predelay=0.018, seed=11):
    """Riverbero sintetico: coda con decadimento dipendente dalla frequenza + prime riflessioni."""
    n = int(round(length * SR))
    ir = np.zeros((2, n))
    pd = int(round(predelay * SR))
    for ch in range(2):
        x = rng(seed + ch).standard_normal(n)
        f, fr, Z = sg.stft(x, SR, nperseg=1024, noverlap=768)
        rt = rt60 * (0.35 + 0.65 / (1 + (f / 3500) ** 1.2))
        rt[f < 150] = rt60 * 0.8
        Z *= np.exp(-6.91 * fr[None, :] / rt[:, None])
        _, y = sg.istft(Z, SR, nperseg=1024, noverlap=768)
        y = y[:n] * sine(tt(n) / 0.012)
        for d, g in ((0.009, 0.5), (0.017, 0.35), (0.026, 0.28), (0.039, 0.2), (0.052, 0.15)):
            i = int((d + 0.003 * ch) * SR)
            y[i] += g * (1 if (ch + int(d * 1000)) % 2 else -1) * 3
        ir[ch, pd:] = y[: n - pd]
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------
class Stem:
    def __init__(self, name):
        self.name = name
        self.dry = np.zeros((2, N))
        self.send = np.zeros((2, N))

    def add(self, sig, t0, gain_db=0.0, pan=0.0, rev=0.0):
        sig = np.asarray(sig, dtype=float)
        if sig.ndim == 1:
            th = (np.clip(pan, -1, 1) + 1) * np.pi / 4
            sig = np.vstack([sig * np.cos(th), sig * np.sin(th)]) * np.sqrt(2)
        sig = sig * db(gain_db)
        i0 = int(round(t0 * SR))
        a, b = max(i0, 0), min(i0 + sig.shape[1], N)
        if b <= a:
            return
        self.dry[:, a:b] += sig[:, a - i0:b - i0]
        if rev > 0:
            self.send[:, a:b] += rev * sig[:, a - i0:b - i0]

    def render(self, ir, ret_db=-4.0):
        wet = np.vstack([sg.fftconvolve(self.send[c], ir[c])[:N] for c in range(2)])
        return self.dry + db(ret_db) * wet


def seg_pan(dur, fn):
    return fn(tt(int(round(dur * SR))))


# ---------------------------------------------------------------------------
# Composizione
# ---------------------------------------------------------------------------
def compose():
    music, sfx = Stem("music"), Stem("sfx")

    # --- room tone (tutta la durata, quasi impercettibile) ---
    room = np.vstack([hp(lp(pink(N, 1), 380), 40), hp(lp(pink(N, 2), 380), 40)])
    room *= sine(T / 1.5) * (1 - sine((T - 13.0) / 2.0))
    room /= np.sqrt(np.mean(room ** 2)) + 1e-12
    sfx.add(room, 0, gain_db=-54)

    # --- 0.25 nascita del punto: sub bloom + bagliore tonale ---
    t0 = CUES["dot_birth"]
    sfx.add(sub(2.6, mtof(38), mtof(26), 0.12, 0.05, 0.9), t0, gain_db=-16, rev=0.1)
    glow = pk(sum(a * fm(3.2, mtof(m), 1.0, 0.3, 0.5, 0.35, 1.3, s)
                  for m, a, s in ((74, 1.0, 1), (81, 0.5, 2), (86, 0.25, 3))))
    music.add(glow, t0 + 0.05, gain_db=-29, rev=0.9)
    # pulsazioni (0.49 accennata, 1.44 piena) — la luce del punto pulsa a ~1 Hz
    sfx.add(sub(1.4, 60, mtof(26), 0.06, 0.04, 0.45), 0.49, gain_db=-27)
    sfx.add(sub(1.4, 60, mtof(26), 0.06, 0.04, 0.5), CUES["dot_pulse"], gain_db=-20, rev=0.05)

    # --- 2.0 draw-on delle linee: whoosh che segue l'easing, stereo che si apre ---
    for side, seed in ((-1, 21), (1, 22)):
        dur = 1.9
        n = int(round(dur * SR))
        e = E(tt(n) / 1.7)
        w = band_noise(dur, lambda u: 380 * (5200 / 380) ** E(u * dur / 1.7), 0.55, seed)
        a = sine(tt(n) / 0.03) * (1 - e) ** 1.15
        sfx.add(w * a, CUES["lines_h"], gain_db=-21, pan=side * (0.2 + 0.65 * e), rev=0.25)
    n = int(round(1.8 * SR))
    e = E(tt(n) / 1.7)
    w = band_noise(1.8, lambda u: 300 * (3200 / 300) ** E(u * 1.8 / 1.7), 0.5, 23)
    sfx.add(w * sine(tt(n) / 0.03) * (1 - e) ** 1.2, CUES["lines_v"], gain_db=-26, rev=0.25)

    # flare anamorfico: tono cristallino + aria, panoramica che segue lo scorrimento del flare
    a0, a1, a2, a3 = CUES["flare"]
    dur = a3 - a0
    t = tt(int(round(dur * SR)))
    fe = env4(t + a0, a0, a1, a2, a3)
    trem = 1 + 0.12 * np.sin(2 * np.pi * 5.3 * t)
    tone = sum(g * np.sin(2 * np.pi * mtof(m) * t + ph) for m, g, ph in ((86, 1, 0), (93, 0.6, 1), (100, 0.35, 2)))
    pan = np.interp(sine(t / dur), [0, 1], [-0.35, 0.4])
    music.add(rms_norm(tone) * fe * trem, a0, gain_db=-35, pan=pan, rev=0.7)
    air = band_noise(dur, lambda u: 7500 + 0 * u, 0.5, 24)
    sfx.add(air * fe, a0, gain_db=-40, pan=pan, rev=0.4)

    # --- 4.0 le 4 staffe: aria in movimento + 4 tick di precisione + lock ---
    for side, seed in ((-1, 31), (1, 32)):
        dur = 2.3
        n = int(round(dur * SR))
        e = E(tt(n) / 1.9)
        w = band_noise(dur, lambda u: 260 * (1500 / 260) ** E(u * dur / 1.9), 0.7, seed)
        sfx.add(w * sine(tt(n) / 0.05) * (1 - e) ** 1.3, 4.0, gain_db=-29, pan=side * 0.55, rev=0.3)
    pans = (-0.45, 0.45, 0.35, -0.35)            # TL, TR, BR, BL (orario)
    ratios = (1.0, 1.12, 1.26, 1.335)             # Re–Mi–Fa#–Sol: tick che salgono
    for i, t0 in enumerate(CUES["brackets"]):
        sfx.add(tick(ratios[i], 40 + i), t0, gain_db=-15 + i * 0.5, pan=pans[i], rev=0.25)
    lock = pk(sub(0.35, 120, 82, 0.02, 0.002, 0.09) + 0.3 * tick(0.8, 49))
    sfx.add(lock, CUES["brackets_lock"], gain_db=-19, rev=0.2)

    # --- 7.0 il "3": tre impatti in crescendo (Sol–Si♭–Re), a sinistra ---
    for i, (t0, m) in enumerate(zip(CUES["three"], (43, 46, 50))):
        sfx.add(impact(mtof(m), 50 + i), t0, gain_db=(-14, -12, -10)[i], pan=-0.3, rev=0.3)
    # movimento di camera 7.0–9.5: respiro basso
    dur = 2.6
    n = int(round(dur * SR))
    w = band_noise(dur, lambda u: 180 + 420 * np.sin(np.pi * u), 0.8, 55)
    sfx.add(w * env4(tt(n), 0, 1.0, 1.4, dur), 7.0, gain_db=-33, rev=0.2)

    # --- 9.5 divisore: "zip" verticale + pulsazione sub; parte il riser ---
    t0 = CUES["divider"]
    dur = 1.5
    n = int(round(dur * SR))
    e = E(tt(n) / 1.3)
    w = band_noise(dur, lambda u: 900 * (5200 / 900) ** E(u * dur / 1.3), 0.3, 61)
    sfx.add(w * sine(tt(n) / 0.02) * (1 - e), t0, gain_db=-26, rev=0.3)
    sfx.add(sub(1.3, 95, 55, 0.05, 0.01, 0.35), t0, gain_db=-19)
    # riser 9.5 → 11.93 (taglio netto: 70 ms di "vuoto" prima dell'hit)
    dur = 11.93 - t0
    n = int(round(dur * SR))
    u = tt(n) / dur
    amp = db(-30 + 30 * u ** 1.5) * (1 - sine((tt(n) - (dur - 0.012)) / 0.012))
    for side, seed in ((-1, 62), (1, 63)):
        w = band_noise(dur, lambda u: 300 * (9000 / 300) ** (u ** 1.6), 0.45, seed)
        sfx.add(w * amp, t0, gain_db=-29, pan=side * 0.6, rev=0.2)
    # reverse cymbal 11.0 → 11.98
    dur = 0.98
    n = int(round(dur * SR))
    u = tt(n) / dur
    rc = hp(rng(64).standard_normal((2, n)), 4500) * (u ** 3) * (1 - sine((tt(n) - (dur - 0.01)) / 0.01))
    sfx.add(rms_norm(rc), 11.0, gain_db=-31)

    # --- 10.05 lettere: arpeggio di vetro, panoramica da sinistra a destra come il reveal ---
    for i, t0 in enumerate(CUES["letters"]):
        m = (69, 74, 76, 79, 81, 86, 88, 91)[i]
        music.add(pk(glass(mtof(m), seed=70 + i)), t0 + 0.03, gain_db=-25 + 0.25 * i,
                  pan=-0.35 + i * 0.13, rev=0.45)

    # --- 10.75 bianco → arancione: bagliore caldo (La7sus4 alto) ---
    dur = 11.97 - CUES["color"]
    sw = pad((69, 74, 76, 79), dur, 0.7, 0.35, lambda t: 1200 + 3000 * sine(t / 0.8), 80, voices=3)
    music.add(sw / (np.max(np.abs(sw)) + 1e-12), CUES["color"], gain_db=-31, rev=0.5)

    # --- 12.0 match-cut: HIT ---
    h = CUES["hit"]
    sfx.add(sub(3.5, 110, mtof(26), 0.07, 0.004, 1.1), h, gain_db=-14.5, rev=0.05)
    n = int(round(1.2 * SR))
    body = pk(lp(rng(90).standard_normal(n) * np.exp(-tt(n) / 0.1), 900)
              + 0.8 * np.sin(2 * np.pi * 65 * tt(n)) * np.exp(-tt(n) / 0.25))
    sfx.add(body, h, gain_db=-12.5, rev=0.35)
    chord = pk(sum(piano(mtof(m), 4.5, 100 + k) for k, m in enumerate((50, 57, 62, 66, 69, 76))))
    music.add(chord, h, gain_db=-10, rev=0.5)
    # reverse swell: coda riverberata dell'accordo, rovesciata, che culmina a 12.0
    ir_rev = make_ir(3.0, 3.0, 0.01, 97)
    wet = np.vstack([sg.fftconvolve(chord, ir_rev[c])[: int(round(1.3 * SR))] for c in range(2)])
    wet = wet[:, ::-1] * sine(tt(wet.shape[1]) / 0.9)
    wet[:, -int(round(0.008 * SR)):] *= np.linspace(1, 0, int(round(0.008 * SR)))
    music.add(wet / np.max(np.abs(wet)), h - wet.shape[1] / SR, gain_db=-18)
    # aria luminosa (schermo chiaro 12.0–12.8)
    dur = 3.5
    t = tt(int(round(dur * SR)))
    sh = sum(g * np.sin(2 * np.pi * mtof(m) * t + k) for k, (m, g) in enumerate(((86, 1), (90, 0.7), (93, 0.6), (98, 0.35))))
    music.add(rms_norm(sh) * env_ad(len(t), 0.35, 1.6) * (1 + 0.1 * np.sin(2 * np.pi * 4.1 * t)), h, gain_db=-33, rev=0.8)
    n = int(round(0.8 * SR))
    for side, seed in ((-1, 91), (1, 92)):
        air = band_noise(0.8, lambda u: 10000 + 0 * u, 0.4, seed)
        sfx.add(air * env4(tt(n), 0, 0.4, 0.4, 0.8), h, gain_db=-37, pan=side * 0.7, rev=0.3)
    # respiro del ritorno al buio (12.46 → 12.9)
    n = int(round(0.5 * SR))
    br = band_noise(0.5, lambda u: 2600 * (500 / 2600) ** u, 0.6, 93)
    sfx.add(br * env4(tt(n), 0, 0.2, 0.3, 0.5), 12.46, gain_db=-33, rev=0.3)

    # --- 12.72–13.62 light sweep: glint che attraversa da sinistra a destra ---
    s0, s1 = CUES["sweep"]
    dur = s1 - s0
    t = tt(int(round(dur * SR)))
    se = env4(t + s0, s0, 12.95, 13.4, s1)
    pan = -0.8 + 1.6 * sine(t / dur)
    gl = sum(g * np.sin(2 * np.pi * mtof(m) * (1 + 0.002 * np.sin(2 * np.pi * 7 * t)) * t + k)
             for k, (m, g) in enumerate(((98, 1), (102, 0.6), (105, 0.45))))
    music.add(rms_norm(gl) * se, s0, gain_db=-31, pan=pan, rev=0.55)
    sfx.add(band_noise(dur, lambda u: 6500 + 3000 * u, 0.5, 95) * se, s0, gain_db=-38, pan=pan, rev=0.3)

    # --- pad armonici ---
    pads = [
        # (inizio, fine, note, attacco, rilascio, cutoff(t), gain rms dB)
        (0.20, 4.6, (38, 45, 50), 2.5, 0.8, lambda t: 260 + 240 * sine(t / 4.0), -37),
        (4.00, 7.4, (46, 50, 53, 57, 62), 0.9, 0.6, lambda t: 500 + 400 * sine(t / 3.0), -28),
        (7.00, 9.9, (43, 50, 53, 58, 62, 69), 0.8, 0.5, lambda t: 800 + 500 * sine(t / 2.5), -28),
        (9.50, 11.97, (45, 52, 55, 62, 64, 69), 0.6, 0.12, lambda t: 1000 * (3.6 ** (t / 2.47)), -30),
        (12.0, 15.0, (38, 45, 50, 54, 57, 64, 66, 69), 0.08, 0.2, lambda t: 1300 + 1700 * np.exp(-t / 1.2), -25),
    ]
    for k, (a, b, notes, at, rl, cut, g) in enumerate(pads):
        p = pad(notes, b - a, at, rl, cut, 200 + k)
        p = hp(p, 45 if k == len(pads) - 1 else 100)   # basso pulito: il sub lo gestiscono gli impatti
        p /= np.sqrt(np.mean(p[:, int(round(at * SR)):int((b - a - rl) * SR)] ** 2)) + 1e-12
        music.add(p, a, gain_db=g, rev=0.35)

    # --- ostinato 120 BPM: semiminime 5.0–9.0, crome 9.5–9.75 e 10.75–11.75 ---
    ost = []
    for i, t0 in enumerate(np.arange(5.0, 9.01, 0.5)):
        cyc = (74, 77, 81, 77) if t0 < 7.0 else (74, 77, 81, 82)
        ost.append((t0, cyc[i % 4]))
    ost += [(9.5, 74), (9.75, 76)]              # 10.05–10.68: suonano le lettere
    ost += list(zip((10.75, 11.0, 11.25, 11.5, 11.75), (74, 76, 79, 81, 86)))
    obus = np.zeros(N)
    for i, (t0, m) in enumerate(ost):
        g = -25 + 3.5 * (t0 - 5.0) / 6.75 - (1.5 if (t0 * 2) % 2 else 0)
        y = pluck(mtof(m), 300 + i) * db(g)
        a = int(round(t0 * SR))
        obus[a:a + len(y)] += y[: N - a]
    music.add(obus, 0, pan=0.0, rev=0.25)
    dl = pingpong(obus, 0.375, 0.38, 6) * db(-9)
    dl *= 1 - sine((T - 11.95) / 0.15)          # le ripetizioni non sporcano l'hit
    music.add(dl, 0, rev=0.3)

    return music, sfx


# ---------------------------------------------------------------------------
# Master: loudness (ITU-R BS.1770-4), limiter true-peak, fade finale
# ---------------------------------------------------------------------------
def k_weight(x):
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    return sg.lfilter(b2, a2, sg.lfilter(b1, a1, x, axis=-1), axis=-1)


def lufs(x):
    y = k_weight(x)
    blk, hop = int(round(0.4 * SR)), int(round(0.1 * SR))
    ms = np.array([np.sum(np.mean(y[:, i:i + blk] ** 2, axis=1)) for i in range(0, y.shape[1] - blk + 1, hop)])
    lk = -0.691 + 10 * np.log10(ms + 1e-20)
    ms = ms[lk > -70]
    rel = -0.691 + 10 * np.log10(np.mean(ms)) - 10
    ms = ms[(-0.691 + 10 * np.log10(ms)) > rel]
    return -0.691 + 10 * np.log10(np.mean(ms))


def true_peak_db(x):
    return 20 * np.log10(np.max(np.abs(sg.resample_poly(x, 4, 1, axis=-1))) + 1e-12)


def limiter(x, ceiling_db, lookahead=0.004, release=0.12):
    ceil = db(ceiling_db)
    os = np.abs(sg.resample_poly(x, 4, 1, axis=-1)).max(axis=0)
    env = os[: (len(os) // 4) * 4].reshape(-1, 4).max(axis=1)[: x.shape[1]]
    g = np.minimum(1.0, ceil / np.maximum(env, 1e-12))
    la = int(round(lookahead * SR))
    g = minimum_filter1d(g, 2 * la + 1, origin=-la if la else 0)
    if la > 1:  # media mobile con bordi replicati (niente falsi interventi a inizio/fine)
        g = np.convolve(np.pad(g, (la, la), mode="edge"), np.ones(la) / la, mode="same")[la:-la]
    k = np.exp(-1 / (release * SR))
    out = np.empty_like(g)
    cur = 1.0
    for i, v in enumerate(g):
        cur = v if v < cur else v + (cur - v) * k
        out[i] = cur
    return x * out, out


def write_wav24(path, x):
    y = np.clip(x, -1.0, 1.0 - 1 / 8388608)
    i = np.ascontiguousarray(np.round(y.T * 8388607).astype("<i4"))
    b = i.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(3)
        w.setframerate(SR)
        w.writeframes(b)


def find_ffmpeg():
    for c in (os.environ.get("FFMPEG"), str(ROOT / "node_modules" / "ffmpeg-static" / "ffmpeg"), shutil.which("ffmpeg")):
        if c and Path(c).exists():
            return c
    return None


def sync_plot(mix, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(16, 7), sharex=True, gridspec_kw={"height_ratios": [1, 1.4]})
    fig.patch.set_facecolor("#2F2B28")
    m = mix.mean(axis=0)
    step = 240
    env = np.abs(m[: len(m) // step * step]).reshape(-1, step).max(axis=1)
    a1.fill_between(np.arange(len(env)) * step / SR, -env, env, color="#FF7800", lw=0)
    f, tt_, S = sg.spectrogram(m, SR, nperseg=2048, noverlap=1536)
    Sdb = 10 * np.log10(S + 1e-14)
    vmax = np.percentile(Sdb, 99.7)
    a2.pcolormesh(tt_, f, Sdb, shading="auto", cmap="magma", vmin=vmax - 75, vmax=vmax)
    a2.set_yscale("symlog", linthresh=200)
    a2.set_ylim(30, 20000)
    labels = [(0.25, "punto"), (2.0, "linee"), (4.0, "staffe"), (5.25, "lock"), (7.0, "«3»"),
              (9.5, "divisore"), (10.05, "lettere"), (10.75, "colore"), (12.0, "MATCH-CUT"),
              (12.72, "sweep"), (13.5, "hold"), (14.7, "fx 0")]
    for ax in (a1, a2):
        ax.set_facecolor("#1f1c1a")
        ax.tick_params(colors="#e9e4df")
        for s in ax.spines.values():
            s.set_color("#5a534d")
        for x, _ in labels:
            ax.axvline(x, color="#FFFFFF", alpha=0.35, lw=0.8)
    for x, lab in labels:
        a1.text(x + 0.04, 0.92 * a1.get_ylim()[1], lab, color="#FFFFFF", fontsize=8, va="top")
    a1.set_title("3D Target — audio sync check (mix master)", color="#e9e4df", loc="left")
    a2.set_xlabel("secondi", color="#e9e4df")
    a2.set_ylabel("Hz", color="#e9e4df")
    a2.set_xlim(0, DUR)
    a2.set_xticks(np.arange(0, 15.5, 0.5), minor=True)
    a2.set_xticks(np.arange(0, 16, 1))
    fig.tight_layout()
    fig.savefig(path, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)


def main():
    (OUT / "stems").mkdir(parents=True, exist_ok=True)
    print("sintesi…")
    music, sfx = compose()
    ir = make_ir()
    stems = {"music": music.render(ir, -3.0), "sfx": sfx.render(ir, -6.0)}

    fade = 1 - sine((T - 13.9) / 1.1)             # silenzio esatto a 15,0 s
    for k in stems:
        stems[k] = hp(stems[k], 22) * fade
    mix = stems["music"] + stems["sfx"]

    # normalizzazione iterativa: guadagno → limiter → rimisura
    pre = mix
    g = db(TARGET_LUFS - lufs(pre))
    for _ in range(4):
        mix, gr = limiter(pre * g, CEILING_DBTP - 0.3)
        g *= db(TARGET_LUFS - lufs(mix))
    mix, gr = limiter(pre * g, CEILING_DBTP - 0.3)
    tp_pre = true_peak_db(pre * g)
    stems = {k: v * g for k, v in stems.items()}
    # gli stem non passano dal limiter: se servisse, li abbasso tutti dello stesso valore
    stem_trim = min(0.0, -1.0 - max(20 * np.log10(np.max(np.abs(v))) for v in stems.values()))
    stems = {k: v * db(stem_trim) for k, v in stems.items()}
    report = {
        "sample_rate": SR, "bit_depth": 24, "samples": N, "duration_s": N / SR,
        "integrated_lufs": round(lufs(mix), 2), "true_peak_dbtp": round(true_peak_db(mix), 2),
        "true_peak_before_limiter_dbtp": round(tp_pre, 2),
        "max_gain_reduction_db": round(-20 * np.log10(gr.min()), 2),
        "stems_trim_db": round(stem_trim, 2),
        "stem_peaks_dbfs": {k: round(20 * np.log10(np.max(np.abs(v))), 2) for k, v in stems.items()},
        "last_100ms_peak_dbfs": round(20 * np.log10(np.max(np.abs(mix[:, -4800:])) + 1e-12), 1),
        "cues": CUES,
    }
    write_wav24(OUT / "3dtarget-logo-audio-mix.wav", mix)
    for k, v in stems.items():
        write_wav24(OUT / "stems" / f"{k}.wav", v)
    (OUT / "audio-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "cues"}, indent=2))

    try:
        sync_plot(mix, OUT / "audio-sync-check.png")
    except ImportError:
        print("matplotlib non installato: salto audio-sync-check.png")

    ff = find_ffmpeg()
    if not ff:
        print("ffmpeg non trovato: niente AAC né audio nell'HTML")
        return
    wav = str(OUT / "3dtarget-logo-audio-mix.wav")
    m4a, webm = OUT / "3dtarget-logo-audio.m4a", OUT / "3dtarget-logo-audio.webm"
    run = lambda *a: subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", wav, *a], check=True)
    run("-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(m4a))   # Safari, Chrome, Edge
    run("-c:a", "libopus", "-b:a", "160k", str(webm))                          # Chromium, Firefox
    if HTML.exists():
        data = {"m4a": "data:audio/mp4;base64," + base64.b64encode(m4a.read_bytes()).decode(),
                "webm": "data:audio/webm;base64," + base64.b64encode(webm.read_bytes()).decode()}
        html = HTML.read_text()
        block = "/*AUDIO_DATA_START*/" + json.dumps(data) + "/*AUDIO_DATA_END*/"
        html, n = re.subn(r"/\*AUDIO_DATA_START\*/.*?/\*AUDIO_DATA_END\*/", lambda _: block, html, flags=re.S)
        assert n == 1, "marker AUDIO_DATA non trovato nell'HTML"
        HTML.write_text(html)
        print("audio incorporato in", HTML.relative_to(ROOT),
              f"(AAC {m4a.stat().st_size // 1024} KB + Opus {webm.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
