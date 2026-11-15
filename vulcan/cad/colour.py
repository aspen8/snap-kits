"""
Avro Vulcan B.2 snap kit: colour build. Paints each part from vulcan.py into per-filament volumes
and writes the STLs, a colour preview (GLB) and the Bambu Studio project.

  python vulcan/cad/colour.py OUT_DIR [SCHEME]         SCHEME: camo (default) or white
  ONLY=name,name python vulcan/cad/colour.py OUT_DIR   (just some parts)

camo:  XM594, Scampton 1966 (Airfix A12011 scheme A): Medium Sea Grey and Dark Green on top,
       white underneath. The green areas come from vulcan/tools/camo_xm594_top.json
       (vulcan/tools/trace_camo.py made it from the Airfix top view).
white: anti-flash white overall (scheme B, XM602, 1963).

v1 of the colour: the camouflage pattern, black radome, ducts and fin cap, silver engine faces
and gear. Not yet: roundels, fin flash, serial, squadron badge, the fin's own
pattern (it is plain grey), tyres. The camouflage ends at the split between the shells: on the
real aircraft it runs a little lower on the nose.
"""
import json
import os
import sys
import time
from pathlib import Path

import manifold3d as mf
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_argv = sys.argv
sys.argv = [_argv[0], str(Path(_argv[1]) / "geo")] if len(_argv) > 1 else _argv
import kitlib as K            # noqa: E402
import vulcan as V            # noqa: E402
sys.argv = _argv
from kitlib import mesh_of    # noqa: E402

SCHEME = sys.argv[2] if len(sys.argv) > 2 else "camo"
_P = V._P
SKIN = 0.8 * _P               # coloured skin depth (0.8 mm printed)
SKIN_OUT = 0.05               # regions reach just past the surface (no zero-thickness sheets)

FILAMENTS = {
    1: ("Medium Sea Grey", "#9EA3A6"),
    2: ("Dark Green", "#4A5238"),
    3: ("White", "#F2F2F0"),
    4: ("Black", "#1C1C1C"),
    5: ("Silver", "#B8BCC0"),
}
GREY, GREEN, WHITE, BLACK, SILVER = range(1, 6)
MAX_COLOURS = 5
BED = (168.0, 240.0)          # packing area from BED_MARGIN: x > 190 is left for the prime tower
BED_MARGIN = (22.0, 6.0)      # the X2D's second nozzle can't reach x < 20.5, and brims need room
PLATE_GAP = 6.0


def camo_prism():
    d = json.load(open(HERE.parent / "tools" / "camo_xm594_top.json"))
    return K.prism_z(K.cs([np.array(r) for r in d["rings"]]))


_cache = {}


def outer_skin():
    """The outer SKIN of the whole aircraft's upper and side surfaces (never its underside, and
    measured on the assembled shape, so joint faces, slots and bays are not skin)."""
    if "skin" not in _cache:
        a = V.airframe() + V.fin()
        core = a.translate([0, 0, -SKIN])
        for v in ([SKIN, 0, 0], [-SKIN, 0, 0], [0, SKIN, 0], [0, -SKIN, 0]):
            core = core ^ a.translate(v)
        _cache["skin"] = K.box(-V.BIG, V.BIG, -V.BIG, V.BIG, -V.BIG, V.BIG) - core
    return _cache["skin"]


def duct_zone():
    """Everything within SKIN of the intake ducts and the jet pipe bores: black."""
    if "duct" not in _cache:
        d = V.intake_ducts()
        _, bores = V.jet_pipes()
        void = d + bores
        void = void + void.mirror([0, 1, 0])
        grown = void
        for v in ([0, SKIN, 0], [0, -SKIN, 0], [0, 0, SKIN], [0, 0, -SKIN], [SKIN, 0, 0]):
            grown = grown + void.translate(v)
        _cache["duct"] = grown
    return _cache["duct"]


