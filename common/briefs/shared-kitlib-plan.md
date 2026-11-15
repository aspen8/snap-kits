# Plan: a shared kitlib

Written 2026-11-15 in answer to `common/briefs/fable-kit-lint-and-shared-kitlib.md`. A plan only: nothing here is done.

## Summary

- Put the shared code in a new package, `common/snapkit/`. It can't be called `kitlib`: each kit's own `cad/kitlib.py` comes first on the import path and would hide it.
- Each kit's `cad/kitlib.py` becomes a short shim: `from snapkit import *` plus that kit's defaults. Every existing `import kitlib as K` keeps working, so the kits switch one file at a time.
- The Halifax switches first. The Hawk's switch is one file (`hawk/cad/kitlib.py`), prepared ready for its owner, who takes it when it suits. Until then nothing under `hawk/` changes.
- The proof at each step is `kitlint`'s signature comparison (`kit-lint-design.md`, check 1). So lint step 1 is built before this migration starts.
- No shared build loop yet. Share the last third of it (plates, placement, 3MF, preview) as functions; leave each kit's part loop alone.

## What the two files really differ in

The brief lists 10 functions with the same name and a different body. Comparing the syntax trees, **three of those are identical**: `key_slots`, `paint` and `pose_matrix`. Seven differ:

| Function | Called by the Halifax | Called by the Hawk | Real merge needed |
|---|---|---|---|
| `connector_key` | yes | no (it uses `spring_key`) | no |
| `make_inlay` | yes | no (markings are painted since v2) | no |
| `make_section_inlay` | yes | no | no |
| `surface_extreme` | no | no | no |
| `pack` | yes | yes | yes |
| `project_settings` | through `write_3mf` | through `write_3mf` | yes |
| `write_3mf` | yes | yes | yes |

So four of the seven have one user, and only the plate and 3MF functions need merging. The other 21 shared functions are identical text.

Also found:
- The two Bambu settings templates have the same 581 keys but differ in content: the Hawk's has slower second-nozzle speeds (outer wall 30 against 50, inner wall 80 against 200, top surface 80 against 200). They must stay separate.
- `git status` shows both `halifax/kit/halifax_kit.3mf` and `hawk/kit/hawk_kit.3mf` modified and uncommitted in this checkout. Settle that before taking any baseline (see step 0).
- `.claude/skills/snap-kit/SKILL.md` still says the Halifax is in the root `cad/` and that a new kit "appends the repo's `cad/` to `sys.path` for `kitlib`". LESSONS says "Python 3.10-3.12 only"; `HANDOFF.md` and the brief say 3.13 works. Both need a line once this lands.

## Layout

```
common/snapkit/
  __init__.py     re-exports everything below, so `from snapkit import *` gives the old kitlib names
  sections.py     cs prism_z prism_y raster_section text_section disc clip band ring rect_outline dots_along
  solids.py       box slab inner_core outer_skin cyl_axis to_manifold mesh_of largest_piece halfspace
                  + leaf, dilate (from halifax/cad/colour.py)
  colour.py       paint  + Outside (from halifax/cad/colour.py, step 3)
  inlay.py        surface_hits surface_extreme under_band floor_plane make_inlay make_section_inlay
                  peg_on_floor  INLAY_FACING INLAY_FLOOR
  joints.py       key_slots connector_key spring_key pose_matrix
  plate.py        pack pack_best place_towers  TOWER TOWER_DEPTH TOWER_CLEAR TOWER_X_MIN
                  + layout_plates (step 3)
  bambu.py        project_settings safe_name write_3mf
```

A single 800-line `common/snapkit.py` would also do. I prefer the package for one reason: `joints.py` is the only module that needs CadQuery, and it should import it inside its functions. Then `kitlint` and the tools can import `snapkit` without loading CadQuery (several seconds, and absent in a cloud session).

Each kit finds it with two lines at the top of its shim: `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "common"))`.

## What is shared and what stays per kit

**Shared:** everything in the layout above.

**From `halifax/cad/colour.py` into `snapkit`, because it is generic:**

| Now | Becomes | Notes |
|---|---|---|
| `leaf`, `dilate`, `_overlaps` | `snapkit.solids` | Unchanged. |
| `pack` wrapper (try both ways round, keep fewer plates) | `snapkit.plate.pack_best(items, bed, gap)` | Unchanged. |
| `Outside` | `snapkit.colour.Outside(solids, skin, inner, gap_close, base)` | Takes a list of `(name, solid)` already filtered, and the three depths, in place of the module constants `SKIN`, `INNER_BLACK`, `GAP_CLOSE` and the `key_` test. `wing_shadow` and the nacelle rule are the Halifax's and stay in a small subclass in `halifax/cad/colour.py`. |
| `add_object`, the plate loop in `__main__`, the preview GLB | `snapkit.plate.layout_plates(objs, groups, bed, origin, gap, max_colours)` returning plates and the `objects` list; `snapkit.bambu.write_preview(path, preview, filaments)` | The two kits' loops are nearly the same text. The Hawk's `add_object` also stores `height`; keep that. |
| peak-memory print | `snapkit.solids.peak_gb()` | Handles macOS bytes and Linux kilobytes. Also used by the lint's memory guard. |
| `thickest_point` | `snapkit.inlay` | Generic (where a peg fits in a letter). |

