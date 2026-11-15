"""The kit's signature (KIT.sig.json, committed next to the 3MF) and the diff against it.

A signature is a few KB: per object its plate, position, size, volume per colour and settings; per
plate its nozzle map and tower. `diff` never fails: it lists what changed, and a session either
explains each line or has found a bug. `kitlint --write-sig` accepts the current state.
"""
import datetime
import json
import os
import subprocess

from .checks import INFO, Finding

POS_TOL = 0.01          # mm
SIZE_TOL = 0.05         # mm
VOL_TOL = 0.5           # mm3 ...
VOL_REL = 0.0002        # ... and 0.02 %. Provisional: set from two builds of an unchanged tree.


def sig_path(kit_path):
    return os.path.splitext(kit_path)[0] + ".sig.json"


def signature(kit):
    objs = {}
    for o in kit.objects:
        lo, hi = o.bounds()
        vols = {}
        for v in o.volumes:
            vols[v.colour] = round(vols.get(v.colour, 0.0) + v.volume, 2)
        objs[o.name] = {"plate": o.plate, "pos": [round(float(c), 3) for c in lo[:2]],
                        "size": [round(float(c), 3) for c in hi - lo], "volumes": vols,
                        "slots": sorted({v.slot for v in o.volumes}), "settings": o.settings}
    plates = {str(p.index): {"name": p.name, "mode": p.mode,
                             "nozzle": {str(k): v for k, v in sorted(p.nozzle.items())},
                             "tower": [round(c, 2) for c in p.tower] if p.tower else None}
              for p in kit.plates}
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.abspath(kit.path))).stdout.strip()
    except OSError:
        rev = ""
    return {"written": datetime.date.today().isoformat(), "git": rev,
            "file": os.path.basename(kit.path), "objects": objs, "plates": plates,
            "filaments": [list(f) for f in kit.filaments]}


def write(kit, path=None):
    path = path or sig_path(kit.path)
    with open(path, "w") as f:
        json.dump(signature(kit), f, indent=1, sort_keys=True)
        f.write("\n")
    return path


def _far(a, b, tol):
    return any(abs(x - y) > tol for x, y in zip(a, b))


def diff(kit, old):
    new = signature(kit)
    out = []

    def add(part, msg):
        out.append(Finding(INFO, "diff", part, msg))

    no, nn = old["objects"], new["objects"]
    for n in sorted(set(no) - set(nn)):
        add(n, "removed")
    for n in sorted(set(nn) - set(no)):
        add(n, f"added on plate {nn[n]['plate']}")
    for n in sorted(set(no) & set(nn)):
        a, b = no[n], nn[n]
        if a["plate"] != b["plate"]:
            add(n, f"plate {a['plate']} -> {b['plate']}")
        elif _far(a["pos"], b["pos"], POS_TOL):
            add(n, f"moved ({a['pos'][0]:.2f}, {a['pos'][1]:.2f}) -> ({b['pos'][0]:.2f}, {b['pos'][1]:.2f})")
        if _far(a["size"], b["size"], SIZE_TOL):
            add(n, "size " + " x ".join(f"{c:.2f}" for c in a["size"]) + " -> "
                + " x ".join(f"{c:.2f}" for c in b["size"]))
        for c in sorted(set(a["volumes"]) | set(b["volumes"])):
            va, vb = a["volumes"].get(c, 0.0), b["volumes"].get(c, 0.0)
            if abs(va - vb) > VOL_TOL and abs(va - vb) > VOL_REL * max(va, vb):
                add(n, f"{c} {va:.1f} -> {vb:.1f} mm3")
        if a["slots"] != b["slots"]:
            add(n, f"filament slots {a['slots']} -> {b['slots']}")
        for k in sorted(set(a["settings"]) | set(b["settings"])):
            if a["settings"].get(k) != b["settings"].get(k):
                add(n, f"{k} {a['settings'].get(k)} -> {b['settings'].get(k)}")
    po, pn = old["plates"], new["plates"]
    for i in sorted(set(po) | set(pn), key=int):
        a, b = po.get(i), pn.get(i)
        tag = f"plate {i}"
        if a is None or b is None:
            add(tag, "added" if a is None else "removed")
            continue
        for k in ("name", "mode", "nozzle"):
            if a[k] != b[k]:
                add(tag, f"{k} {a[k]} -> {b[k]}")
        if (a["tower"] is None) != (b["tower"] is None) or (a["tower"] and _far(a["tower"], b["tower"], 0.5)):
            add(tag, f"prime tower {a['tower']} -> {b['tower']}")
    if old.get("filaments") != new["filaments"]:
        add("-", "filament list changed")
    return out
