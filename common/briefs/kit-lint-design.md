# Design: kit lint

Written 2026-11-15 in answer to `common/briefs/fable-kit-lint-and-shared-kitlib.md`. Design only: nothing here is built yet. All lengths are printed millimetres (the Hawk's 1:40 model lengths times `PRINT_K`).

## Summary

One script, `kitlint`, reads the kit 3MF that the build just wrote, plus a small sidecar file the build writes next to it, and prints one line per finding. The build calls it as its last step, so a session gets the report without doing anything. A second mode adds slicing (about 1 minute a kit) for handover.

- It checks the file that ships, not the build's memory, so it also runs on a committed 3MF with no build, and on the Hawk without touching the Hawk's code.
- It replaces the second 10-minute assembled build (`python halifax.py OUT2`): the sidecar carries each part's transform back to the assembled frame, so the clash and paint checks rebuild the assembled model from the 3MF.
- Three things can't be seen in the 3MF and stay in the build as guards: mesh accuracy against the B-rep, peak memory, and dropped pieces. They write their numbers to the sidecar and `kitlint` reports them.
- Known, accepted findings live in `<kit>/lint.toml`. Anything not listed there is new and is flagged.

## Inputs

| Input | Written by | Holds |
|---|---|---|
| `KIT.3mf` | `write_3mf` | Per object: the colour volumes in print pose, plate, position, per-object settings. Per plate: nozzle map. Project settings: tower positions, bed limits (`extruder_printable_area`, `printable_area`), `prime_tower_width`, line width, brim. |
| `KIT.lint.json` (the sidecar) | the kit's `colour.py` | Per object: `to_assembled` (3 x 4 matrix from the object's 3MF coordinates to the assembled frame, or null for loose keys and test pieces), `mesh_dev` and `mesh_fallback` from the mesher, dropped pieces. Build: peak memory, seconds, git revision. `fits`: the current value of each constant named in `fits.toml`. |
| `KIT.sig.json` (the signature) | `kitlint --write-sig` | Per object: name, plate, position, size, volume per colour, settings. Per plate: nozzle map, tower position. A few KB of readable JSON, committed next to the 3MF. |
| `<kit>/lint.toml` | by hand | Kit rules (base colour, what may be seen from below), accepted exceptions, budgets. |
| `<kit>/fits.toml` | by hand | The fits table (problem 13). |
| slice result | `common/tools/slice.py` | `summary.json`: per plate time, changes, grams, warnings, errors. |

Without a sidecar, `kitlint` runs the print-pose checks only and says which checks it skipped. That is the Hawk's state until its owner adds the sidecar (about 25 lines in `hawk/cad/colour.py`).

The loader starts from the parser in `common/tools/facepaint.py`. I haven't timed it on the 39 MB kit: regex over about 200 MB of XML may take 30 to 60 s. If it does, cache the parsed arrays in `OUT/lint_cache.npz` keyed on the 3MF's size and time.

I chose a sidecar file over a `Metadata/kitlint.json` entry inside the 3MF because I don't know whether Bambu Studio accepts an unknown entry, and it would drop it on save anyway.

## The checks

Levels: FAIL (exit code 1), WARN (exit 0, or 1 with `--strict`), INFO (in the report only). An accepted exception turns a FAIL or WARN into INFO.

### 1. `diff`: nothing changed that wasn't meant to

- **Measures:** this kit against `KIT.sig.json`: objects added or removed, plate and position (0.01 mm), size (0.05 mm), volume per colour (more than 0.5 mm3 and 0.02 %), per-object settings, nozzle maps, tower positions.
- **Input:** 3MF and the signature.
- **Fails:** never on its own. It prints the changes as a table. The session reads it and either explains each line or finds a bug. `--write-sig` accepts the new state.
- **Why these tolerances:** `HANDOFF.md` says a rebuild changes the mesh slightly without changing the design. I don't know how large that noise is in volume. Measure it once (two builds of an unchanged tree) and set the tolerance at three times the largest difference.
- **Catches:** the brief's constraint "no change may alter a printed part without saying so". It is also the acceptance test for the shared kitlib (`shared-kitlib-plan.md`).

