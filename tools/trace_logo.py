#!/usr/bin/env python3
"""
Vettorializza il logo 3D Target a partire dai PNG ufficiali (con trasparenza).

- Ogni elemento del logo (il "3", le 4 staffe, il punto, i 4 segmenti del mirino,
  il divisore, le lettere del testo) viene isolato come componente connessa
  dell'alpha e tracciato con potrace su una versione sovracampionata (x6)
  dell'alpha originale: nessun ridisegno, solo il contorno reale dei pixel.
- Le varianti chiare (A, D) e scure (B, C) hanno una spaziatura leggermente
  diversa della parola "Target": vengono quindi tracciate due geometrie
  ("dark" da B, "light" da A), ognuna fedele alla propria variante.

Output:
  assets/logo/logo-data.json                  percorsi (geometria B "dark", A "light") + colori
  assets/logo/3dtarget-logo-{A,B,C,D}.svg     SVG statici, viewBox 0 0 2000 536
  e aggiorna il blocco dati dentro animation/3dtarget-logo-animation.html

Uso:  python3 tools/trace_logo.py
Dipendenze: pip install pillow numpy scipy potracer
"""
import json
import re
from pathlib import Path

import numpy as np
import potrace
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "assets" / "source"
OUT = ROOT / "assets" / "logo"
HTML = ROOT / "animation" / "3dtarget-logo-animation.html"
UP = 6  # fattore di sovracampionamento prima del tracing

# Colori campionati dai file (valori esatti, pixel pieni)
ORANGE = "#FF7800"
WHITE = "#FFFFFF"
DARK_WARM = "#2F2B28"   # "3" nella variante A, tutto nella variante D
DARK_NEUTRAL = "#2D2D2D"  # mirino, divisore e "Target" nella variante A

# Nome dei componenti in base alla posizione (bbox x0,x1,y0,y1 nei PNG 2000x536)
def classify(x0, x1, y0, y1):
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if x1 < 400:
        return "three"
    if 780 < cx < 810:
        return "divider"
    if 540 < cx < 590 and 240 < cy < 295 and (x1 - x0) > 30:
        return "dot"
    if 550 < cx < 575:
        return "vline_top" if cy < 268 else "vline_bottom"
    if (y1 - y0) < 20 and 255 < cy < 280:
        return "hline_left" if cx < 563 else "hline_right"
    if 420 < x0 < 590 and x1 < 710:
        h = "l" if cx < 563 else "r"
        v = "t" if cy < 268 else "b"
        return f"br_{v}{h}"
    letters = [(870, "txt_3"), (1000, "txt_D"), (1175, "txt_T"), (1300, "txt_a"),
               (1420, "txt_r"), (1495, "txt_g"), (1625, "txt_e"), (1740, "txt_t")]
    name = None
    for lx, n in letters:
        if x0 >= lx:
            name = n
    return name


def load(name):
    return np.array(Image.open(SRC / name).convert("RGBA")).astype(np.float64)


def components(rgba):
    alpha = rgba[..., 3]
    core = alpha > 127
    lab, n = ndimage.label(core)
    # assegna i pixel di antialiasing (0<a<=127) alla componente più vicina
    _, (iy, ix) = ndimage.distance_transform_edt(lab == 0, return_indices=True)
    owner = lab[iy, ix]
    owner[alpha == 0] = 0
    comps = {}
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        name = classify(x0, x1, y0, y1)
        assert name and name not in comps, (name, x0, x1, y0, y1)
        pad = 4
        Y0, Y1, X0, X1 = max(y0 - pad, 0), y1 + pad, max(x0 - pad, 0), x1 + pad
        a = np.where(owner[Y0:Y1, X0:X1] == i, alpha[Y0:Y1, X0:X1], 0.0)
        colors = rgba[Y0:Y1, X0:X1][(owner[Y0:Y1, X0:X1] == i) & (alpha[Y0:Y1, X0:X1] > 250)][:, :3]
        comps[name] = dict(alpha=a, x0=X0, y0=Y0, color=np.median(colors, axis=0).round().astype(int).tolist())
    return comps


