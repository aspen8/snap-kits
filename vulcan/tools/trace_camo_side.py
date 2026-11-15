"""
Trace the camouflage of the port side from the Airfix A12011 scheme A side view
(ref/vulcan/airfix_a_side_port.png, not in git) into vulcan/tools/camo_xm594_side.json:
  green: the dark green areas, (x, z) rings
  upper: everything painted in the upper colours (grey or green), so its lower edge is the line
         where the camouflage meets the white underside, (x, z) rings
in model mm at 1:72. The colour build projects them across the span onto the nose sides, the tail
cone and the fin. Run from the repo root:

  .venv/bin/python vulcan/tools/trace_camo_side.py [check.png]

Calibration: the "side" view in vulcan/tools/refs.json (u = 153 + 2.2857 x, v = 186 - 2.2857 z).
Markings (roundel, fin flash, serial, labels) are filled with the colour round them.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import measure

ROOT = Path(__file__).resolve().parents[2]
ref = json.load(open(ROOT / "vulcan/tools/refs.json"))["side"]
A = np.array(ref["affine"], float)
im = np.array(Image.open(ROOT / ref["image"]).convert("RGB")).astype(int)
r, g, b = im[..., 0], im[..., 1], im[..., 2]
lum = im.mean(2)
H, W = lum.shape
paint = lum < 232
paint[:, :140] = False                         # the probe's tip and the margin
lab, n = ndi.label(ndi.binary_closing(paint, iterations=2))
body = lab == 1 + int(np.argmax(ndi.sum(paint, lab, range(1, n + 1))))
body = ndi.binary_fill_holes(body)


def clean(mask, close=3, keep=150, hole=600):
    mask = ndi.median_filter(mask.astype(np.uint8), size=5).astype(bool)
    mask = ndi.binary_opening(ndi.binary_closing(mask, iterations=close), iterations=2)
    lab, n = ndi.label(mask)
    sizes = ndi.sum(mask, lab, range(1, n + 1))
    mask = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > keep])
    lab, n = ndi.label(~mask)
    sizes = ndi.sum(~mask, lab, range(1, n + 1))
    return mask | np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s < hole])


green = clean(body & (r - b > 25) & (g - b > 15) & (lum < 190))
upper = clean(body & (lum < 205), close=4, hole=4000)        # grey, green, markings: not the white underside


def rings_of(mask):
    out = []
    for c in measure.find_contours(np.pad(mask.astype(float), 1), 0.5):
        v, u = c[:, 0] - 1, c[:, 1] - 1
        x, z = (u - A[0, 2]) / A[0, 0], (v - A[1, 2]) / A[1, 1]
        pts = measure.approximate_polygon(np.c_[x, z], 0.25)
        if len(pts) >= 4:
            out.append([[round(float(p[0]), 2), round(float(p[1]), 2)] for p in pts])
    return out


res = {"_source": "Airfix A12011 scheme A (XM594, 1966) port side view: (x, z) mm at 1:72, even-odd rings",
       "green": rings_of(green), "upper": rings_of(upper)}
out = ROOT / "vulcan/tools/camo_xm594_side.json"
json.dump(res, open(out, "w"))
print(f"green {len(res['green'])} rings, upper {len(res['upper'])} rings -> {out}")
if len(sys.argv) > 1:
    chk = im.copy().astype(np.uint8)
    chk[green ^ ndi.binary_erosion(green, iterations=1)] = (255, 0, 255)
    chk[upper ^ ndi.binary_erosion(upper, iterations=1)] = (0, 200, 255)
    Image.fromarray(chk).save(sys.argv[1])