**Stays per kit:**
- The Bambu settings template and its overrides (`PRINT_OVERRIDES`, `object_settings`, `TALL_BRIM`).
- `FILAMENTS`, the nozzle maps, `PLATE_GROUPS`, `BED`, `BED_X0` / `BED_MARGIN`.
- Every fit constant and joint design. `connector_key` (the Halifax's flexing key, CadQuery) and `spring_key` (the Hawk's split key, manifold) do the same job, were tested on different kits at different fits, and both stay. Don't unify them.
- `colour_part`, patterns, markings, frames, the stand, `detail.py`.
- The mesher (`halifax.mesh` at 0.05 rad with its fallback; `hawk.to_m` at 0.12). A shared `tessellate` could come with the lint's mesh guard, later.
- The Hawk's `PRINT_K` scaling and `DEFAULT_TEMPLATE`, which is found from `__file__` and so must live in `hawk/cad/`.

**No shared build loop.** The part loops differ for real reasons: the Halifax goes CadQuery, mesh, detail, inlays, `leaf`, `Outside`, paint; the Hawk has manifold parts, builds each wing from a detailed whole, scales by `PRINT_K`, and `ONLY` filters at a different point. Sharing `layout_plates`, `write_3mf` and the lint call gives most of the benefit at little risk. Look again after a third kit.

## The seven diverging functions

### `pack(items, bed, gap=8.0, across=False)`: merge with a switch

The only difference is one line. The Hawk also turns a part when `h > w and h <= bed[0]` ("lie long parts across the shelf").

- `across=False`: the Halifax's rule. `across=True`: the Hawk's.
- Halifax: no change. It keeps calling through `pack_best`.
- Hawk: its shim sets `pack = functools.partial(snapkit.pack, across=True)`. No change.
- Neither kit takes the other's rule: either would move parts on plates.

### `project_settings(template, filaments, *, overrides=None, towers=None, nozzle_map=None)`: the Halifax's body, one addition

| Point | Halifax today | Hawk today | Shared |
|---|---|---|---|
| Print overrides | `d.update(overrides)` | none | as the Halifax; the Hawk passes none |
| Tower positions | from `towers` (a list from `place_towers`), else the template's | `WIPE_TOWER` (200, 12) repeated for `n_plates` | from `towers`. The Hawk's shim passes `[WIPE_TOWER] * n_plates` |
| Number format | `"22.0"` | `"200"` | `"%.1f"`. The Hawk's file changes from `"200"` to `"200.0"`: same number, different text |
| `filament_map` | from `nozzle_map`, default 1 | all 1, or from the map | the same list either way |
| `filament_map_mode` | always set: Manual with a map, else "Auto For Flush" | set to Manual with a map, else left as the template has it | as the Halifax. The Hawk's template already says "Auto For Flush", so no change |

`n_plates` disappears as a parameter (it is `len(towers)`).

### `write_3mf(path, objects, plates, template, filaments, title, *, overrides=None, nozzle_map=None, towers="auto")`: the Halifax's body, three additions

| Point | Halifax today | Hawk today | Shared |
|---|---|---|---|
| 7th positional argument | `overrides` | `filament_map` | **keyword only after `title`**: the two kits pass different things in that position, and a mix-up would be silent |
| Nozzle map | one dict for all plates | a dict, or a list with one dict or `None` per plate | `nozzle_map` takes either. The project-level map is the first plate's, as the Hawk does; for a single dict that is the same thing |
| Towers | `place_towers` when there is a template | fixed | `towers="auto"` calls `place_towers`; a list is used as given |
| No template | writes no project settings (the file opens as bare geometry: the Hawk lesson) | uses `DEFAULT_TEMPLATE` | `template` is required; `None` raises. Each kit supplies its own default |
| Plate names | `safe_name` | as given | `safe_name`. The Hawk's names have none of the refused characters, so no change |
| Per-object `settings` | written | none | written when present. Objects without it produce the same XML as now |

What changes for each kit:
- **Halifax:** four call sites move `C.PRINT_OVERRIDES` to `overrides=`: `colour.write_3mf`, `joint_test.py:81`, `tail_test.py:73`, `test_plate.py:279`. `colour.py`'s template argument defaults to `project_settings_template.json` beside it when not given on the command line (today that silently writes a file with no settings). Output: unchanged.
- **Hawk:** nothing in `colour.py` or `test_coupons.py`. The shim keeps the old signature:

