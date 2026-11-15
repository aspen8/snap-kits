"""Read a Bambu Studio project 3MF (ours or one Bambu Studio re-saved) into plain arrays.

Every object's colour volumes come back in plate coordinates (the plate's lower-left corner at 0, 0),
so they are what the printer sees. No CadQuery here: this must run anywhere the kit 3MF is.
"""
import json
import math
import re
import zipfile
from dataclasses import dataclass, field

import numpy as np

BED_STEP = 1.2          # Bambu lays plates out on a grid, 1.2 bed widths apart


@dataclass
class Volume:
    slot: int           # filament slot, 1-based
    colour: str         # filament name from the part name ("Dark Green"), or "slot N"
    V: np.ndarray       # (n, 3) float64, plate coordinates
    F: np.ndarray       # (m, 3) int64

    @property
    def volume(self):
        T = self.V[self.F]
        return float(np.einsum("ij,ij->i", T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() / 6.0)


@dataclass
class Obj:
    oid: str
    name: str
    plate: int          # 1-based
    settings: dict      # per-object metadata (layer_height, brim_type, ...)
    volumes: list = field(default_factory=list)

    def bounds(self):
        V = np.vstack([v.V for v in self.volumes])
        return V.min(0), V.max(0)

    def xy(self, n=4000):
        V = np.vstack([v.V[:, :2] for v in self.volumes])
        return V[:: max(1, len(V) // n)]


@dataclass
class Plate:
    index: int          # 1-based
    name: str
    nozzle: dict        # slot -> nozzle (1 main, 2 auxiliary)
    mode: str           # "Manual" or "Auto For Flush"
    tower: tuple        # (x, y) lower-left corner of the prime tower, or None
    objects: list = field(default_factory=list)


@dataclass
class Kit:
    path: str
    objects: list
    plates: list
    settings: dict      # project settings JSON
    filaments: list     # [(name, hex)] by slot - 1


def _mat(s):
    """3MF transform "m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32" (row vectors) as a 4 x 3."""
    if not s:
        return None
    return np.array(s.split(), float).reshape(4, 3)


def _apply(V, M):
    return V if M is None else V @ M[:3] + M[3]


_VERT = re.compile(rb'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"')
_TRI = re.compile(rb'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"')
_OBJ = re.compile(rb'<object id="(\d+)"[^>]*>(.*?)</object>', re.S)


def _meshes(z, path, cache):
    if path not in cache:
        data = z.read(path.lstrip("/"))
        out = {}
        for oid, body in _OBJ.findall(data):
            V = np.array(_VERT.findall(body), dtype="S24").astype(float)
            F = np.array(_TRI.findall(body), dtype="S12").astype(np.int64)
            out[oid.decode()] = (V.reshape(-1, 3), F.reshape(-1, 3))
        cache.clear()                   # one sub-model file at a time: they reach 130 MB
        cache[path] = out
    return cache[path]


def _meta(body):
    return dict(re.findall(r'<metadata key="([^"]+)" value="([^"]*)"', body))


def load(path, meshes=True):
    """The kit at `path`. meshes=False skips the geometry (names, plates and settings only)."""
    z = zipfile.ZipFile(path)
    main = z.read("3D/3dmodel.model").decode()
    cfg = z.read("Metadata/model_settings.config").decode()
    try:
        settings = json.loads(z.read("Metadata/project_settings.config"))
    except KeyError:
        settings = {}
    names = settings.get("filament_colour", [])
    filaments = list(zip(settings.get("filament_settings_id", [""] * len(names)), names))

    # objects in model_settings.config: name, settings, part extruders in order
    info = {}
    for oid, body in re.findall(r'<object id="(\d+)">(.*?)</object>', cfg, re.S):
        head = body.split("<part", 1)[0]
        meta = _meta(head)
        parts = []
        for pid, pbody in re.findall(r'<part id="(\d+)"[^>]*>(.*?)</part>', body, re.S):
            pm = _meta(pbody)
            parts.append((pid, pm.get("name", ""), pm.get("extruder")))
        info[oid] = (meta, parts)

    # plates
    plate_xml = re.findall(r"<plate>(.*?)</plate>", cfg, re.S)
    n_plates = max(1, len(plate_xml))
    cols = max(1, math.ceil(math.sqrt(n_plates)))
    step = 256.0 * BED_STEP
    if "printable_area" in settings:
        xs = [float(p.split("x")[0]) for p in settings["printable_area"]]
        step = (max(xs) - min(xs)) * BED_STEP
    tx, ty = settings.get("wipe_tower_x", []), settings.get("wipe_tower_y", [])
    global_map = settings.get("filament_map")
    plates, plate_of = [], {}
    for i, body in enumerate(plate_xml):
        head = body.split("<model_instance", 1)[0]
        m = _meta(head)
        idx = int(m.get("plater_id", i + 1))
        fm = m.get("filament_maps")
        fm = fm.split() if fm else (global_map or [])
        nozzle = {k + 1: int(v) for k, v in enumerate(fm)}
        tower = (float(tx[idx - 1]), float(ty[idx - 1])) if idx - 1 < min(len(tx), len(ty)) else None
        plates.append(Plate(idx, m.get("plater_name", ""), nozzle,
                            m.get("filament_map_mode", settings.get("filament_map_mode", "")), tower))
        for oid in re.findall(r'<metadata key="object_id" value="(\d+)"', body):
            plate_of[oid] = idx

    # build items: object -> transform (world)
    items = {oid: _mat(t) for oid, t in
             re.findall(r'<item objectid="(\d+)"[^>]*?transform="([^"]+)"', main)}
    comps = dict(re.findall(r'<object id="(\d+)"[^>]*>\s*<components>(.*?)</components>', main, re.S))

    objects, cache = [], {}
    for oid, (meta, parts) in info.items():
        name = meta.pop("name", oid)
        obj_ext = meta.pop("extruder", "1")
        meta.pop("face_count", None)
        pl = plate_of.get(oid, 0)
        o = Obj(oid, name, pl, meta)
        objects.append(o)
        if not meshes:
            o.parts = [(p[1], int(p[2] or obj_ext)) for p in parts]
            continue
        pi = pl - 1 if pl else 0
        offset = np.array([(pi % cols) * step, -(pi // cols) * step, 0.0])
        world = items.get(oid)
        clist = re.findall(r'<component p:path="([^"]+)" objectid="(\d+)"(?:[^>]*?transform="([^"]+)")?', comps.get(oid, ""))
        by_id = {p[0]: p for p in parts}
        for k, (cpath, cid, ct) in enumerate(clist):
            V, F = _meshes(z, cpath, cache)[cid]
            V = _apply(_apply(V, _mat(ct)), world) - offset
            pid, pname, ext = by_id.get(cid) or (parts[k] if k < len(parts) else (cid, "", None))
            slot = int(ext or obj_ext)
            colour = pname[len(name) + 1:].replace("_", " ") if pname.startswith(name + "_") else f"slot {slot}"
            o.volumes.append(Volume(slot, colour, V, F))
    # A volume's colour is its slot's filament. Part names say which colour the build meant, and
    # a re-save keeps the name when someone moves a volume to another slot, so take each slot's
    # name by majority over the kit.
    votes = {}
    for o in objects:
        for v in o.volumes:
            votes.setdefault(v.slot, {}).setdefault(v.colour, 0)
            votes[v.slot][v.colour] += 1
    slot_name = {s: max(c, key=c.get) for s, c in votes.items()}
    for o in objects:
        for v in o.volumes:
            v.meant = v.colour
            v.colour = slot_name[v.slot]
    for p in plates:
        p.objects = [o for o in objects if o.plate == p.index]
    z.close()
    return Kit(path, objects, sorted(plates, key=lambda p: p.index), settings, filaments)
