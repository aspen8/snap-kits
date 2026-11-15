"""
Avro Vulcan B.2 snap kit: colour build. Paints each part from vulcan.py into per-filament volumes
and writes the STLs, a colour preview (GLB) and the Bambu Studio project.

  python vulcan/cad/colour.py OUT_DIR [SCHEME]         SCHEME: camo (default) or white
  ONLY=name,name python vulcan/cad/colour.py OUT_DIR   (just some parts)

camo:  XM594, Scampton 1966 (Airfix A12011 scheme A): Medium Sea Grey and Dark Green on top,
       white underneath. The green areas come from vulcan/tools/camo_xm594_top.json
       (vulcan/tools/trace_camo.py made it from the Airfix top view).
white: anti-flash white overall (scheme B, XM602, 1963).

v2 of the colour: the camouflage from the top view on upper surfaces and from the side view on the
nose sides, tail cone and fin (vulcan/tools/camo_xm594_side.json, traced by trace_camo_side.py),
so on the nose it runs below the shell split; one 84-inch Type D roundel on the upper port wing and
one on each side of the nose (the Airfix notes); fin flash and the serial XM594 on the fin; canopy
glazing; black radome and ducts; silver engine faces and gear with black tyres. The glazing and
the serial are in roundel blue (a very dark blue), which keeps every plate to five colours.
"""
import json
import os
import sys
import time
from pathlib import Path

import manifold3d as mf
from manifold3d import Manifold as M
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
    6: ("Roundel Red", "#B3262E"),
    7: ("Roundel Blue", "#22305C"),
}
GREY, GREEN, WHITE, BLACK, SILVER, RED, BLUE = range(1, 8)
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
GLAZE_FRAME = 0.9             # frame width between the panels (0.7 mm printed)
# Windscreen (v33, user: "the front 3 windows should be 4 sided"): seen head-on, a rectangular
# centre panel and a trapezoid each side, its outer edge following the canopy's slope. (y, z)
# outlines, projected along x onto the canopy's sloping front.
GLAZE_SCREEN = [
    [(-2.2, 23.0), (2.2, 23.0), (2.2, 27.6), (-2.2, 27.6)],
    [(3.1, 23.0), (7.8, 23.0), (4.8, 27.6), (3.1, 27.6)],
    [(-3.1, 23.0), (-3.1, 27.6), (-4.8, 27.6), (-7.8, 23.0)],
]
# Side window: a triangle just behind each side panel, its front edge one frame behind the panel's
# rear edge (which runs from x 68.6, z 23 to x 70.5, z 27.6 on the canopy): user, "line up with the
# main 3". (x, z)
GLAZE_SIDE = [(69.5, 23.0), (74.5, 23.0), (71.3, 27.2)]
GLAZE_PORT = (77.5, 27.0, 2.3, 42.0)     # porthole: x, z, radius, and the angle above the horizon it faces (42: 0.74 as tall as wide from the side, as the side photo):
                                         # a circle seen from there, an ellipse from the side (user review)


def glazing():
    if "glaze" not in _cache:
        from shapely.geometry import Point
        to_x = np.array([[0, 0, 1, 50.0], [1, 0, 0, 0], [0, 1, 0, 0]], float)   # (y, z) along x, from x 50
        screen = K.cs([np.array(p) for p in GLAZE_SCREEN]).extrude(19.0).transform(to_x)
        sides = V._plate_xz([np.array(GLAZE_SIDE)], -30.0, 30.0)
        px, pz, pr, el = GLAZE_PORT
        from shapely.geometry import Polygon, LineString
        T = np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0]], float)
        sec = Polygon(np.vstack(V.canopy().transform(T).slice(float(px)).to_polygons()))
        py = sec.intersection(LineString([(0, pz), (30, pz)])).bounds[2]     # on the canopy's side
        for sgn in (1, -1):
            c = M.cylinder(8.0, pr, pr, 48).translate([0, 0, -4.0])      # axis along z, centred
            c = c.rotate([-(90.0 - el) * sgn, 0, 0]).translate([px, sgn * py, pz])
            sides = sides + c
        _cache["glaze"] = (screen, sides)
    return _cache["glaze"]


def xz_prism(sec, y0=-80.0, y1=80.0):
    """A CrossSection in (x, z) extruded across the span from y0 to y1."""
    return sec.extrude(y1 - y0).rotate([90, 0, 0]).translate([0, y1, 0])


def side_camo():
    """(upper colours, green) as prisms across the span, from the side view."""
    if "side" not in _cache:
        d = json.load(open(HERE.parent / "tools" / "camo_xm594_side.json"))
        _cache["side"] = tuple(xz_prism(K.cs([np.array(r) for r in d[k]])) for k in ("upper", "green"))
    return _cache["side"]