### 2. `solid`: every part is one closed solid

- **Measures:** each colour volume is a valid manifold with positive volume; the colours fill the part exactly (sum of colour volumes equals the volume of their union, within 0.5 mm3 or 0.02 %); the union is one piece (pieces under 0.01 mm3 ignored, as `HANDOFF.md` describes for `decompose()`); no negative-volume shell over 0.5 mm3 (a sealed hollow, the Hawk nozzle lesson).
- **Input:** 3MF. The sidecar adds the pieces `largest_piece` dropped in the build: WARN for any over 1 mm3 (today that is a line on stderr nobody has to read).
- **Unsure:** the 3MF rounds vertices to 0.001 mm, so the union of colour volumes may leave hair cracks that `decompose()` counts. If the first run shows that, take the piece count from `OUT/stl/<name>.stl` (the uncut solid) when it is there, and keep the union only for the volume test.
- **Catches:** 7. Also the LESSONS items on islands, loose rivet dots and sealed hollows.

### 3. `plate`: the plate can be printed

Limits are read from the 3MF's own project settings where they exist (second nozzle x 20.5, bed 256 x 256, tower width 35), so the check follows the printer profile.

| Rule | Threshold | Level | Why |
|---|---|---|---|
| Part inside the second nozzle's reach, on a plate that uses nozzle 2 or is on "Auto For Flush" | x min >= 21.0 | FAIL | `extruder_printable_area` 20.5 plus 0.5 |
| The same with the part's brim | x min minus `brim_width` >= 21.0, for objects with an explicit brim (`outer_only`) | FAIL | Problem 8: a 6 mm brim at x 21 reached x 15. For `auto_brim` the width isn't known before slicing, so only the slice check covers it |
| Part and brim on the bed | within 0 to 256 in x and y; height <= 256 | FAIL | |
| Parts apart | outlines >= 2 mm plus both brims | WARN | |
| One tower position per plate | `wipe_tower_x` and `_y` have one entry per plate | FAIL | LESSONS: the template's 3 positions on a 9-plate kit |
| Tower clear of parts, on plates with more than one colour | tower box 35 x 50 mm; >= 12 mm from every part outline: WARN; under 6 mm plus brim: FAIL | | Problem 9. 35 x 50 and 12 are `kitlib.TOWER_DEPTH` and `TOWER_CLEAR` |
| Tower on the bed | x >= 22; x + 35 <= 241; y >= 2; y + 50 <= 254 | FAIL | The Hawk's tower ran off at x 214 and is fine at x 200. 241 is my guess between them: adjust if a plate fails or is wrongly flagged |
| Colours per plate | <= 5 | FAIL | Already an `assert` in both builds |
| Colours on nozzle 2 | <= `aux_colours` in `lint.toml` (Halifax 1) | FAIL | The user's auxiliary nozzle takes one colour |
| One layer height on a multi-colour plate | all objects equal | WARN | `colour.py` says the prime tower needs it, but `halifax/docs/slicing.md` shows plates 4 and 6 at "0.12/0.2" slicing fine. Unsure: downgrade to INFO if it only produces noise |
| Names | no `<>:/\|?*"` in object or plate names; object names unique; project settings present; every slot used has a filament | FAIL | LESSONS: Bambu Studio refuses the file, or opens bare geometry |
| Part sits on the bed | lowest z within 0.01 of 0 | FAIL | |

- **Input:** 3MF.
- **Catches:** 8 (explicit brims) and 9 before slicing.
- **Finding while reading:** `place_towers` falls back to the whole bed and can then put a tower at x up to 220, which is past where the Hawk's failed (214). The rule above would flag it.

### 4. `overhang`: nothing hangs in the air in the print pose

`overhang.py` sums the area of faces steeper than 50 degrees and prints it with no threshold, so the fin pocket (about 120 mm2 on a part with other overhang) and the gun barrels (thin lines) never stood out. Area is the wrong measure. What matters is how far a layer reaches from its support.

