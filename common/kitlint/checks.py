"""Print-pose checks that need only the 3MF: solid, plate, pairs.

Each check is a function (kit, rules) -> [Finding]. Thresholds are printed millimetres and come from
common/briefs/kit-lint-design.md, where each is explained.
"""
import re
from dataclasses import dataclass

import numpy as np

FAIL, WARN, INFO = "FAIL", "WARN", "info"


@dataclass
class Finding:
    level: str
    check: str
    part: str
    msg: str
    value: float = None     # the measured figure an accepted exception's `limit` is compared with
    accepted: str = None


# ---------------------------------------------------------------- solid

VOL_TOL = 0.5           # mm3 ...
VOL_REL = 0.0002        # ... or 0.02 %, whichever is larger
PIECE_MIN = 0.05        # mm3: smaller pieces are mesh dust (a 0.01 sliver on wing_outer_stbd)
HOLLOW_MAX = 0.5        # mm3: a sealed hollow bigger than this is a design error


def _manifold(V, F):
    import manifold3d as mf
    mesh = mf.Mesh(vert_properties=np.ascontiguousarray(V, np.float32),
                   tri_verts=np.ascontiguousarray(F, np.uint32))
    m = mf.Manifold(mesh)
    if m.status() != mf.Error.NoError:
        mesh.merge()
        m = mf.Manifold(mesh)
    return m


