"""
Joint test 2 (2026-11-16): the joints changed after print 1, cut from the built kit parts (as each
part stands on the plate) so every slot, rail and boss prints as in the kit.

Run after the colour build:  python joint_test2.py KIT_OUT_DIR [project_settings_template.json]

Plate 1 (the kit's wing-plate settings):
  wing_inner_stbd bottom 34 mm      the inner nacelle's top and the rail slot under the wing
  fuselage_rear bottom 24 mm        the dorsal turret hole and its snap boss (x 184-208)
  fuselage_tail top 22 mm           the tail turret's snap boss (x 340-362)
  tailplane_stbd / _port bottom 12 mm   the root faces and the bow-tie pocket across the centre join
Plate 2 (the kit's own settings for each):
  nacelle1_stbd_inboard / _outboard (whole), key_nacelle_nose x2 (one spare),
  turret_dorsal, turret_tail, key_tailplane x2 (one spare)
Everything in black. Writes KIT_OUT_DIR/halifax_joint_test2.3mf.

What to check: the nacelle halves close round the rail by hand and slide aft onto the wing slab to
the leading edge, and stay closed; the nose key goes in and is trapped; both turrets snap on with a
firm push and turn; the tailplane halves hold together on their key.
"""
import sys
from pathlib import Path

import manifold3d as mf
import numpy as np
import trimesh

import colour as C
import kitlib as K

SLICES = [  # (test name, kit part, from top?, thickness)
    ("t_wing_nacelle", "wing_inner_stbd", False, 34.0),
    ("t_dorsal_boss", "fuselage_rear", False, 24.0),
    ("t_tail_boss", "fuselage_tail", True, 22.0),
    ("t_tailplane_stbd", "tailplane_stbd", False, 12.0),
    ("t_tailplane_port", "tailplane_port", False, 12.0),
]
WHOLE = [  # (test name, kit part)
    ("nacelle1_stbd_inboard", "nacelle1_stbd_inboard"),
    ("nacelle1_stbd_outboard", "nacelle1_stbd_outboard"),
    ("key_nacelle_nose_1", "key_nacelle_nose_1"),
    ("key_nacelle_nose_spare", "key_nacelle_nose_2"),
    ("turret_dorsal", "turret_dorsal"),
    ("turret_tail", "turret_tail"),
    ("key_tailplane_1", "key_tailplane_1"),
    ("key_tailplane_spare", "key_tailplane_1"),
]


def load(path):
    t = trimesh.load(path)
    return mf.Manifold(mf.Mesh(t.vertices.astype(np.float32), t.faces.astype(np.uint32)))


def main():
    out = Path(sys.argv[1])
    template = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).with_name("project_settings_template.json"))
    stl = out / "stl"
    pieces = {}
    for name, part, top, t in SLICES:
        P = load(stl / f"{part}.stl")
        x0, y0, z0, x1, y1, z1 = P.bounding_box()
        a, b = (z1 - t, z1) if top else (z0, z0 + t)
        S, dropped = K.largest_piece(P ^ K.box(x0 - 1, x1 + 1, y0 - 1, y1 + 1, a, b))
        if dropped:
            print(f"  {name}: dropped loose bits {[round(v, 2) for v in dropped]}")
        pieces[name] = (S, part)
    for name, part in WHOLE:
        pieces[name] = (load(stl / f"{part}.stl"), part)
    groups = [("Joint slices", [n for n, *_ in SLICES]), ("Nacelle, turrets and keys", [n for n, _ in WHOLE])]
    objects, names = [], []
    for pi, (gname, group) in enumerate(groups):
        items = []
        for n in group:
            S = pieces[n][0]
            x0, y0, z0, *_ = S.bounding_box()
            S = S.translate([-x0, -y0, -z0])
            pieces[n] = (S, pieces[n][1])
            bb = S.bounding_box()
            items.append((n, (bb[3], bb[4])))
        packed = K.pack(sorted(items, key=lambda it: -it[1][0] * it[1][1]), C.BED, 12.0)
        assert len(packed) == 1, gname
        names.append(gname)
        for n, x, y, rot in packed[0]:
            S, kit = pieces[n]
            if rot:
                w = S.bounding_box()[4]
                S = S.rotate([0, 0, 90]).translate([w, 0, 0])
            st = C.object_settings(kit)
            if n.startswith("t_"):                  # a short slice needs no tall brim
                st = {k: v for k, v in st.items() if k not in ("brim_type", "brim_width")}
            objects.append({"name": n, "placement": (pi, x + C.BED_X0, y + C.BED_Y0), "settings": st,
                            "volumes": [(C.BLACK, *K.mesh_of(S))]})
            print(f"plate {pi + 1}: {n:24} from {kit:24} {st}")
    path = out / "halifax_joint_test2.3mf"
    K.write_3mf(path, objects, names, template, C.FILAMENTS, "Halifax joint test 2", C.PRINT_OVERRIDES)
    print("wrote", path)


if __name__ == "__main__":
    main()