- **Measures:** slice each part at its own layer height (`Manifold.slice`). For each layer, the unsupported region is the layer minus the layer below grown by `max(layer height, 0.21)` (half a 0.42 line). For each connected region: its area, its height above the bed, and its **reach**: the largest distance from any point in it to supported material (found by offsetting the support until the region is covered). A bridge of span L has reach L/2; a cantilever of length L has reach L.
- **Speed:** only slice the layers where down-facing triangles exist (most of a fuselage section on end has none). Not measured: I expect under a minute for the kit.
- **Input:** 3MF (union of the colour volumes; see the note under `solid`).

| Finding | Threshold | Level |
|---|---|---|
| Long bridge or cantilever | reach > 5.0 mm | FAIL |
| Short bridge or cantilever | reach 1.5 to 5.0 mm | WARN (accept once per part with a reason) |
| Recess on the bed face | region at z <= 3.0 mm, reach >= 1.0 mm, area >= 4 mm2 | WARN |
| Shallow overhang | total area of regions with reach 0.2 to 1.5 mm, per part | WARN when it is over the accepted figure by 20 mm2 and 20 %; with no accepted figure, over 100 mm2 |

- **Why:** the key-slot ceilings are 2.7 mm bridges (reach 1.35) and print fine, so they stay under the WARN line. The gun barrels (13 mm, reach 13) and the Hawk's root tongues (13 to 14 mm) are far over the FAIL line. The fin pocket roof is caught twice: by reach (at least 1.75, or 17 if it was only held at its ends) and by the bed-face rule, which is LESSONS' "never put a joint recess on a part's bed face" as a check. The shallow-overhang line is for curves like the tailplane leading edge before its 45 degree ramp, and it works by comparison because every aerofoil has some.
- **Unsure:** 5.0 is a judgement. The report lists every region with reach >= 1.5, so the first full run shows where the real parts sit and the line can move.
- **Catches:** 1, 2. Also the LESSONS items on tongues above the bed, the canopy on its pegs and socket ceilings.

Bed contact, in the same pass:

| Finding | Threshold | Level |
|---|---|---|
| Small first layer | contact area < 20 mm2 | WARN |
| Tall on a narrow base | height > 6 times the narrowest width of the contact outline, and no brim set on the object | WARN |
| Centre of mass outside the contact outline | | FAIL |

These are LESSONS' "tall pieces on end need a real base" and the wheel on a thin ring.

### 5. `clash`: parts don't overlap when assembled

