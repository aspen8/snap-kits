# Brief: a kit check suite ("kit lint") and a shared kitlib

Written 2026-11-15 for a design session. **Output is two design documents, not code changes.** A later session implements them.

## Context in one paragraph

This repo (`aspen8/snap-kits`) builds fully printed, multi-colour, snap-together scale model kits for a Bambu X2D. The X2D has two nozzles; the second can't reach x < 20.5 mm. Every part is generated in Python and painted into per-colour volumes, then written to a Bambu 3MF. There are two kits: the Halifax (`halifax/`, this brief's main source) and the Hawk (`hawk/`, maintained by another session: **read it, but don't plan edits that break it**). One Halifax build takes about 20 minutes and 3 GB (`cd halifax/cad && python -u colour.py OUT project_settings_template.json`). Most of the real cost has been physical test-print rounds that found problems a script could have found first.

## Read these (in this order, skim the long ones)

1. `LESSONS.md` (root, 453 lines): the pitfalls, both kits.
2. `.claude/skills/snap-kit/SKILL.md` (51 lines): the workflow for a new kit.
3. `halifax/HANDOFF.md`: current state and build commands.
4. `common/tools/*.py`: existing checks (list below).
5. `halifax/cad/kitlib.py` (681 lines) and `hawk/cad/kitlib.py` (503 lines).
6. `halifax/cad/colour.py` (994 lines): look at `main` (bottom), `Outside`, `object_settings`, `PLATE_GROUPS`, `pack`; and `hawk/cad/colour.py` (780 lines) for the same jobs done differently.
7. `git log --oneline -60` for how problems were found and fixed.

Don't open the `.3mf` files directly (39-75 MB zips); the tools below read them.

## Problems the test prints (or the slicer) found, and the check that would have caught each

| # | Problem (Halifax, Nov 2026) | Found by | A check that would have caught it |
|---|---|---|---|
| 1 | Fin tip pocket and tab slot opened onto the bed face: their roofs bridged the whole 34 mm chord, printed rough and loose | tail test 1 | Downward-facing area above the bed per part, with bridge spans, in the **print pose** (`overhang.py` exists but wasn't run or didn't flag it) |
| 2 | Gun barrels hung in the air (cantilevered 13 mm barrels) | slicer warning, user | Same as 1 |
| 3 | Camo painted on internal faces: joint faces between sections (a slightly tilted face gets a film over its whole area), key-slot floors, wing-root tongues, nacelle half split faces and wing notch, nacelle parts under the wing | user, in the slicer preview | Non-black area on faces that touch another part in the assembly, or on the bed/top joint faces (`common/tools/facepaint.py` measures the latter per object) |
| 4 | Thin wall over the fin-rod slot came out coloured on its inside when sliced (0.9 mm wall, 0.8 mm paint) | user, slicer preview | Paint within about one line width (0.45 mm) of an internal face |
| 5 | Wing roundel and code-letter inlays cut too deep: through the wing, and a red letter visible from the underside | user | Inlay depth against local wall thickness; colours seen from the opposite side (`colour_check.py` does the view part) |
| 6 | Mesh too coarse: lofted fuselage sides came out as flat bands up to 0.5 mm inside the true surface (a visible "fillet") | user | Mesh deviation from the exact B-rep (sampled), or left/right symmetry of symmetric parts |
| 7 | Finer mesh left one part (tail turret glazing) not watertight | build crash | Every part a single watertight solid (done ad hoc with `decompose()`) |
| 8 | Plate failed to slice: Bambu prints a brim with whichever filament starts the first layer, and a 6 mm brim on a part at x 21 put the second nozzle at x 15 | slicer error | Placement rule: x >= 20.5 + brim width for every part (now `BED_X0 = 27.5`) |
| 9 | Plate failed with "G-code conflicts": the prime tower grows with colour count, and its rib walls stick out past the nominal square | slicer error | Tower footprint and clearance from parts (now 35 x 50 mm, 12 mm clear) |
| 10 | Build used over 100 GB and was killed: Manifold is lazy, and keeping 80 parts' unevaluated histories held every intermediate | build crash | Peak memory per part in the build log, with a limit |
| 11 | A 0.06 mm "clash" between wing root and fuselage: two meshes of one flush surface | `interference.py` | Interference with a threshold that tells real clashes from flush faces |
| 12 | Wing key too near the leading edge: the joint peeled open from the trailing edge | joint test 1 | Design rule, not a check |
| 13 | Key fits: 0.15 a side slightly loose on most joints, 0.10 right; rod slot 0.15 right | joint and tail tests | Not checkable: needs a fits table with the tested value and date per joint type |
| 14 | Non-critical slicer warnings (floating regions, cantilevers) that are known and accepted, mixed with new ones | slicer | A list of accepted warnings per part; flag anything new |

Most of these became a rule in `LESSONS.md` only after they cost a print.

## Existing check tools (`common/tools/`)

- `interference.py`: overlapping parts in the assembled model (needs `python halifax.py OUT2`, 10 min).
- `overhang.py`: bed contact area and downward overhangs per part in the print pose.
- `colour_check.py`: colours seen from one direction (camo flecks on a black underside).
- `facepaint.py`: paint on each object's bed and top faces, read straight from a 3MF.
- `slice.py`: slices every plate with the Bambu CLI and summarises time, grams, colour changes, and warnings and errors. It reads filament names from `halifax/cad/colour.py` (hard-coded).
- `render.py`, `raster.py`, `closeup.py`: previews. `ref_overlay.py`: outline over a calibrated reference drawing (images live in `ref/`, git-ignored, not on this Mac at the moment).
- In the build itself: `kitlib.largest_piece` (single solid), peak memory per part (printed by `colour.py`).

## The two kitlibs

Shared names (28): `band box clip connector_key cs cyl_axis disc dots_along inner_core key_slots largest_piece make_inlay make_section_inlay mesh_of outer_skin pack paint pose_matrix prism_y prism_z project_settings raster_section rect_outline ring slab surface_extreme text_section to_manifold write_3mf`.

Same name, different body (10): `connector_key key_slots make_inlay make_section_inlay pack paint pose_matrix project_settings surface_extreme write_3mf`.

Only in the Halifax: `place_towers`, `floor_plane`, `halfspace`, `peg_on_floor`, `surface_hits`, `under_band`, `safe_name`, and helpers `_along _plane _z_to`. Only in the Hawk: `spring_key`.

Halifax-only work that lives in `halifax/cad/colour.py` but is generic: `Outside` (paint only the outside of the assembled model), `leaf` (drop Manifold's lazy history), the build loop, plate grouping and packing, nozzle mapping. Each kit has its own Bambu project settings file.

## Constraints for the design

- The Hawk is another session's kit: any migration plan must leave it building as it does now, or put its switch-over in a separate step its owner can take.
- No change may alter a printed part without saying so. A good acceptance test: a rebuild matches the committed 3MF (object count and volumes per colour; meshes differ slightly between runs, see `HANDOFF.md`).
- Checks must run without the Bambu GUI and without the reference images. Slicing (about 1 minute per kit) is acceptable; a second 10-minute assembled build is not, unless it can be folded into the main build.
- Python 3.13, manifold3d, trimesh, CadQuery, numpy, shapely. macOS, 3 GB is fine, 100 GB isn't.
- Keep it simple enough that a session can run it after every build without thinking.

## Deliverables (write these two files; change nothing else)

### 1. `common/briefs/kit-lint-design.md`
- The checks: for each, what it measures, its input (built parts in memory, `OUT/stl`, the 3MF, the slice result), a threshold and why, and which problems in the table above it catches.
- Where it runs: inside `colour.py` after painting, as a separate script, or both. What it prints and when it fails.
- Which existing tools it absorbs, keeps or retires.
- How accepted exceptions are recorded (problem 14) and the fits table (problem 13).
- Order of implementation, smallest useful step first, with a rough size for each.
- Anything in the table you think is better solved by a design rule than a check.

### 2. `common/briefs/shared-kitlib-plan.md`
- What goes into a shared `common/kitlib` (and maybe a shared build loop), what stays per kit.
- For each of the 10 diverging functions: which version wins, or how to merge them, and what changes for each kit.
- Step-by-step migration that keeps both kits building at every step; where the Hawk's owner has to act.
- How to prove nothing changed (the acceptance test above).
- Risks and what not to share.

Be concrete: function names, file paths, thresholds in mm. Say where you're unsure rather than guessing.
