# To do

## Next build (user's notes, 2026-11-16; build once more feedback is in)

- [ ] **No colour on the prop mushroom bosses.** The boss on each nacelle nose (`prop_boss`, both nacelle halves) must be all black: colour volumes inside a snap feature make it weaker. Keep the camo off it in `colour.Outside.keep_paint_outside` (or paint the boss region black). Do the same for the turret snap bosses (`snap_boss`) on `fuselage_rear` and `fuselage_tail`.
- [ ] **Gun packs as two separate pieces, one per side.** Each piece is one stacked pair (one gun above the other), so the pair looks as if it could travel up and down in the turret. Today each pack is split top/bottom into `guns_*_upper` / `guns_*_lower` (`gun_half`, `GUN_PEG`), each half holding one gun from each side. Split it left/right instead (`GUN_SIDE` 3.2 either side of the centreline), and check how each piece prints and fits in the turret slot.

## After the test print of the current iteration (flexing keys, built-in pegs, D/F pop-in)

- [ ] **Rear fuselage and the code letters.** The codes are now press-in inlays in the on-end rear section. Consider instead:
  - **Option A:** print the rear fuselage in left/right halves lying flat, like the earlier model, so the codes and roundel print in as colour.
  - **Option B:** keep the on-end section, but cut the code/roundel area out as a flat-printed side panel that slots in, with the lettering printed into it.
  - Decide from how the inlays look and fit on the test print. Weigh layer-line visibility (on end hides them), colour changes on the fuselage plate, and how well the joints show.

## Functionality (where it conflicts with scale accuracy, favour function)

- [ ] **Print-in-place hinged control surfaces.** Explore ailerons, elevators and rudders that move: hinge knuckles printed in place on a pin, or a clearance hinge line about 0.3 mm. Check what the X2D clearances allow with a small test coupon first.
- [ ] **Stronger prop and wheel shafts.** Make the prop shafts and wheel axles thicker than scale where needed, for example 4 mm or more, with a larger flange and collar. Also try:
  - printing them on their side so the layers run along the shaft;
  - using a D-flat or hex in place of round where the part must turn with the shaft.
  Re-run the pin fit test at the new sizes.