- **Measures:** every pair of parts whose assembled boxes overlap. Raw overlap volume, and the overlap after shrinking one part by 0.08 mm (inside a box round the overlap, so it is cheap).
- **Input:** 3MF and sidecar. Parts with `to_assembled` null (loose keys) are left out, as the HANDOFF does by hand today.
- **Threshold:** shrunk overlap > 0.05 mm3: FAIL. Raw overlap > 0.5 mm3 that vanishes when shrunk: INFO ("flush faces").
- **Why:** the wing root on the fuselage is two meshes of one surface and overlaps by up to 0.06 mm (problem 11); a real clash is deeper than any fit (0.08 to 0.15). 0.08 sits between. Intended press fits (the Hawk's crush ribs, 1.4 mm3) go in `lint.toml` as accepted pairs with a volume limit.
- **Catches:** 11. Replaces `interference.py` and the `OUT2` build.
- **Later, optional:** give each key an assembled position in `halifax.py` (the points passed to `key_slots`). Keys would then be checked against their slots too.

### 6. `paint`: colour only where it shows

Four measures, cheapest first.

**6a. Flat-face paint (no sidecar needed).** `facepaint.py` as it is: the area of non-base colour lying flat on each object's bed face and top face. INFO, with a WARN when it rises over the accepted figure by 10 mm2 and 20 %. On its own it can't tell a joint face from a painted bed face (the fins, the Hawk's chevrons), which is why it needs accepted figures.

**6b. Hidden paint (needs the sidecar).** This is the real check for problem 3, and it does not reuse `colour.Outside`: a check that shares the generator's method only proves the generator ran.

- Put every part in its assembled place. Fill a 0.5 mm voxel grid from surface samples (0.2 mm spacing). Flood the empty voxels from a corner: that is the outside air. Fit gaps (0.1 to 0.36) are narrower than a voxel, so joints close by themselves; key slots between joined parts are sealed and never fill; panel lines (0.5 wide) stay open, which is right, since they are outside.
- For each sample on a coloured surface of a part (colour other than the part's base, on the part's own outer surface), look 0.5 mm along its normal: air means visible.
- A coloured sample that is not visible is allowed only in the band where a joint face meets the outside: air within 1.5 mm to the side. `Outside` deliberately leaves a `SKIN`-wide band there so colour runs across the join.
- **Thresholds, per part:** hidden colour with no air within 1.5 mm: FAIL over 5 mm2 (the films measured 60 to 635 mm2 per part before the fix). Hidden colour with air straight behind it within 1.5 mm (the inside of a thin wall, problem 4): FAIL over 2 mm2.
- **Memory:** the Halifax grid is about 160 M voxels, 160 MB as booleans. Don't use a full distance transform (3 GB or more); the lookups above only need the air mask.
- **Unsure:** this is the least certain check. A 0.5 mm grid is coarse next to a 0.9 mm wall and a 0.8 mm skin, so the two area thresholds will need tuning. Validate it before trusting it: build with `Outside` switched off (add an `OUTSIDE=0` switch) and confirm it reports the joint faces, key-slot floors, tongues and the fin-rod slot wall; then confirm the current kit passes.
- Parts that can't all be fitted at once (wheels-up inserts against the gear) are marked `alt` in `lint.toml` and left out.

**6c. Seen from a side (needs the sidecar).** Rules in `lint.toml`, for example Halifax from below: only Black and Silk Silver, skipping the stand. Sum the visible coloured area from 6b whose normal faces that way. FAIL over 2 mm2 per part. Replaces `colour_check.py`, and its stray hits on joint faces are gone because 6b already knows what is hidden.

**6d. Films and specks (no sidecar needed).** For each connected piece of each colour volume: mean thickness 2 x volume / area under 0.2 mm with area over 3 mm2: WARN (a film or zero-thickness sheet). Smallest box dimension under 0.42 mm with volume over 0.05 mm3: WARN (thinner than one line, the slicer will drop it: the Hawk's "empty layer" lesson). This doesn't find a film joined to the main skin; 6b does.

- **Catches:** 3 (6b, partly 6a), 4 (6b), 5 as far as "a colour seen from the wrong side" (6c). The other half of 5, the socket too deep, is a rule in the generator: see the last section.

### 7. `pairs`: port matches starboard

- **Measures:** for names ending `_port` / `_stbd`: both exist, same plate group, same layer height, total volume within 0.5 %. With the sidecar: the surface of one against the mirror of the other in the assembled frame, sampled: over 0.1 mm apart is a WARN.
- **Why:** the mesh "fillet" (problem 6) was seen as one side differing from the other and was confirmed fixed when the "sides match to 0.03 mm". The Hawk's padded `clip` was found by an uneven inlay count.
- **Catches:** 6 when the coarse mesh is one-sided. A mesh that is equally coarse on both sides passes, so check 8 is the real one.
- Colour volumes are not compared unless `lint.toml` says the scheme is symmetric (the Halifax camo isn't).

### 8. Build guards (in the build; reported through the sidecar)

**Mesh accuracy.** In the kit's mesher (`halifax.mesh`, `hawk.to_m`), after tessellating: take the centres of the 300 largest triangles and measure each one's distance to the B-rep solid. Store the largest per part as `mesh_dev`. WARN over 0.15 mm, FAIL over 0.25 mm. The docstring of `halifax.mesh` says 0.05 rad keeps it under 0.15 and that 0.15 rad gave 0.5, which was visible. Also store `mesh_fallback` when `mesh` silently retries at 0.15 rad (today nothing reports that, and a fallback brings problem 6 back for that part): WARN unless accepted (the tail turret glazing is). Unsure: the cost of 300 OCC distance queries a part; if it is slow, sample 50. Catches 6.

**Memory.** After each part: if peak memory is over 8 GB, stop the build with the part's name (it is 3.1 GB today; the bad run reached over 100). `ru_maxrss` is bytes on macOS and kilobytes on Linux: the helper must handle both. The sidecar keeps the peak; WARN when it is 1.5 times the accepted figure. Catches 10.

**Dropped pieces** and **sealed hollows**: already computed by `largest_piece`; store them (see `solid`).

### 9. `slice`: the slicer agrees (`kitlint --slice`)

- **Runs** `slice.py` (plate by plate, about 1 minute) and reads `summary.json`.
- **FAIL:** a plate that doesn't slice, or any slicer error.
- **Warnings** are turned into `(object, kind)` pairs. Bambu's text is `It seems object NAME has floating regions.` or `... floating cantilever.` Each pair is looked up in `lint.toml`. Listed: INFO. Not listed: WARN, "new slicer warning". A listed pair that no longer appears is reported as stale so the list shrinks.
- **Budgets:** time, colour changes and waste grams per plate against the figures in `lint.toml`: WARN over 5 % more. This is how a pose change that doubles the swaps gets noticed.
- **Log noise:** add "Detected missing Voronoi vertex" to the report as INFO, not to `HARMLESS`: it appears on plates 2 and 3 of the current kit, which slice, but I don't know that it is always harmless.
- **Fix needed in `slice.py`:** `filament_names()` reads `halifax/cad/colour.py` for every kit. Take the names from the 3MF instead (each volume's name in `model_settings.config` ends with its filament name).
- **Catches:** 8 and 9 for certain (including auto brims), 14, and the Hawk's "empty layer".

### 10. `fits`: the fits table matches the code

Problem 13 can't be checked by geometry, but two things about it can: see "The fits table" below.

## Where it runs and what it prints

1. **End of every colour build.** `colour.py` writes the 3MF and the sidecar, then calls `kitlint` on them. The 3MF is always written, so the user can still open it; a FAIL makes the build exit with code 1. `LINT=0` skips it for single-part work (`ONLY=`), where plate and clash checks mean nothing.
2. **Before a handover or commit:** `python common/tools/kitlint.py halifax/kit/halifax_kit.3mf --slice`.
3. **Any time, on any 3MF:** the same command without `--slice`. `--only overhang,plate` picks checks. `--write-sig` accepts the current state as the signature.

Output is one line per finding, worst first, then a summary. It also writes `lint.json` next to the 3MF.

```
kitlint halifax_kit.3mf   88 objects, 7 plates   sidecar: yes   signature: 2026-11-11
FAIL overhang  guns_dorsal_lower    cantilever, reach 13.0 mm at z 2.4 (limit 5.0)
FAIL plate     plate 1 fuselage_nose  brim reaches x 15.0 (second nozzle from 20.5)
WARN slice     plate 6 stand_post   new warning: floating cantilever
info overhang  fuselage_rear        bridge, reach 1.4 mm at z 21.6   accepted: key-slot ceilings
info diff      wing_outer_port      Dark Green 412.6 -> 409.1 mm3
stale accept   guns_tail_lower / slice / floating cantilever   (no longer reported)
2 FAIL, 1 WARN, 14 accepted, 1 stale.   Skipped: none.
```

## Existing tools

| Tool | Fate |
|---|---|
| `facepaint.py` | Absorbed: its parser becomes the loader, its measure becomes 6a. Remove the file once `kitlint` is in use. |
| `interference.py` | Absorbed by `clash`. Keep the file until the Hawk writes a sidecar: the Hawk's handoff uses it on STLs. |
| `overhang.py` | Replaced by `overhang`. Same condition as above. |
| `colour_check.py` | Replaced by 6c once 6b is validated. Until then keep it. |
| `slice.py` | Kept as the slicer runner; `kitlint --slice` calls it. Fix `filament_names`. |
| `single_nozzle.py`, `render.py`, `raster.py`, `closeup.py`, `ref_overlay.py`, `silhouette.py`, `grid.py`, `white_regions.py`, `trace_colours.py`, `compare_ref_model.py` | Kept. They are previews and reference tools, not checks. |
| `python halifax.py OUT2` as a check step | Dropped once `clash` runs from the sidecar. The geometry-only build stays for quick single-part work. |

Code goes in `common/kitlint/` (loader, one module per check group) with a thin `common/tools/kitlint.py` so it runs by path like the other tools. The loader and the checks must not import CadQuery.

## Accepted exceptions (`<kit>/lint.toml`)

TOML, because every entry needs a reason next to it and Python reads it without a new package.

```toml
base = "Black"            # the colour that isn't paint
aux_colours = 1           # colours the second nozzle may carry

[[seen]]
from = "below"
expect = ["Black", "Silk Silver"]
skip = ["stand_", "df_loop"]

[[accept]]
check = "slice"
part = "fuselage_rear"
match = "floating regions"
reason = "key-slot ceilings (2.7 mm bridges), wing-root pockets, stand socket"
date = 2026-11-08

[[accept]]
check = "overhang"
part = "turret_dorsal"
limit = 3.0               # reach in mm: a longer one is new
reason = "..."
date = 2026-11-08

[[accept]]
check = "clash"
part = "wing_inner_stbd x fuselage_front"
limit = 1.0               # mm3
reason = "flush root face, two meshes of one surface"

[budget."Wings and fuselage"]
hours = 25.6
changes = 439
waste_g = 262
```

- An entry matches on check, part (a prefix is allowed) and, where it has one, a limit. Over the limit is a new finding.
- An entry that matched nothing is printed as stale.
- Figures that work by comparison (shallow overhang, flat-face paint, memory) are written by `kitlint --accept-figures` into a `[figures]` table, so nobody types them.
- **Finding while reading:** `HANDOFF.md` lists the gun packs among the expected slicer notes, but the latest slice on disk (`out/slice/halifax_kit/summary.json`) reports only `fuselage_rear`, `turret_dorsal` and `stand_post`: the guns were fixed on 2026-11-11. Build the first `lint.toml` from a fresh slice, not from the handoff.

## The fits table (`<kit>/fits.toml`)

One entry per joint type, with the constant that holds it, so the tested value and the code can't drift apart.

```toml
[[fit]]
id = "fuselage key, nose joint"
const = "FUSE_KEY_FIT[0]"          # evaluated in the kit module (halifax.py)
value = 0.10                       # mm per side, printed size
kind = "flexing key in a slot"
parts = ["fuselage_nose", "fuselage_front"]
tested = { value = 0.10, date = 2026-11-09, print = "joint test 2", layer = 0.24, result = "right" }
history = ["0.15: slightly loose (joint test 1, 2026-11-08)"]
```

Fill it from `HANDOFF.md` ("Test print results" and the dated sections) and the LESSONS printer table: `FIT`, `KEY_FIT`, `FUSE_KEY_FIT`, `WING_SPLIT_FIT`, `NOSE_KEY_FIT`, `TAIL_KEY_FIT`, `FIN_ROD_FIT`, `FIN_POCKET_FIT`, `GEAR_PLUG_FIT`, `STUB_GRIP`, `STUB_SPIN`, `PEG_GRIP`, `INLAY_FIT`, `PROP_BOSS`. `status = "untested"` or `"scaled"` is allowed and reported.

What `fits` checks:
- The build evaluates each `const` in the kit module and writes the values to the sidecar. A value that differs from the table: WARN ("code says 0.15, table says 0.10 tested").
- A constant in the kit module whose name ends in `_FIT` or `_GRIP` and isn't in the table: WARN.
- The layer height of each listed part in the 3MF against `tested.layer`: WARN when they differ. This is a live case: `HANDOFF.md` notes the tailplane slot and wing-root pockets were tested at 0.16 and now print at 0.24. LESSONS also says fits differ by print orientation, so the entry can carry `pose` later.
- Entries with `status = "untested"`: INFO.

## Order of implementation

Sizes are rough lines of new code. Each step is useful alone.

| Step | What | Size | Needs |
|---|---|---|---|
| 1 | Loader (from `facepaint.py`), signature and `diff`, `solid`, `plate`, name-and-count half of `pairs`, `lint.toml` reading, the CLI and output. Run it on both committed kits and write their signatures. | 300 | Nothing. Works on the Hawk as it is. |
| 2 | `--slice`: warnings against accepted, budgets; fix `slice.py` filament names. First `halifax/lint.toml` from a fresh slice. | 100 | Step 1 |
| 3 | `overhang` and bed contact. Validate on old kits: the 3MF before `e8c0457` (fin pockets) and before `16471d8` (gun barrels) must FAIL, today's must pass. Get them with `git show REV:path > file`; the path was `kit/halifax_kit.3mf` before the restructure. | 180 | Step 1 |
| 4 | Sidecar from the Halifax build; `clash`; call `kitlint` at the end of `colour.py`. Drop the `OUT2` check step from `HANDOFF.md`. | 150, plus 30 in `colour.py` | Step 1 |
| 5 | Build guards: mesh deviation and fallback report in `halifax.mesh`, memory limit. | 70 | Step 4 |
| 6 | `paint` 6a and 6d (cheap), then 6b and 6c with the `OUTSIDE=0` validation. | 250 | Step 4 |
| 7 | `fits.toml` filled in, and the `fits` check. | 70, plus the table | Step 4 |
| 8 | Hawk sidecar, `hawk/lint.toml`, `hawk/fits.toml`. | 25 in `hawk/cad/colour.py` | The Hawk's owner |

Step 1 comes first for a second reason: the shared kitlib migration uses `diff` as its proof.

Steps 3 to 7 each need one Halifax build (20 minutes) to try on real data, but they can share builds: write the sidecar in step 4 and later steps run on the saved 3MF.

## Better as a rule than a check

| # | Problem | Why a rule |
|---|---|---|
| 12 | Wing key too near the leading edge | A leverage judgement. Rule (already in LESSONS): key across the middle of the chord, 12 mm into each piece. A check would need to know what a "joint" is. |
| 13 | Fits | Only a print tells. The table records it; the check only keeps table and code together. |
| 5 | Inlay cut too deep | Guard it where the socket is cut. `make_inlay` already keeps `INLAY_FLOOR` clear of any underside. Make that general: a helper `wall_left(P, cutter)` that returns the area of `P`'s outer 0.3 mm that a cutter removes, called for every slot, socket and pocket, with the expected mouth area. This is the Hawk's formula `(slot ^ (P - P.translate(-0.3 * n))).volume() == 0`. It catches a slot breaking through a tapering part at the moment it is cut, with the slot's name. |
| 1 | Recess on the bed face | The check catches it, but the rule comes first: choose the pose so recesses open upwards. |
| 8, 9 | Brim and tower placement | Derive the packer's margins from the printer limits and the largest brim in the group (`20.5 + brim + 1`), not from literals. `plate` then only confirms it. |
| 10 | Memory | `leaf()` after every part is the fix. The guard only stops a regression early. |
| 6 | Mesh too coarse | Partly a rule: mesh lofted skins at 0.05 rad. The guard measures it because a setting can be right and the result still wrong (the fallback). |

## Decisions I'd like from the user

1. **Should a FAIL stop the build's exit code?** I've assumed yes, with the 3MF still written.
2. **Three small files committed next to each kit 3MF** (`.sig.json`, `.lint.json`, and `lint.json` output is not committed). Fine?
3. **The hidden-paint check (6b)** is new machinery (a voxel flood fill) and the least certain part. The alternative is to reuse `colour.Outside` as the checker, which is quicker to write but can't catch a bug in `Outside` itself. I recommend the independent one, last in the order.
4. **Overhang limit of 5 mm reach** (a 10 mm bridge or 5 mm cantilever fails). Your eye on the first report will set this better than I can.