def _pieces(vols):
    """Connected pieces of an object's colour volumes, with their signed volumes. Volumes join where
    they share a vertex (to 0.001 mm, the 3MF's precision): the painted volumes are cut from one
    solid, so neighbours share their boundary. Topology, not a boolean union: a union of the big
    parts takes minutes."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    keys, faces, off = [], [], 0
    for v in vols:
        keys.append(np.round(v.V * 1000).astype(np.int64))
        faces.append(v.F + off)
        off += len(v.V)
    K = np.vstack(keys)
    _, idx = np.unique(K, axis=0, return_inverse=True)
    idx = idx.ravel()
    F = idx[np.vstack(faces)]
    n = idx.max() + 1
    r = np.concatenate([F[:, 0], F[:, 1]])
    c = np.concatenate([F[:, 1], F[:, 2]])
    _, lab = connected_components(coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n)), directed=False)
    # signed volume of each piece, from the triangles of each colour volume
    vol = np.zeros(lab.max() + 1)
    for v, fv in zip(vols, faces):
        T = v.V[v.F]
        tv = np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])) / 6.0
        np.add.at(vol, lab[idx[fv[:, 0]]], tv)
    return vol


def solid(kit, rules):
    import manifold3d as mf
    out = []
    for o in kit.objects:
        if not o.volumes:
            out.append(Finding(FAIL, "solid", o.name, "no geometry"))
            continue
        good = []
        for v in o.volumes:
            m = _manifold(v.V, v.F)
            if m.status() != mf.Error.NoError:
                out.append(Finding(FAIL, "solid", o.name, f"{v.colour} volume is not a closed manifold ({m.status().name})"))
            elif m.volume() <= 0:
                out.append(Finding(FAIL, "solid", o.name, f"{v.colour} volume is empty or inside out ({m.volume():.2f} mm3)"))
            else:
                good.append(v)
        if not good:
            continue
        pieces = _pieces(good)
        solid_ = sorted(p for p in pieces if p > PIECE_MIN)
        if len(solid_) > 1:
            small = solid_[:-1]
            out.append(Finding(FAIL, "solid", o.name,
                               f"{len(solid_)} separate pieces; loose: {', '.join(f'{p:.2f}' for p in small[:5])} mm3",
                               sum(small)))
        hollow = [-p for p in pieces if p < -HOLLOW_MAX]
        if hollow:
            out.append(Finding(WARN, "solid", o.name, f"sealed hollow of {max(hollow):.1f} mm3", max(hollow)))
    return out


# ---------------------------------------------------------------- plate

AUX_X = 20.5            # the X2D's second nozzle can't reach x < 20.5 (extruder_printable_area)
AUX_MARGIN = 0.5
GAP = 2.0               # parts apart, plus both brims
TOWER_W = 35.0          # prime_tower_width; depth below is kitlib.TOWER_DEPTH
TOWER_D = 50.0
TOWER_CLEAR = 12.0      # kitlib.TOWER_CLEAR
TOWER_FAIL = 6.0
MAX_COLOURS = 5
BAD_CHARS = re.compile(r'[<>:/\\|?*"]')


def _bed(kit):
    s = kit.settings
    pts = [tuple(map(float, p.split("x"))) for p in s.get("printable_area", ["0x0", "256x256"])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    aux = AUX_X
    epa = s.get("extruder_printable_area")
    if epa and len(epa) > 1:
        aux = min(float(p.split("x")[0]) for p in epa[1].split(","))
    w = float(s.get("prime_tower_width", TOWER_W))
    return (min(xs), min(ys), max(xs), max(ys)), float(s.get("printable_height", 256)), aux, w


def _brim(o, kit):
    t = o.settings.get("brim_type", kit.settings.get("brim_type", "auto_brim"))
    if t == "no_brim":
        return 0.0, True
    if t == "auto_brim":
        return 0.0, False           # width decided at slicing: only the slice check can see it
    return float(o.settings.get("brim_width", kit.settings.get("brim_width", 0))), True


def plate(kit, rules):
    from shapely.geometry import MultiPoint, box
    out = []
    (bx0, by0, bx1, by1), height, aux_x, tower_w = _bed(kit)
    aux_colours = rules.get("aux_colours")
    names = [o.name for o in kit.objects]
    for n in sorted({n for n in names if names.count(n) > 1}):
        out.append(Finding(FAIL, "plate", n, "object name used more than once"))
    for n in names:
        if BAD_CHARS.search(n):
            out.append(Finding(FAIL, "plate", n, "name has a character Bambu Studio refuses"))
    if not kit.settings:
        out.append(Finding(FAIL, "plate", "-", "no project settings: Bambu Studio opens bare geometry"))
    nfil = len(kit.filaments)
    tx = kit.settings.get("wipe_tower_x", [])
    if kit.settings and len(tx) != len(kit.plates):
        out.append(Finding(FAIL, "plate", "-", f"{len(tx)} prime tower positions for {len(kit.plates)} plates"))
    for o in kit.objects:
        if not o.plate:
            out.append(Finding(WARN, "plate", o.name, "on no plate"))
    for p in kit.plates:
        tag = f"plate {p.index}"
        if any(BAD_CHARS.search(c) for c in p.name):
            out.append(Finding(FAIL, "plate", tag, f"plate name {p.name!r} has a character Bambu Studio refuses"))
        slots = sorted({v.slot for o in p.objects for v in o.volumes})
        for s in slots:
            if s > nfil:
                out.append(Finding(FAIL, "plate", tag, f"uses filament slot {s}; the project has {nfil}"))
        if len(slots) > MAX_COLOURS:
            out.append(Finding(FAIL, "plate", tag, f"{len(slots)} colours (the printer holds {MAX_COLOURS})", len(slots)))
        auto = p.mode != "Manual"
        on2 = [s for s in slots if p.nozzle.get(s, 1) == 2]
        uses_aux = auto or bool(on2)
        if aux_colours is not None and not auto and len(on2) > aux_colours:
            cn = sorted({v.colour for o in p.objects for v in o.volumes if v.slot in on2})
            out.append(Finding(FAIL, "plate", tag, f"{len(on2)} colours on the second nozzle ({', '.join(cn)}); "
                                                   f"lint.toml allows {aux_colours}", len(on2)))
        if auto and len(slots) > 1:
            out.append(Finding(WARN, "plate", tag, "filament grouping is Auto For Flush: Bambu may put any "
                                                   "colour on the second nozzle"))
        heights = {o.settings.get("layer_height", kit.settings.get("layer_height")) for o in p.objects}
        if len(slots) > 1 and len(heights) > 1:
            out.append(Finding(WARN, "plate", tag, f"layer heights {'/'.join(sorted(map(str, heights)))} on a "
                                                   "multi-colour plate (prime tower)"))
        hulls = {}
        for o in p.objects:
            lo, hi = o.bounds()
            brim, known = _brim(o, kit)
            if abs(lo[2]) > 0.01:
                out.append(Finding(FAIL, "plate", o.name, f"lowest point at z {lo[2]:.3f}, not on the bed", lo[2]))
            if uses_aux and lo[0] < aux_x + AUX_MARGIN:
                out.append(Finding(FAIL, "plate", o.name, f"{tag}: x min {lo[0]:.1f} is outside the second "
                                                          f"nozzle's reach (from {aux_x})", lo[0]))
            elif uses_aux and known and brim and lo[0] - brim < aux_x + AUX_MARGIN:
                out.append(Finding(FAIL, "plate", o.name, f"{tag}: {brim:g} mm brim reaches x {lo[0] - brim:.1f} "
                                                          f"(second nozzle from {aux_x})", lo[0] - brim))
            if lo[0] - brim < bx0 or lo[1] - brim < by0 or hi[0] + brim > bx1 or hi[1] + brim > by1:
                out.append(Finding(FAIL, "plate", o.name, f"{tag}: off the bed ({lo[0] - brim:.1f}, {lo[1] - brim:.1f})"
                                                          f" to ({hi[0] + brim:.1f}, {hi[1] + brim:.1f})"))
            if hi[2] > height:
                out.append(Finding(FAIL, "plate", o.name, f"{hi[2]:.1f} mm tall (printer {height:g})", hi[2]))
            hulls[o.name] = (MultiPoint(o.xy()).convex_hull, brim)
        items = list(hulls.items())
        for i, (a, (ha, ba)) in enumerate(items):
            for b, (hb, bb) in items[i + 1:]:
                d = ha.distance(hb)
                if d < GAP + ba + bb:
                    out.append(Finding(WARN, "plate", f"{a} x {b}", f"{tag}: outlines {d:.1f} mm apart "
                                                                    f"(want {GAP + ba + bb:g} with brims)", d))
        if p.tower and len(slots) > 1:
            x, y = p.tower
            if x < aux_x + 1.5 or y < by0 + 2 or x + tower_w > bx1 - 15 or y + TOWER_D > by1 - 2:
                out.append(Finding(FAIL, "plate", tag, f"prime tower at ({x:.0f}, {y:.0f}) is too near the bed edge"))
            t = box(x, y, x + tower_w, y + TOWER_D)
            for n, (h, brim) in hulls.items():
                d = t.distance(h)
                if d < TOWER_FAIL + brim:
                    out.append(Finding(FAIL, "plate", n, f"{tag}: {d:.1f} mm from the prime tower", d))
                elif d < TOWER_CLEAR:
                    out.append(Finding(WARN, "plate", n, f"{tag}: {d:.1f} mm from the prime tower "
                                                         f"(want {TOWER_CLEAR:g})", d))
    return out


# ---------------------------------------------------------------- pairs

PAIR_REL = 0.005        # port and starboard volumes within 0.5 %


def _mirror(name):
    toks = name.split("_")
    if "port" in toks:
        return "_".join("stbd" if t == "port" else t for t in toks)
    if "stbd" in toks:
        return "_".join("port" if t == "stbd" else t for t in toks)
    return None


def pairs(kit, rules):
    out = []
    by = {o.name: o for o in kit.objects}
    for o in kit.objects:
        m = _mirror(o.name)
        if m is None:
            continue
        if m not in by:
            out.append(Finding(FAIL, "pairs", o.name, f"no {m}"))
            continue
        if "port" not in o.name.split("_"):
            continue
        s = by[m]
        lh = (o.settings.get("layer_height"), s.settings.get("layer_height"))
        if lh[0] != lh[1]:
            out.append(Finding(WARN, "pairs", o.name, f"layer height {lh[0]} vs {m} {lh[1]}"))
        va, vb = sum(v.volume for v in o.volumes), sum(v.volume for v in s.volumes)
        rel = abs(va - vb) / max(va, vb)
        if rel > PAIR_REL:
            out.append(Finding(WARN, "pairs", o.name, f"volume {va:.0f} vs {m} {vb:.0f} mm3 "
                                                      f"({100 * rel:.1f} % apart)", 100 * rel))
    return out


CHECKS = {"solid": solid, "plate": plate, "pairs": pairs}