```python
# hawk/cad/kitlib.py after the switch (the whole file, apart from the sys.path lines)
from snapkit import *                      # noqa: F401,F403
import functools, snapkit
DEFAULT_TEMPLATE = Path(__file__).with_name("bambu_x2d_project_settings.json")
WIPE_TOWER = (200.0, 12.0)
pack = functools.partial(snapkit.pack, across=True)
connector_key = functools.partial(snapkit.connector_key, flex=False)

def write_3mf(path, objects, plates, template, filaments, title, filament_map=None):
    snapkit.write_3mf(path, objects, plates, template or DEFAULT_TEMPLATE, filaments, title,
                      nozzle_map=filament_map, towers=[WIPE_TOWER] * len(plates))
```

  Output: the same objects, plates, positions and maps. The tower numbers read `200.0` and `12.0`. Object UUIDs are random on every run already.

### `connector_key`: the Halifax's wins

The Halifax's has the flexing design behind `flex=True`; with `flex=False` it is the Hawk's body exactly. The Hawk never calls it. Its shim pins `flex=False` anyway, so a future call behaves as before.

### `make_inlay`, `make_section_inlay`: the Halifax's win

The Halifax versions have the tilted floor, the underside guard, pegs, back labels and the key cavity, and return one or two more values (the print rotation, and the floor for `add_peg`). The Hawk has no callers. If the Hawk goes back to inlays it should use these: they fix the "socket far too deep on a curved skin" lesson. The old bodies stay in git history (`hawk/cad/kitlib.py` before the switch).

### `surface_extreme`: the Halifax's wins

Nobody calls it in either kit (the Halifax's `make_inlay` uses `surface_hits` and `floor_plane` now). Keep the Halifax's, which goes through `surface_hits` and so ignores surface that turns away (`facing=0.6`). It could be deleted; keeping it costs four lines.

## Migration, step by step

Both kits build at every step. Each step is one commit on a short branch.

**Step 0. Baselines (no code change).**
- Settle the two modified 3MFs (`git status`): commit or restore them, so "the committed kit" means one thing.
- On an untouched `main`, build each kit on this Mac and write its signature with `kitlint --write-sig` into the build folder (Halifax 20 min, Hawk 8 min). **Compare against these, not against the committed 3MF**: `HANDOFF.md` says the Mac's OCC meshes differ slightly from the cloud's.
- Build the Halifax a second time, unchanged, and compare the two signatures. The largest difference is the build's own noise, and sets the tolerance (see "Proof"). If two builds match exactly, the tolerance can be near zero. This is the one extra 20-minute build I think is worth it; skip it and the tolerance is a guess.
- Needs: lint step 1 (loader, signature, `diff`).

**Step 1. Create `common/snapkit/` (nothing imports it yet).**
- Copy `halifax/cad/kitlib.py` into the modules above. Add `spring_key` from the Hawk. Apply the three merges. CadQuery imports go inside `key_slots`, `connector_key` and `pose_matrix`.
- Add `common/snapkit/parity.py`, which loads both old kitlibs by path (`importlib`) and compares old against new on fixed inputs. It runs in seconds and needs no kit build:
  - the 24 identical functions: same output on a small solid or section;
  - `pack`: the same placements on a saved list of sizes, for each kit's rule (take the lists from each kit's last build log, or 30 random sizes with a fixed seed);
  - `project_settings`: equal JSON for each kit's template, filaments and maps, treating number strings as numbers;
  - `write_3mf`: a two-object, two-plate toy written by old and new; compare every zip entry with UUIDs blanked.
- Kits: untouched. Risk: none.

**Step 2. Switch the Halifax.**
- `halifax/cad/kitlib.py` becomes its shim (`from snapkit import *`; nothing else is needed).
- Update the four `write_3mf` call sites.
- Proof: full build, `kitlint diff` against the step 0 baseline. Then `joint_test.py` and `tail_test.py` (seconds each), and `test_plate.py` (3 min) with a `diff` of its 3MF against one made before the step.
- Hawk: untouched.

**Step 3. Move the generic parts of `halifax/cad/colour.py`.**
- 3a: `leaf`, `dilate`, `pack_best`, `peak_gb`, `thickest_point`. Plain moves; can ride with step 2's build.
- 3b: `Outside`, `layout_plates`, `write_preview`. These are rewrites with parameters, so they get their own build and `diff`. `joint_test.py`, `tail_test.py` and `test_plate.py` import from `colour` (`C.BED`, `C.FILAMENTS`, and `test_plate` more): check each still runs.
- Hawk: untouched.