# Canopy glazing (side photo, head-on photo): the canopy is metal with small windows. Three flat
# windscreen panels on its sloping front, a small side window behind each side panel, and a round
# porthole on each side further back. Painted black into the skin; the frames are the canopy's
# own colour.
GLAZE_FRAME = 0.9             # frame width round and between the windscreen panels (0.7 mm printed)
GLAZE_SCREEN = (69.0, 22.3, 28.8, 2.2)   # windscreen: section at this x, from z to z, centre panel half-width
GLAZE_DIAG = ((60.0, 22.3), (69.0, 27.5))   # the side panels' lower frame: a diagonal in side view (x, z)
GLAZE_SIDE = [(63.6, 23.0), (70.4, 23.0), (70.4, 26.4), (68.6, 26.4)]   # side window below it, (x, z)
GLAZE_PORT = (74.8, 27.0, 2.3)           # porthole: x, z, radius


def glazing():
    if "glaze" not in _cache:
        from shapely.geometry import Polygon, Point, box as sbox
        x, z0, z1, hc = GLAZE_SCREEN
        f = GLAZE_FRAME
        T = np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0]], float)
        sec = Polygon(np.vstack(V.canopy().transform(T).slice(float(x)).to_polygons()))
        win = sec.buffer(-f).intersection(sbox(-50, z0, 50, z1))
        win = win.difference(sbox(hc, -50, hc + f, 50)).difference(sbox(-hc - f, -50, -hc, 50))
        polys = [np.array(g.exterior.coords)[:-1] for g in getattr(win, "geoms", [win])]
        # (y, z) outlines extruded along x, from x 50 to the section
        screen = K.cs(polys).extrude(x - 50.0).transform(np.array([[0, 0, 1, 50.0], [1, 0, 0, 0], [0, 1, 0, 0]], float))
        (xa, za), (xb, zb) = GLAZE_DIAG                # side panels stop at the diagonal frame
        k = (zb - za) / (xb - xa)
        below = V._plate_xz([[(40.0, za - (xa - 40.0) * k - 0.0), (90.0, za + (90.0 - xa) * k), (90.0, -50.0), (40.0, -50.0)]], -50.0, 50.0)
        below = below - K.box(-V.BIG, V.BIG, -hc - f / 2, hc + f / 2, -V.BIG, V.BIG)
        screen = screen - below
        side = Polygon(GLAZE_SIDE)
        px, pz, pr = GLAZE_PORT
        xz = [np.array(side.exterior.coords)[:-1], np.array(Point(px, pz).buffer(pr, 24).exterior.coords)[:-1]]
        sides = V._plate_xz(xz, -30.0, 30.0)
        _cache["glaze"] = (screen, sides)
    return _cache["glaze"]


def colour_part(name, P):
    """{filament: Manifold} for one part (assembled frame)."""
    upper = name.endswith("_upper")
    lower = name.endswith("_lower")
    if name == "radome":
        return {BLACK: P}
    if name.startswith("engine_face") or "gear" in name:
        return {SILVER: P}
    if name.startswith("stand"):
        return {BLACK: P}
    if name.startswith("fin_"):
        if SCHEME == "white":
            base = WHITE
        else:
            base = GREY
        cap = K.box(350.0, 420.0, -10, 10, V.FIN_CAP[1][3] - 0.2, 100.0)       # the fin cap fairing
        return K.paint(P, [(BLACK, cap)], base)
    if upper or lower:
        ops = []
        base = WHITE
        if upper and SCHEME == "camo":
            base = GREY
            ops.append((GREEN, camo_prism() ^ outer_skin()))
        ops.append((BLACK, duct_zone()))
        if name == "front_upper":
            screen, sides = glazing()
            canopy = V.canopy()
            ops.append((BLACK, (screen + sides) ^ outer_skin() ^ canopy))
        return K.paint(P, ops, base)
    return {WHITE: P}            # doors, bay roof, Blue Steel, keys, probe


