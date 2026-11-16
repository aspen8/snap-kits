"""
Test coupons for the Vulcan's joints, cut from the real kit parts (same fits and print poses), in
one colour. Print these before the full kit and adjust the fits from what you find (FIT, KEY_FIT,
GEAR_PLUG_FIT, FIN_FIT in vulcan.py).

Run from the repository root:
  .venv/bin/python vulcan/cad/test_coupons.py OUT_DIR      (writes OUT_DIR/vulcan_test_coupons.3mf, stl/)

  c1 shell key       a block of the centre upper and lower shells round one 6 x 10 key, and the key
  c2 wing joint      the centre body / outer wing joint round its 22 mm key (four shell pieces), and the key
  c3 radome          the radome, the probe, and the front shells' nose with the tongue
  c4 fin             the fin halves' root (x 300-350) and the centre upper shell's slot there
  c5 nose gear       both nose leg halves, the gear-down door frame, and the centre shells round the socket
  c6 main gear       both starboard main leg halves, its door frame, and the wing shells round the socket
  c7 engine face     the starboard inner engine face and the centre shells round its slot
  c8 stand           the top of the stand post, the stand's bomb door panel and the bay roof round the key
  c9 Blue Steel      the missile's front key, and the Blue Steel door round it
"""
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_argv = sys.argv
sys.argv = [_argv[0], str(Path(_argv[1] if len(_argv) > 1 else "out/vulcan/coupons") / "geo")]
import kitlib as K            # noqa: E402
import vulcan as V            # noqa: E402
sys.argv = _argv
from kitlib import mesh_of    # noqa: E402

B = V.BIG
WHITE = 1
FILAMENTS = {WHITE: ("White", "#F2F2F0")}
BED = (200.0, 240.0)
BED_MARGIN = (22.0, 6.0)
GAP = 5.0


def box(x0, x1, y0, y1, z0=-B, z1=B):
    return K.box(x0, x1, y0, y1, z0, z1)


def coupons():
    """[(coupon name, kit part name, crop region or None)]"""
    k = V.KEY_AT
    return [
        ("c1_centre_upper", "centre_upper", box(160, 184, 4, 24)),
        ("c1_centre_lower", "centre_lower", box(160, 184, 4, 24)),
        ("c1_key", k[(172.0, 14.0)], None),
        ("c2_centre_upper", "centre_upper", box(186, 214, 48, 59.5)),
        ("c2_centre_lower", "centre_lower", box(186, 214, 48, 59.5)),
        ("c2_wing_upper", "wing_stbd_upper", box(186, 214, 58.5, 70)),
        ("c2_wing_lower", "wing_stbd_lower", box(186, 214, 58.5, 70)),
        ("c2_key", k[(199.5, 59.0)], None),
        ("c3_radome", "radome", None),
        ("c3_probe", "probe", None),
        ("c3_front_upper", "front_upper", box(-B, 40, -B, B)),
        ("c3_front_lower", "front_lower", box(-B, 40, -B, B)),
        ("c4_fin_stbd", "fin_stbd", box(300, 350, -B, B, -B, 32)),
        ("c4_fin_port", "fin_port", box(300, 350, -B, B, -B, 32)),
        ("c4_centre_upper", "centre_upper", box(295, 355, -12, 12)),
        ("c5_leg_a", "nose_gear_a", None),
        ("c5_leg_b", "nose_gear_b", None),
        ("c5_door_frame", "doors_open_nose", None),
        ("c5_centre_upper", "centre_upper", box(112, 136, -12, 12)),
        ("c5_centre_lower", "centre_lower", box(112, 136, -12, 12)),
        ("c6_leg_a", "main_gear_stbd_a", None),
        ("c6_leg_b", "main_gear_stbd_b", None),
        ("c6_door_frame", "doors_open_main_stbd", None),
        ("c6_wing_upper", "wing_stbd_upper", box(234, 262, 59.5, 80)),
        ("c6_wing_lower", "wing_stbd_lower", box(234, 262, 59.5, 80)),
        ("c7_face", "engine_face_stbd_inner", None),
        ("c7_centre_upper", "centre_upper", box(183, 201, 21, 40)),
        ("c7_centre_lower", "centre_lower", box(183, 201, 21, 40)),
        ("c8_post_top", "stand_post", box(-B, B, -B, B, -32, B)),
        ("c8_door", "door_bomb_stand", box(226, 254, -B, B)),
        ("c8_bay_roof", "bomb_bay_roof", box(226, 254, -B, B)),
        ("c9_missile", "blue_steel", box(203, 227, -B, B)),
        ("c9_door", "door_bluesteel", box(203, 227, -B, B)),
    ]


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out/vulcan/coupons")
    (out / "stl").mkdir(parents=True, exist_ok=True)
    parts = V.build()
    objs = {}
    for cname, pname, region in coupons():
        P, pose = parts[pname]
        if region is not None:
            P = P ^ region
        pieces = sorted(P.decompose(), key=lambda q: -q.volume())
        if len(pieces) > 1 and pieces[1].volume() > 1.0:
            print(f"!! {cname}: {len(pieces)} pieces, the second {pieces[1].volume():.1f} mm3 (dropped)")
        P = pieces[0]
        m = pose(P).scale([V.PRINT_K] * 3)
        lo = np.asarray(m.bounding_box()[:3])
        m = m.translate(list(-lo))
        size = np.asarray(m.bounding_box()[3:])
        trimesh.Trimesh(*mesh_of(m)).export(out / "stl" / f"{cname}.stl")
        objs[cname] = (m, size)
        print(f"{cname:18s} from {pname:24s} {size[0]:5.1f} x {size[1]:5.1f} x {size[2]:5.1f} mm")
    items = sorted(((n, (s[0], s[1])) for n, (m, s) in objs.items()), key=lambda it: -it[1][0] * it[1][1])
    plates = K.pack(items, BED, GAP)
    objects = []
    for pi, its in enumerate(plates):
        for n, x, y, rot90 in its:
            m, s = objs[n]
            if rot90:
                m = m.rotate([0, 0, 90]).translate([s[1], 0, 0])
            objects.append({"name": n, "placement": (pi, x + BED_MARGIN[0], y + BED_MARGIN[1]),
                            "volumes": [(WHITE, *mesh_of(m))]})
        print(f"plate {pi + 1}: " + ", ".join(n for n, *_ in its))
    K.write_3mf(out / "vulcan_test_coupons.3mf", objects, [f"Test coupons {i + 1}" for i in range(len(plates))],
                None, FILAMENTS, "Avro Vulcan B.2 snap kit 1:96 - test coupons")
    print("wrote", out / "vulcan_test_coupons.3mf")