**Step 4. Switch the Hawk. The Hawk's owner does this.**
- Prepared for them on a branch: the shim above as the new `hawk/cad/kitlib.py`. That is the whole change. `hawk.py`, `colour.py`, `detail.py` and `test_coupons.py` are not edited.
- The owner builds (8 min), runs `kitlint diff` against the Hawk's step 0 baseline, and slices. Expected differences: none in objects; tower numbers `200` to `200.0`.
- Undo: restore one file.
- Until this step is taken, the Hawk keeps its 503-line kitlib and is unaffected by anything above.

**Step 5. Optional for the Hawk, one at a time, each a real change the owner chooses:**
- `towers="auto"` in place of the fixed (200, 12): towers move; the packer's `x > 190` reserve could then go. Slice to confirm.
- A sidecar for `kitlint` (25 lines in `colour.py`): turns on the clash and paint checks.
- `layout_plates` in place of its own plate loop.
- Per-object settings, if it wants brims or layer heights per part.

**Step 6. Tidy up.**
- `SKILL.md`: a new kit copies `hawk/` and gets the shim; say where `snapkit` is. LESSONS: the Python version line. Both `HANDOFF.md` files: the new layout.
- The shims can stay for good. They are where a kit's defaults live.

## Proof that nothing changed

`kitlint diff BASELINE.sig.json NEW.3mf` must report:

| Compared | Must be |
|---|---|
| Object names and count | identical |
| Plate of each object, plate names and order | identical |
| Position on the plate | within 0.01 mm |
| Size of each object | within 0.05 mm |
| Volume of each colour in each object | within the noise measured in step 0 (my starting guess: 0.5 mm3 or 0.02 %, whichever is larger) |
| Per-object settings, project overrides | identical |
| Nozzle map and mode, per plate and project | identical |
| Tower positions | identical as numbers |
| Filament names and colours | identical |

Then slice the new 3MF (`kitlint --slice`, 1 minute): the same plates slice, with time and colour changes within 1 % and the same warnings. Slicing proves the settings half, which the signature only samples.

Bytes can't be compared: the UUIDs are random and the mesher is not exactly repeatable.

## Risks

| Risk | Guard |
|---|---|
| Name clash: a kit's `kitlib.py` hides anything else called `kitlib`. | The shared package has a different name. |
| `from snapkit import *` doesn't pass on names starting with `_`, and copies constants by value. Code that sets `K.INLAY_FLOOR = ...` would change the shim's copy only. | No kit does this today (constants are only read). Say so in the shim's docstring; add an `__all__` so the exported set is explicit. |
| Import order. `hawk.py` appends its own folder to `sys.path`; the shim inserts `common/` at the front. A stray `common/kitlib.py` in future would break both. | Never add a module named `kitlib` to `common/`. |
| Two sessions change `common/snapkit` at once. After step 4 a change for one kit can alter the other. | Rule for `snapkit`: a change is either additive (a new function, or a new keyword whose default keeps the old behaviour), or it comes with a clean `kitlint diff` for **both** kits (28 minutes of builds). Write that rule at the top of `common/snapkit/__init__.py`. |
| Units. The Hawk models at 1:40 and scales by 1.25 on output; the Halifax models at print size. `INLAY_FLOOR`, `INLAY_FACING` and `Outside`'s depths are model lengths. | The Hawk doesn't use the inlay code. `Outside` takes its depths as arguments, so the Hawk would pass printed size divided by `PRINT_K`. Tower and packing numbers are plate millimetres for both. |
| The positional 7th argument of `write_3mf` meant different things. | Keyword only in `snapkit`; the Hawk's shim keeps its old positional form. |
| `template=None` used to be allowed for the Halifax. | It now raises, on purpose. The Halifax scripts get a default path. |
| The Halifax test scripts aren't covered by the kit build. | Run all three in step 2 and step 3b. |
| A 20-minute build per step. | Steps 2 and 3a share one. `parity.py` catches most mistakes in seconds first. |

## Not to share

- The two settings templates (different second-nozzle speeds, and each is the user's saved profile).
- Fits, joint designs and their constants: tested per kit, per orientation, per layer height.
- `PLATE_GROUPS`, colour limits per plate, nozzle maps: these are print-time decisions per kit.
- Paint rules (`colour_part`) and anything that names a part.
- The meshers, for now.

## Decisions I'd like from the user

1. **The name.** `snapkit` is my suggestion; it only has to be anything but `kitlib`.
2. **When the Hawk switches** (step 4), and who tells its owner. Nothing forces a date: the Halifax gets the full benefit after step 3.
3. **The extra 20-minute Halifax build in step 0** to measure build-to-build noise. I recommend it.
4. **The two modified, uncommitted 3MFs** in this checkout: commit or discard before step 0?