PLATE_GROUPS = [
    ("Upper centre", lambda n: n in ("centre_upper", "front_upper")),
    ("Upper wings", lambda n: n.startswith("wing_") and n.endswith("_upper")),
    ("Fin", lambda n: n.startswith("fin_")),
    ("Lower centre", lambda n: n in ("centre_lower", "front_lower")),
    ("Lower wings", lambda n: n.startswith("wing_") and n.endswith("_lower")),
    ("Black and silver", lambda n: n == "radome" or n.startswith(("stand", "engine_face")) or "gear" in n),
    ("White small parts", lambda n: True),
]

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out/vulcan/colour")
    (out / "stl").mkdir(parents=True, exist_ok=True)
    only = [o for o in os.environ.get("ONLY", "").split(",") if o]
    objs, preview = {}, []
    for name, (P, pose) in V.build().items():
        if only and not any(o in name for o in only):
            continue
        t0 = time.time()
        P, dropped = K.largest_piece(P)
        if any(abs(v) > 1.0 for v in dropped):
            print(f"!! {name}: dropped loose pieces {[round(v, 1) for v in dropped if abs(v) > 1.0]} mm3")
        vols = colour_part(name, P)
        pf = lambda m, pose=pose: pose(m).scale([V.PRINT_K] * 3)
        for c, v in vols.items():
            preview.append((c, *mesh_of(v.scale([V.PRINT_K] * 3)), name))
        posed = {c: pf(v) for c, v in vols.items()}
        lo = np.min([v.bounding_box()[:3] for v in posed.values()], axis=0)
        hi = np.max([v.bounding_box()[3:] for v in posed.values()], axis=0)
        posed = {c: v.translate(list(-lo)) for c, v in posed.items()}
        trimesh.Trimesh(*mesh_of(pf(P).translate(list(-lo)))).export(out / "stl" / f"{name}.stl")
        objs[name] = {"vols": posed, "size": (hi - lo)[:2]}
        print(f"{name:24s} " + ", ".join(f"{FILAMENTS[c][0]} {v.volume() / 1000:.2f}cc" for c, v in sorted(posed.items()))
              + f"   [{time.time() - t0:.1f}s]", flush=True)

    scene = trimesh.Scene()
    for i, (c, Vv, F, pname) in enumerate(preview):
        m = trimesh.Trimesh(Vv, F)
        m.visual.face_colors = [int(FILAMENTS[c][1][k:k + 2], 16) for k in (1, 3, 5)] + [255]
        scene.add_geometry(m, node_name=f"{pname}__{i}", geom_name=f"{pname}__{i}")
    scene.export(out / f"vulcan_{SCHEME}_preview.glb")

    plates_all, seen = [], set()
    for gname, pred in PLATE_GROUPS:
        group = sorted((n for n in objs if n not in seen and pred(n)), key=lambda n: -objs[n]["size"][0] * objs[n]["size"][1])
        seen.update(group)
        for items in K.pack([(n, tuple(objs[n]["size"])) for n in group], BED, PLATE_GAP):
            plates_all.append((gname, items))
    objects = []
    for pi, (gname, items) in enumerate(plates_all):
        cols = sorted({c for n, *_ in items for c in objs[n]["vols"]})
        print(f"plate {pi + 1} ({gname}): " + ", ".join(FILAMENTS[c][0] for c in cols) + " | " + ", ".join(n for n, *_ in items))
        assert len(cols) <= MAX_COLOURS, f"plate {pi + 1} needs {len(cols)} colours"
        for n, x, y, rot90 in items:
            vols = objs[n]["vols"]
            if rot90:
                sy = objs[n]["size"][1]
                vols = {c: v.rotate([0, 0, 90]).translate([sy, 0, 0]) for c, v in vols.items()}
            objects.append({"name": n, "placement": (pi, x + BED_MARGIN[0], y + BED_MARGIN[1]),
                            "volumes": [(c, *mesh_of(v)) for c, v in sorted(vols.items())]})
    if not only:
        names = [f"{g} {i + 1}" for i, (g, _) in enumerate(plates_all)]
        K.write_3mf(out / f"vulcan_{SCHEME}_kit.3mf", objects, names, None, FILAMENTS,
                    f"Avro Vulcan B.2 snap kit 1:96 ({SCHEME})")
        print("wrote", out / f"vulcan_{SCHEME}_kit.3mf")
