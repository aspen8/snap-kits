"""
Trace the dark green areas of the upper camouflage from the Airfix A12011 scheme A top view
(ref/vulcan/airfix_a_top.png, not in git) into vulcan/tools/camo_xm594_top.json: rings of (x, y)
in model mm at 1:72, which the colour build reads. Run from the repo root:

  .venv/bin/python vulcan/tools/trace_camo.py [check.png]

Calibration: the "plan" view in vulcan/tools/refs.json (u = 578 + 2.2857 y, v = 60 + 2.2857 x).
Green is told from grey by r - b; panel lines, labels and the roundel are smoothed away (the
roundel's area is filled with whichever colour surrounds most of it: grey).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import measure

ROOT = Path(__file__).resolve().parents[2]
ref = json.load(open(ROOT / "vulcan/tools/refs.json"))["plan"]
A = np.array(ref["affine"], float)
im = np.array(Image.open(ROOT / ref["image"]).convert("RGB")).astype(int)
r, g, b = im[..., 0], im[..., 1], im[..., 2]
lum = im.mean(2)
paint = (lum < 215) & (lum > 50)
paint[:440, :430] = False                      # the colour key and notes
paint[990:, :480] = False                      # the next view's corner
paint[960:, 700:] = False                      # the Blue Steel drawing
lab, n = ndi.label(ndi.binary_closing(paint, iterations=2))
body = lab == 1 + int(np.argmax(ndi.sum(paint, lab, range(1, n + 1))))
body = ndi.binary_fill_holes(body)
green = body & (r - b > 45) & (g - b > 25)
green = ndi.median_filter(green.astype(np.uint8), size=7).astype(bool)      # panel lines out
green = ndi.binary_opening(ndi.binary_closing(green, iterations=3), iterations=3)
green = ndi.binary_dilation(green, iterations=2)                            # a little past the outline: clipped by the model
lab, n = ndi.label(green)
sizes = ndi.sum(green, lab, range(1, n + 1))
green = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s > 150])       # specks out
lab, n = ndi.label(~green)                                                  # small holes (ochre dots, vents) filled
sizes = ndi.sum(~green, lab, range(1, n + 1))
green = green | np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s < 600])

rings = []
k = A[0, 1]
for c in measure.find_contours(np.pad(green.astype(float), 1), 0.5):
    v, u = c[:, 0] - 1, c[:, 1] - 1
    x, y = (v - A[1, 2]) / A[1, 0], (u - A[0, 2]) / A[0, 1]
    pts = measure.approximate_polygon(np.c_[x, y], 0.25)
    if len(pts) >= 4:
        rings.append([[round(float(p[0]), 2), round(float(p[1]), 2)] for p in pts])
out = ROOT / "vulcan/tools/camo_xm594_top.json"
json.dump({"_source": "Airfix A12011 scheme A (XM594, 1966) top view: dark green areas, (x, y) mm at 1:72, even-odd rings",
           "rings": rings}, open(out, "w"))
print(f"{len(rings)} rings, {sum(len(q) for q in rings)} points -> {out}")
if len(sys.argv) > 1:
    chk = im.copy().astype(np.uint8)
    edge = green ^ ndi.binary_erosion(green, iterations=2)
    chk[edge] = (255, 0, 255)
    Image.fromarray(chk).save(sys.argv[1])