def f(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def trace(comp):
    a = comp["alpha"] / 255.0
    big = ndimage.zoom(a, UP, order=3, grid_mode=True, mode="grid-constant")
    bm = potrace.Bitmap(big <= 0.5)  # potracer: False = pixel "nero" (pieno)
    plist = bm.trace(turdsize=4, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                     alphamax=1.0, opticurve=True, opttolerance=0.2)
    X0, Y0 = comp["x0"], comp["y0"]
    P = lambda p: f"{f(p.x / UP + X0)} {f(p.y / UP + Y0)}"
    d = []
    for curve in plist:
        d.append(f"M{P(curve.start_point)}")
        for seg in curve.segments:
            if seg.is_corner:
                d.append(f"L{P(seg.c)}L{P(seg.end_point)}")
            else:
                d.append(f"C{P(seg.c1)} {P(seg.c2)} {P(seg.end_point)}")
        d.append("Z")
    return "".join(d)


def measure(comp):
    """bbox (dai bordi al 50% di alpha, sovracampionati) e baricentro/raggio equivalente."""
    a = comp["alpha"] / 255.0
    big = ndimage.zoom(a, UP, order=3, grid_mode=True, mode="grid-constant") > 0.5
    ys, xs = np.nonzero(big)
    X0, Y0 = comp["x0"], comp["y0"]
    bbox = [xs.min() / UP + X0, ys.min() / UP + Y0, (xs.max() + 1) / UP + X0, (ys.max() + 1) / UP + Y0]
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    cx = (a * (xx + 0.5)).sum() / a.sum() + X0
    cy = (a * (yy + 0.5)).sum() / a.sum() + Y0
    return dict(bbox=[round(v, 2) for v in bbox], cx=round(cx, 2), cy=round(cy, 2),
                r=round(float(np.sqrt(a.sum() / np.pi)), 2))


def hexcol(c):
    return "#%02X%02X%02X" % tuple(c)


def svg(paths, colors, order):
    body = "\n".join(
        f'  <path id="{k}" fill="{colors[k]}" d="{paths[k]}"/>' for k in order)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2000 536" '
            'width="2000" height="536">\n' + body + "\n</svg>\n")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    A = components(load("logo-A-color-light.png"))
    B = components(load("logo-B-color-dark.png"))
    C = components(load("logo-C-mono-white.png"))
    D = components(load("logo-D-mono-dark.png"))
    order = ["three", "br_tl", "br_tr", "br_bl", "br_br", "hline_left", "hline_right",
             "vline_top", "vline_bottom", "dot", "divider",
             "txt_3", "txt_D", "txt_T", "txt_a", "txt_r", "txt_g", "txt_e", "txt_t"]
    assert set(order) == set(A) == set(B) == set(C) == set(D)

    print("Colori campionati per componente (A | B | C | D):")
    for k in order:
        print(f"  {k:13s}", *(hexcol(V[k]["color"]) for V in (A, B, C, D)))

    geo = {v: {k: trace(V[k]) for k in order} for v, V in (("A", A), ("B", B), ("C", C), ("D", D))}
    dark, light = geo["B"], geo["A"]

    colors = {
        "A": {k: hexcol(A[k]["color"]) for k in order},
        "B": {k: hexcol(B[k]["color"]) for k in order},
        "C": {k: hexcol(C[k]["color"]) for k in order},
        "D": {k: hexcol(D[k]["color"]) for k in order},
    }
    metrics = {g: {k: measure(V[k]) for k in order} for g, V in (("dark", B), ("light", A))}
    data = dict(viewBox=[0, 0, 2000, 536], order=order, dark=dark, light=light,
                metrics=metrics, colors=colors)
    (OUT / "logo-data.json").write_text(json.dumps(data, indent=1))
    for v in "ABCD":
        (OUT / f"3dtarget-logo-{v}.svg").write_text(svg(geo[v], colors[v], order))

    if HTML.exists():
        html = HTML.read_text()
        block = "/*LOGO_DATA_START*/" + json.dumps(data, separators=(",", ":")) + "/*LOGO_DATA_END*/"
        html, n = re.subn(r"/\*LOGO_DATA_START\*/.*?/\*LOGO_DATA_END\*/", lambda m: block, html, flags=re.S)
        assert n == 1, "marker LOGO_DATA non trovato nell'HTML"
        HTML.write_text(html)
        print("aggiornato", HTML.relative_to(ROOT))
    print("scritti", *(p.name for p in sorted(OUT.iterdir())))


if __name__ == "__main__":
    main()
