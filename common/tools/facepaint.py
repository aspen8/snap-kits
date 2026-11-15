"""Paint on each object's bottom (bed) and top faces: area of non-black triangles lying flat there."""
import zipfile, re, sys, numpy as np
def objects(path):
    z = zipfile.ZipFile(path)
    main = z.read('3D/3dmodel.model').decode(); cfg = z.read('Metadata/model_settings.config').decode()
    names = dict(re.findall(r'<object id="(\d+)">\s*<metadata key="name" value="([^"]+)"', cfg))
    ext = {}
    for oid, body in re.findall(r'<object id="(\d+)">(.*?)</object>', cfg, re.S):
        ext[oid] = dict(re.findall(r'<part id="(\d+)" subtype="normal_part">.*?key="extruder" value="(\d+)"', body, re.S))
    comps = re.findall(r'<object id="(\d+)"[^>]*>\s*<components>(.*?)</components>', main, re.S)
    for oid, c in comps:
        vols = []
        for path_, cid in re.findall(r'<component p:path="([^"]+)" objectid="(\d+)"', c):
            sub = z.read(path_.lstrip('/')).decode()
            obj = re.search(r'<object id="%s".*?</object>' % cid, sub, re.S).group(0)
            V = np.array(re.findall(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"', obj), float)
            F = np.array(re.findall(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', obj), int)
            vols.append((ext[oid].get(cid, '1'), V, F))
        yield names.get(oid), vols
pat = sys.argv[2] if len(sys.argv) > 2 else ''
for name, vols in objects(sys.argv[1]):
    if not re.match(pat, name or ''): continue
    zmax = max(V[:, 2].max() for _, V, _ in vols)
    res = {}
    for e, V, F in vols:
        if e == '1': continue
        T = V[F]; zs = T[:, :, 2]
        a = 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
        bot = a[(zs.max(1) < 0.02)].sum(); top = a[(zs.min(1) > zmax - 0.02)].sum()
        res[e] = (round(bot, 1), round(top, 1))
    print(f"{name:26s}", res)