# Where the side view's pattern is used rather than the top view's: the nose sides below the
# top of the fuselage's shoulder, and the tail cone behind the wing.
SIDE_ZONES = [(-10.0, 112.0, 13.0, 40.0), (361.0, 440.0, 9.0, 16.0)]     # x from, x to, below z, within |y|


def side_zone():
    return mf.Manifold.batch_boolean([K.box(x0, x1, -yw, yw, -V.BIG, z) for x0, x1, z, yw in SIDE_ZONES], mf.OpType.Add)


# Roundels: Type D, red : white : blue diameters 1 : 2 : 3 (Airfix A12011 scheme A).
ROUNDEL_WING = (309.2, -164.2, 30.3)     # x, y, diameter: 84 inches, upper port wing only (Airfix notes)
ROUNDEL_NOSE = (75.3, 3.7, 18.6)         # x, z, diameter: both sides of the nose
FIN_FLASH = (336.4, 348.3, 28.0, 36.3)   # x from (red, at the front), x to, z from, z to
FIN_SERIAL = ("XM594", 342.0, 22.55, 5.7)  # text, x centre, z centre, height (both sides, read from outside)


def roundel_ops(discs, prism):
    """[(colour, region)] for a Type D roundel: blue, then white, then red on top."""
    return [(c, prism(k)) for c, k in ((BLUE, 1.0), (WHITE, 2 / 3), (RED, 1 / 3))]


def wing_roundel():
    x, y, d = ROUNDEL_WING
    return roundel_ops(None, lambda k: K.prism_z(K.disc(x, y, d * k)))


def nose_roundels():
    x, z, d = ROUNDEL_NOSE
    return roundel_ops(None, lambda k: xz_prism(K.disc(x, z, d * k)))


def tyres(name):
    """Black tyres round each wheel's hub (gear halves)."""
    g = V.NOSE_GEAR if name.startswith("nose") else V.MAIN_GEAR
    rmax = max(r for _, r in g["wheel_profile"])
    out = []
    for x, z in (g.get("wheels") or [g["wheel"]]):
        ann = K.disc(x, z, 2 * rmax + 2.0) - K.disc(x, z, 2 * rmax * 0.62)
        out.append(xz_prism(ann, -200.0, 200.0))
    return mf.Manifold.batch_boolean(out, mf.OpType.Add)


def colour_part(name, P):
    """{filament: Manifold} for one part (assembled frame)."""
    upper = name.endswith("_upper")
    lower = name.endswith("_lower")
    if name == "radome":
        return {BLACK: P}
    if name.startswith("engine_face"):
        return {SILVER: P}
    if "gear" in name:
        return K.paint(P, [(BLACK, tyres(name))], SILVER)
    if name.startswith("stand"):
        return {BLACK: P}
    if name.startswith("fin_"):
        if SCHEME == "white":
            return {WHITE: P}
        port = name.endswith("port")
        x0, x1, z0, z1 = FIN_FLASH
        w = (x1 - x0) / 3
        text, xc, zc, h = FIN_SERIAL
        ops = [(GREEN, side_camo()[1])]
        ops += [(c, xz_prism(K.cs([np.array([(x0 + i * w, z0), (x0 + (i + 1) * w, z0), (x0 + (i + 1) * w, z1), (x0 + i * w, z1)])])))
                for i, c in enumerate((RED, WHITE, BLUE))]
        ops.append((BLUE, xz_prism(K.text_section(text, h, xc, zc, mirror=not port))))
        return K.paint(P, [(c, r ^ outer_skin()) for c, r in ops], GREY)
    if upper or lower:
        ops = []
        base = WHITE
        skin = outer_skin()
        if SCHEME == "camo":
            zone = side_zone()
            sup, sgreen = side_camo()
            if upper:
                base = GREY
                ops.append((GREEN, (camo_prism() - zone) ^ skin))
            else:
                ops.append((GREY, sup ^ zone ^ skin))
            ops.append((GREEN, sgreen ^ zone ^ skin))
            if name.startswith("front"):
                ops += [(c, r ^ skin) for c, r in nose_roundels()]
            if upper and name.startswith("wing_port"):
                ops += [(c, r ^ skin) for c, r in wing_roundel()]
        ops.append((BLACK, duct_zone()))
        if name == "front_upper":
            screen, sides = glazing()
            ops.append((BLUE, (screen + sides) ^ skin ^ V.canopy()))
        return K.paint(P, ops, base)
    return {WHITE: P}            # doors, bay roof, Blue Steel, keys, probe


PLATE_GROUPS = [
    ("Upper centre", lambda n: n == "centre_upper"),
    ("Upper wings and nose", lambda n: n == "front_upper" or (n.startswith("wing_") and n.endswith("_upper"))),
    ("Fin", lambda n: n.startswith("fin_")),
    ("Lower centre", lambda n: n == "centre_lower"),
    ("Lower wings and nose", lambda n: n == "front_lower" or (n.startswith("wing_") and n.endswith("_lower"))),
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
