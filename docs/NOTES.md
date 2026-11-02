# Open list, 2026-09-28

The material and lighting translation is now in rF2's own terms rather than
AC's, taken from Studio 397's Joesville: material colours at rF2's convention,
scene ambient 126, sun 220, fog 50 to 5000. The compensation machinery that
existed to fight the old translation -- a 1.9 gain, a ceiling that clipped the
brightest materials, an ambient of 237, fog pushed to 60000, a gamma exponent
-- is all gone.

## Judge this build against official rF2 content, not against CSP
The reference changed deliberately. Assetto Corsa is running CSP, whose
tonemapping we cannot reproduce by translating materials: in the same frame its
ground is brighter than ours and its sky darker, which is a response curve, not
a coefficient. Measured, AC's total light is around 440 units where rF2 native
gives about 300. Chasing the remainder through material values is what produced
two days of compensations.

## Known, measured, and not fixable by translation
- The hillside sits near 0.82 of where it was, and around half of AC's. The
  composed textures are within 9% of AC's own albedo (sbanc 0.97, splat_maps
  0.97, sand_trap 0.95, asphalt 0.91), so this is light, not texture. Scene
  ambient is the knob if it reads too dark next to official content.

## Next, and the most promising thing found so far
The material flag bit. Studio 397's foliage carries 0x68902003, ours carries
0x68900023: they set 0x00002000 and we set 0x00000020. The addon labels 0x20
Transparency, which is alpha blending, and labels 0x2000 "Car Body", which is
plainly wrong for a tree -- so 0x2000 is almost certainly the alpha test bit.

Everything else about our cut-outs now matches theirs: threshold correct and at
the right offset, bump shader that supports testing, blend source and
destination identical. The material is simply flagged to blend rather than to
test, which is why four builds of changing values changed nothing.

Set 0x00002000 for alpha tested materials, probably instead of 0x00000020.
Try it on a handful of meshes first and look at the flag word in the gmt before
spending an hour.

## Open
1. White tree trunks. Not the specular placeholder, not the normal map
   (bark_NM measures R 0.501 G 0.502 B 0.984, the same convention as every
   other one). Under the new scheme bark sits at 0.79 against asphalt's 0.95,
   so it is darker than it was relative to the road. Re-judge before digging.
2. Gravel and sand could take slightly more contrast. Second stage detail
   textures are used by nothing else, so a contrast boost there is texture
   only and needs no re-export.
3. Trees drawing over nearer trees. Foliage is alpha tested now with AC's own
   ksAlphaRef, which should let it write depth and sort itself. Confirm.
4. Flickering. Eleven decal materials are lifted a centimetre along their
   vertex normals. Confirm, particularly off the asphalt where it started.
5. drift is several builds behind. Rebuild when convenient, it is minutes.

## Parked with reasons
- detailUVMultiplier: AC authors a detail scale on 37 materials; its value for
  sand_trap works out finer than ours, not coarser, so adopting it would not
  give the coarser gravel that was wanted. Needs a re-export.
- Vegetation saturation: trees and grass bind AC's texture directly, so it
  needs either texture processing or a per material colour.
- Retail packaging (.mas + .mft).

## Habit worth keeping
Two material changes went straight into hour long exports unverified and both
came back broken, the second as green boxes where the trees were. The native
conversion was checked on five materials first and the values landed exactly as
intended. Do that every time.

## The green panels: colour keying (the actual cause)

**The alpha reference does nothing unless colour keying is switched on.**
Texture flag `0x80` at offset +64 from the texture name is the enable. We had
been writing a correct threshold into a test nothing had turned on, so trees,
grass and fences drew as solid panels whatever the number was -- which is why
moving it from 26 to 77 to 191 changed nothing visible.

Found by diffing one of our fence gmts against `Fence_ChainLink.gmt`, which
does the same job with the same shader and works:

| offset | ours | official |
|--------|------|----------|
| +64 texture flags | `0x00000008` | `0x00200098` |
| +100 alpha reference | 191 | 191 |

Across both official tracks `0x80` is set on 18 texture entries, every one a
diffuse map and 17 of the 18 at a threshold of 191: their entire cut-out set.
Every opaque diffuse has reference 1 and the bit clear.

The property name matters, and only one of them works.
`probe_colorkey.py` sets each candidate on its own mesh and reads the
exported byte back:

| property | bit moves |
|----------|-----------|
| `Flag_0x00000080` | yes |
| `ColorKey` | yes |
| `Flag_0x00000080_Color_Key` | no |
| `Color_Key` | no |
| `Transparent_Alpha` | no |

The same trap as `Alpha_Reference` and the blend factors: the assignment is
accepted and silently ignored. `verify_install.py` now checks the bit, and
caught 229 of 229 cut-outs unkeyed in the build before this one.

Our textures were also missing `0x10` Linear_Filter, which all 359 official
texture entries carry and a fresh addon node leaves off.

## The alpha threshold (still right, but it was not the panel)

## The green panels, the flicker, the grass and the fences (threshold detail)

One cause, measured rather than guessed: **the alpha threshold, down the mip
chain.**

rF2 cuts out foliage with the alpha *test*, not blending. 73 of the 75
materials in Joesville and Loch Drummond carry blend factors One/Zero --
trees, 2D trees, shrubs, crowds, chain link and safety fences among them.
Only `Grassverges` and `RoadLines` really blend. Every cut-out they ship uses
an alpha reference of **191**.

Why 191 and not AC's figure. Building a mip averages the transparent
background into the leaves, so the *smaller* the mip, the more of a low
threshold's texture gets through:

| threshold | our trees mip0 -> mip8 | our grass | official Trees3D |
|-----------|------------------------|-----------|------------------|
| 26 (AC's) | 29% -> **46%**         | 33% -> **77%** | 50% -> **100%** |
| 191       | 25% -> 16%             | 30% -> 5%      | 45% -> 25%      |

At a low threshold the quad fills in with `[62 69 34]` dark green as it
recedes -- the green box with a tree in the middle -- and the mip the card
picks changing with distance is the flicker and the pop-in. Official content
at 26 would do the same, so it is the threshold and not our textures: our
tree atlas (29%/25%) behaves just like theirs (50%/45%).

Two things this also explains:

- Every gmt we shipped was *already* opaque One/Zero, because
  `mat["Blend_Source_List"] = 4` as a custom key is silently ignored, exactly
  like `Alpha_Reference` was. "Matching Joesville bit for bit did not cut
  anything" was true, and the reason was the number, not the blending.
- `wood_planks` got a threshold of 128 from the `ksAlphaRef or 0.5` fallback
  while its alpha is uniformly a fifth. The whole wooden fence was being
  discarded.

The threshold is now decided in `bake_layers.cutout_ref` from the texture
that actually ships, three ways:

- **hard mask** (<5% nothing in between) -> 191
- **gradient** (>20% in between) -> left exactly as it was. `gravel_brd` is
  28/28/44 -- the soft sand-to-gravel edge. Raising it would eat a third of
  the border and bring back the on/off line.
- **nothing transparent** -> no alpha test at all

## Reflectance: still open, and quantified

Official rF2 writes `ambient = diffuse = 1.0` on **all 75** materials, with
zero variation: the texture is the albedo and the scene light does the work.
We write AC's `ks` coefficients normalised against the track's upper quartile,
which puts the whole track at about 2.5x AC's reflectance.

Our textures are byte-identical to AC's (checked against the kn5: ratio 1.00
on bark, fences, metal grid and the tree atlas), so the texture pipeline is
not the problem. The white trunk is arithmetic:

| | effective albedo of a trunk |
|---|---|
| AC (`bark.dds` 130 lum x `ksDiffuse` 0.30) | **39** |
| official rF2 (`PalmTrunk` at diffuse 1.0)  | **61** |
| ours (130 x 0.75)                          | **98** |

Both references put a trunk at 39-61 and we are at 98.

Three translations were tried against the data and all three fail:

- *write AC's `ks` verbatim* -> the track goes to 0.4x and everything is dark
- *fold `ks` into the texture* -> works for hard surfaces (bark 39 vs their
  61, metal grid 42 vs 48) and collapses for foliage (trees 9.7 vs 55, grass
  18 vs 65), because AC's `ksTree` coefficients are not plain albedo and CSP
  boosts them further
- *clamp the effective albedo to official's ceiling* -> there is no ceiling
  to clamp to. Official albedo runs median 78, p75 115, max 255.

So AC's `ks` is not a reflectance in rF2's sense and no single factor
reconciles the two. What is left is to drop the global 2.5x lift, keep AC's
relationships without the 1.0 clamp (25% of materials currently pile up on
it), and put the overall level in the scene lighting -- one lever. That
rescales the road, sand, gravel and rubber, which are already signed off, so
it is a separate change and not one to slip in beside the alpha fix.

### Texture flag property names (measured, not guessed)

`probe_colorkey.py` sets each candidate on its own mesh and reads the byte
back out of the exported gmt. The addon is not consistent:

| bit | works | silently ignored |
|-----|-------|------------------|
| 0x80 colour key | `Flag_0x00000080`, `ColorKey` | `Flag_0x00000080_Color_Key`, `Color_Key`, `Transparent_Alpha` |
| 0x10 linear filter | `LinearFilter` | `Flag_0x00000010`, `Flag_0x00000010_Linear_Filter`, `Linear_Filter`, `Filter` |

Run the probe before trusting any new property. Three separate rounds of
this pipeline were lost to assignments that were accepted and dropped.

## The flicker: AC's LOD distances, which we were throwing away

Not the decals, and not a depth bias. AC states a distance range on nearly
every mesh and we ignored both numbers:

| mesh | lod_in | lod_out |
|------|--------|---------|
| `track_hi_1_SUB7`      | 0   | 500  |
| `track_low_014_SUB1`   | 450 | 1000 |
| `Jersey_Plastic_LOW_3` | 190 | 500  |
| `BBgrass.003`          | 0   | 200  |

In AC the high chunk draws out to 500 m and the low one from 450, so the two
coincide across a 50 m band. We drew every level at every distance, so
coplanar copies fought for pixels wherever they overlapped -- measured at the
two places the user named, `track_low_011_SUB1` against `track_hi_5_SUB0`,
same material, median height difference **0.0000 m**.

rF2 takes the same pair as `LODIn`/`LODOut` per instance, so they are now
carried straight across and every detail level is kept: 1045 of 1066 drawn
meshes have a range, nothing is deleted. 127 meshes used to be thrown away by
name matching, which also lost the far geometry that should appear in the
distance.

Three heuristics were tried and abandoned before the LOD data was found, and
each is worth not repeating:

- *keep the richer of two coplanar meshes* -- triangle count does not tell
  AC's levels apart at all. `track_low_011_SUB2` has 4982 triangles against
  `track_hi_5_SUB1`'s 5014, so "richer" retired the near copy and started
  deleting real road.
- *pair them one to one by footprint* -- AC chunks its low detail track
  differently from its high detail track, so one low sheet lies across parts
  of several high chunks and matches none of them.
- *cover the low sheet with the union of the high ones* -- they are only
  partial overlaps. A low sheet runs on past the high set onto ground no high
  mesh occupies, so dropping it leaves holes and keeping it flickers. No
  mesh-level rule can win that; only distance can.

The name-based pass and the coplanar pass both survive as fallbacks for the
21 meshes AC leaves unbounded.

Also worth knowing: AC's node matrices are row-major with the translation in
the **last row**, and a node inherits its parents', so the product runs child
first. Getting that backwards leaves every instanced prop at the origin,
where all 66 pit lane cones look perfectly coplanar with one another -- it
produced 338 "duplicate" pairs that did not exist.

## Reflectance: moved to rF2's own convention

All 75 official materials carry ambient and diffuse 1.0, with no variation.
We were writing AC's coefficients normalised against this track's upper
quartile, a 2.38x lift with the top 6 materials clamped at 1.0.

Measured against the albedo of 342 official textures, by share of drawn
triangles landing inside their p25-p75 band:

| | in band |
|---|---------|
| AC's ks x 2.38, clamped (what we shipped) | 71.3% |
| rF2 native 1.0/1.0                        | **85.2%** |

The materials it rescues are the ones that were reported wrong:

| material | effective albedo now | at 1.0 | official counterpart |
|----------|---------------------|--------|----------------------|
| `BBgrass`   | 42.6 | 71.5 | their grass 64.8 |
| `DB2X2_L01` canopies | 20.6 | 57.8 | their foliage 55 |
| `BBbushes`  | 25.5 | 71.5 | |

It costs the two materials whose AC texture is already brighter than rF2 ever
authors: `Trank_bark` and `concrete-barriers` go from 93 to 130. AC hides that
behind a low ksDiffuse and rF2 has nowhere to put it. The groove keeps AC's
own figure so the racing line stays dark.

Ruled out by measurement, do not retry: folding ks into the texture (works for
hard surfaces, collapses for foliage -- trees land at 9.7 against their 55),
and capping the effective albedo (there is no ceiling to cap to; official
albedo runs median 78, p75 115, max 255).

## Terrain: the wrong detail layer was being tiled

`splat-maps` is `ksMultilayer` with four detail layers blended by mask:

| layer | texture | AC weight |
|-------|---------|-----------|
| txDetailR | `Soil5.dds` | **multR 0.50** |
| txDetailB | `GrassDead0119...` | multB 0.15 |
| txDetailG | `Grass0117_1_L` | multG 0.07 |
| txDetailA | `terrain_asphalt` | multA 0.00 |

`single_detail` picked by mask coverage alone, which chose the dead grass on B
and dropped `Soil5` entirely -- dark dead grass tiled over the hills at 3.4 m.
AC's shader scales each layer by its own multX, so the pick is now coverage
times weight.

Note `laguna_seca_terrain_4k.dds` reads [43, 75, 115], blue dominant: it is
the base colour map of an aerial, not an albedo, and the mask is the separate
`laguna-seca-terrain-4k.dds`.

## Grass: what it actually is

`BBgrass` is **not** ground cover. Its face normals are entirely horizontal
(upward fraction 0.000): 316k triangles of upright billboards spread over
285,000 m2, with `BBbushes` another 40k on `ksTree`. Bounding boxes suggested
flat sheets and were wrong -- `upward_fraction` is the measure that holds.

So 191 is right for it and lowering the threshold would bring the green
panels straight back. What was wrong was the brightness (42.6 against their
64.8, fixed above) and that we drew it to the horizon when AC stops at 200 m,
which the LOD ranges now handle.

Still open if it does not look right: AC gives it one flat diffuse with no
normal map and no detail layer, where official grass is six textures on
`L2MULTIGRASS` (`Grass_Natural`, `Grass_Soil`, `Grass_Weeds`, a MULT and two
normals) with `L2SPECULARMAPT0XT1` for the verges. That is authored content we
cannot synthesise from one AC texture.

## The far mountains (not started, by the user's ordering)
One mesh: `Cylinder001`, material `horizont`, `horizont.dds` (2048x4096, lum
137.7), **192 tris**, radius 2812 m, always drawn, built by `backdrop.py`.

### Where the scene file gets its per-instance facts

`finalize_track` builds the scene from `gmt/exported.json`, which the geometry
stage writes -- so a new per-instance field added in `convert_track` reaches
the map but not the scene, and the first build after adding `lod_in`/`lod_out`
wrote no LOD keys at all despite every row carrying them. There is already a
join for exactly this (`render` is taken from the mapping rather than the
export record, so changing what is drawn needs no re-export); new fields have
to be added to that join. They are also recorded in `exported.json` now, but
the join is what the scene actually reads.

Check it the same way every time: `grep -cE 'LODOut=\([1-9]' <venue>.scn`
should count the instances that carry a real range, as distinct from the
collision shells closed off with `LODOut=(0.01)`.

## Pop-in: carrying AC's LOD ranges traded one fault for another

Carrying `lod_in`/`lod_out` across stopped the flicker and introduced obvious
pop-in, because AC fades between levels and rF2 switches hard. AC's own
numbers are brutal without a fade: trunks culled at **15 m**, canopies at 30,
tyre walls at 100, marshals at 150, grass at 200. 239 primary meshes vanished
within 300 m.

Now: a mesh with `lod_in > 0` only ever appears beyond that distance, so it is
the far stand-in for something already drawn from zero. Those 269 are dropped
and everything else is given no range at all -- one set of geometry drawn at
every distance. No switch to pop, no second copy to fight over pixels. The
eleven green billboard panels go too, since they are the only thing their
material draws.

Grass stops disappearing at 200 m as a side effect, which was the "it only
loads super close" complaint.

## Aiming reflectance at rF2's albedo band

A flat 1.0 everywhere was right for textures that are already rF2-ish and
wrong where AC's texture is much brighter and AC hides it behind a low
ksDiffuse. Measured effective albedos against official's p25 51 / median 78 /
p75 115:

| material | at 1.0 | aimed | what it is |
|----------|--------|-------|------------|
| `chrome` | 255.0 | 70 | the corkscrew buildings |
| `distanz` | 187.4 | 70 | distance boards |
| `metal_rust` | 165.6 | 70 | |
| `gstand_main` | 159.6 | 70 | grandstand seating |
| `altoparlante` | 154.8 | 70 | loudspeakers, 22k tris |
| `Trank_bark` | 130.1 | 70 | trunks |
| `concrete-barriers` | 129.9 | 70 | |
| `sbanc` | 115.1 | 70 | |
| `BBgrass` | 71.1 | 65 | their grass is 64.8 |

`factor = clamp(target / measured_albedo, 0.2, 1.0)`, with the albedo measured
in `bake_layers` on the shipping texture and stored as `albedo_lum`. Targets:
70 for an ordinary surface, 65 for cut-out foliage.

**What is exempt, and why the obvious test was wrong.** Ground keeps rF2's
plain 1.0. `track_surface` alone is no good as the test -- it is a
proximity-to-racing-line flag, so it also exempts the concrete barriers and
the rusted metal, which are exactly what was too bright. Flatness alone is no
good either: a grandstand's seating tiers face up as squarely as the road, and
`gstand_main` slipped through at 160 that way.

The test that holds is **decal, or flat AND (two stage OR track surface)**.
A two stage first stage is a base its detail modulates, not the final albedo,
so it must not be rescaled; and the markings are all one of decal or track
surface. That leaves road, curbs, markings, sand, gravel and terrain untouched
-- the surfaces already signed off -- and catches every upright structure.

`chrome` also had `ksDiffuse` 0.00, which AC means as "no diffuse, reflection
only"; our `float(...) or default` turned the literal zero into the default
and then native wrote 1.0, so it shipped at an albedo of 255.

## Terrain: a blended detail, not one layer of four

The hills reading as mud was my own doing. `splat-maps` blends four layers by
mask and rF2's second stage takes one, so picking by coverage tiled dead grass
over everything and picking by AC's weight tiled bare soil instead. Neither is
the terrain, which is soil AND grass AND dead grass.

`blend_details` now averages the layers in the proportion AC's shader sums
them -- the mask's coverage of each channel times that channel's `multX` --
and writes one detail texture. Laguna's terrain comes out Soil5 49%,
GrassDead 39%, Grass 12%. Uniform where AC's varies across the map, which is
the part one stage cannot express, but it is the right average and it reads as
ground rather than as whichever layer won. Several other materials improve
the same way (gravel is now Soil2 43% / Soil3 37% / Soil1 20%).

Worth recording against the original complaint: the terrain was **not** dark.
Its composed albedo measures 94.5, above official's `Grass_Soil` at 88.6 and
their median of 78, while the grass was 71.1. The hills were brighter than the
grass; what was wrong was colour and character, not brightness. So the fix was
the blend plus taking the grass down to 65, not lifting the terrain.

## Rubber contrast: a regression of mine, measured against the backup

The road did not get darker. Measured against `~/ac2rf2_backup` (the
2026-09-28 install with the signed-off "darker rubber"):

| | road rendered | rubber rendered | contrast |
|---|---|---|---|
| backup | 111.6 | 11.2 `[9 10 14]` | 10.0 : 1 |
| after the native move | 154.5 | 28.0 `[24 26 35]` | 5.5 : 1 |

The road went up 38%; the **rubber went up 2.5x**, diffuse 0.130 to 0.325,
which halved the contrast. `groove.dds` is itself blue (`[72 79 107]`); near
black that does not show, at 28 it does. The groove's exception was rewritten
wrong during the native move -- it was meant to keep AC's raw coefficient and
was given the old divide-by-upper-quartile lift. Back to raw: with today's
brighter road that is about 14:1, more than the version that was liked.

Lesson: when a user reports a surface "got darker", measure it against the
last version they approved before believing either of us. Here the perception
was real but the cause was the overlay, not the surface.

## Grass: the threshold stripped the blades (not upside down)

The user suspected it was upside down or cut in half. Rendering the atlas
over magenta at full alpha and at 191 settled it: the bushes survive 191
because their leaves are dense, but every thin grass tuft is stripped back to
the dense strip at its base -- "a rectangle of grass, not the middle part
higher". AC knew: `BBgrass` and `BBbushes` share `BBGRASS_D.dds` with 0.1 (26)
and 0.7 (178) respectively.

Orientation was checked and is fine. AC stores these V coordinates negative
(-0.999..-0.024) and relies on wrap addressing; our UV path is a linear flip
both ways with no clamp, and five cut-outs that already render correctly use
the same negative convention.

**The fix that makes AC's thresholds safe: coverage-preserving mips.**
`texconv -keepcoverage <ref>` rebuilds each mip so the share of texels passing
the threshold matches full size. Read back from the stored BC3 alpha blocks:

| | 2048 | 512 | 128 | 32 | 8 |
|---|---|---|---|---|---|
| AC's own mips @26 | 32.9% | 39.9% | 45.5% | 54.5% | **71.9%** |
| our copy @26 | 32.9% | 33.0% | 32.8% | 31.7% | 29.7% |

So 191 is retired as a workaround. Every hard cut-out now uses the threshold
AC authored it with, on its own copy (`<stem>_a<ref>.dds`) whose mips hold that
threshold -- one copy per texture and threshold, since coverage is preserved
for one at a time. Stored as `cutout_tex` in the map.

`bc3_alpha_mips` style decoding (header at 128, BC3 alpha block = two
endpoints then 16 three-bit indices) is the way to check this; simulating mips
by box-filtering the top level would not have shown whether texconv did it.

## Terrain: why "brighter than official" still read as mud

Two wrong turns before the right answer, both worth recording.

1. **multX is tiling, not weight.** I weighted the detail layers by
   coverage x multX and gave the soil 49%. `bake_material` already carries a
   comment recording this exact mistake being made and fixed before. Back to
   coverage alone.
2. **Neutral grain did not change the colour.** Our first stage already carries
   each layer's colour (the mask-painted low-frequency bake), so a coloured
   detail looked like a double application. Making the detail neutral grey did
   not move the composed average at all -- `[106 98 80]` either way -- because
   the per-channel compensation re-targets the base to the same colour. It is
   more correct and stays (off the racing surface only), but it was not the
   fix.

What was actually missing, measured against Joesville's terrain:

| | ours | official |
|---|---|---|
| grain contrast (std/mean) | 0.123 | 0.15 - 0.23 |
| normal map relief | flat, 0 deg | GRASS_NORM mean 5.1 deg |

Averaging four layer textures pixel by pixel cancels their grain against each
other (dead grass alone is 0.273). And with no normal map the hillside lit as
one smooth sheet. Now: grain contrast restored to the coverage-weighted
contrast of AC's own layers (0.262 on Laguna), and a tangent-space normal map
derived from that grain as a height field, wrap-around gradients so it tiles,
scaled until its mean tilt is Joesville's 5.1 degrees. Carried as
`two_stage[...]["detail_nm"]` and fed to `sBump` on UV_D.

Only off-track painted surfaces get this (the terrain and `sbanc`). The curbs,
gravel and asphalt variants are painted too but were signed off as they are.

## Round of 2026-10-05: what I broke, and the corrected approach

The previous round changed too many things in one build and two of them broke
work that had been signed off. Recording the mistakes as plainly as the fixes.

### Comparisons that ignored the scene light

I told the user the road had got *brighter* (material 111.6 -> 154.5). It had
got darker on screen, because the scene light fell at the same time:

| | ambient | sun | fog |
|---|---|---|---|
| backup (signed off) | 237 | 245 | starts 2 km |
| now | 126 | 220 | starts 50 m |

Lit horizontal surface, road on screen: backup 157.3, last build 143.0.
**Always compare on-screen values (albedo x scene light), never material
values alone, and never across builds with different scene files.**

### Rubber contrast is capped by opacity, not diffuse

`groove.dds` is 22% opaque on average, 46% at most, and rF2 blends it. So the
rubber darkens the road by 1.25x on average however dark its diffuse -- equal
in the backup and now. Lowering diffuse from 0.325 to 0.130 changed nothing
visible, which I had predicted would quadruple the contrast. Now the rubber
has its own copy at twice the opacity and grey (the texture is blue), and the
road under it (found by letting each rubber sample vote for the surface
beneath it: only `asphalt_norm`) is lifted 1.10 to restore exactly the 157:

| | typical | heaviest |
|---|---|---|
| before | 1.26 | 1.53 |
| now | **1.64** | **3.22** |

### Cut-outs: neither threshold works alone

- At 191 (rF2's convention) AC's textures lose their soft content: every fence
  panel's chain-link mesh disappears outright (fences keeps 49% of what AC
  draws), privacy screens go to speckle, grass blades strip to their base.
  This had been true since the 191 build and nobody noticed because the green
  panels were the bigger problem.
- At AC's own thresholds the canopies and bushes went see-through. Most
  likely because the same build turned on linear filtering (0x10) for the
  cut-outs for the first time: bilinear alpha erodes every leaf toward its
  core at a high threshold like 178. Every earlier, point-sampled build drew
  them solid.

The approach that satisfies both: keep the test at **191**, **remap alpha** so
that whatever AC draws at its own threshold lands at 191 and above, rebuild
mips **holding coverage at 191**, and **point sample** cut-outs. Checked at
native resolution, texel for texel, our copy at 191 against AC's original at
its own threshold: grass 99.97% identical, fences 99.85%, canopies 99.93%.
Stored mip coverage holds flat (grass 32.9 -> ~32 where AC's own mips fill in
to 72%).

Two measurement traps hit while checking this:
- resampling a texture to 512 px to "compare shapes" filters its alpha and
  invents a mismatch; compare at native size;
- whole-texture coverage is meaningless when two materials share an atlas.

### Walls: measure where the triangles sample, not the whole atlas

The reflectance target used the mean of the whole texture. A wall that uses
one bright corner of a large atlas averages dark, so it was never corrected:
`bridge-coopertires` averages 34 over its atlas and 89 where it is drawn.
`convert_track` now records up to 1500 triangle-centre UVs per material
(`uv_samples`, wrapped into the texture) and `bake_layers` measures the albedo
there. Caught: pit garages, containers/tents, the Red Bull and media
buildings, bridges, gazebo, marshal posts -- all 83 to 104 on screen, now 70.

### Process

One fix per symptom, each verified on the actual output (decoded mips,
native-resolution renders, on-screen values with the scene light) before the
hour-long build. When the user reports something got worse, measure it
against the last version they approved -- including the scene file.

## Agenda for the next session (read-only findings, nothing changed)

### 1. Rubber: put it back exactly as it was
The user wants the rubber as before and only the road brighter. Revert the
`RUBBER_OPACITY` grey copy (`rubber_tex`) -- groove back to `groove.dds` /
`tyres_add2.dds` at AC's raw coefficient -- and keep `ROAD_LIFT` on
`asphalt_norm`. The doubled opacity read as "artificially dark".

### 2. THE MISSING LAYER: CSP, which the user runs in AC
`assettocorsa/extension/config/tracks/loaded/ks_laguna_seca.ini` (807 lines,
v5, 2020) changes what AC shows, and the converter has never read it.

**`[GRASS_FX] GRASS_MATERIALS = splat-maps`** -- CSP draws procedural 3D grass
over the whole terrain at runtime (`MASK_MAIN_THRESHOLD = 0.1`,
`SHAPE_SIZE = 5`). That is the grassy ground in AC. It is not in the kn5, so in
rF2 the terrain shows bare with only the sparse `BBgrass` billboards on it:
"bright fresh grass growing on mud" is literally that. No texture or
reflectance fix on the terrain could have reproduced it, which is why every
attempt left it looking the same.

**Summer `MATERIAL_ADJUSTMENT`s** (`CONDITION = SEASON_SUMMER`) override the
kn5 coefficients:

| material | kn5 kd / ka | CSP summer kd / ka |
|---|---|---|
| `splat?` (terrain) | 0.60 / 0.70 | **0.72 / 0.40** |
| `BBgrass?` | 0.25 / 0.30 | **0.20 / 0.20** |
| `DB2X2?, Trank?` | 0.15-0.30 | **0.10 / 0.15** |
| `tree?, bush?, bark?, BBbush?` | | 0.20 / 0.20 |
| `gravel` | 0.35 / 0.40 | 0.42 / 0.35 |
| `asphalt?` | 0.38 / 0.42 | 0.42 / 0.35 |
| `sbanc` | 0.55 / 0.70 | 0.80 / 0.45 |

So in the user's AC the terrain has ~3.6x the grass's diffuse; in our build
they are near parity (1.0 vs 0.91). CSP darkens all vegetation and lifts the
terrain.

Also: `[LIGHTING] SPECULAR_MULT = 0.15` (track specular cut to 15%),
`[BOUNCED_LIGHT]` on buildings and vehicles, `Material_Horizon` with
`LocalContrast = 1.5, FogMultiplier = 2` (relevant to the far mountains),
and `TRACK_MAP` naming walls (`concrete-barriers, tyres`) and buildings.

Options to decide with the user:
- **read CSP's track config generically** in `convert_track` and apply the
  active `MATERIAL_ADJUSTMENT`s (summer) to the kn5 props before conversion --
  generic across every AC track with a CSP config, and it is the AC the user
  actually compares against;
- **emulate GrassFX**: rF2 has no procedural grass, so either generate grass
  billboard geometry over the terrain where the mask/threshold says grass
  (faithful, heavy), or bake a greener, grassier look into the terrain base
  where GrassFX would cover it (cheap, flat);
- at minimum, take CSP's grass/terrain balance so the billboards stop
  standing out against the ground.

### 3. Walls (pit garages especially), and white trucks
`Pitbox` (64k tris) is already corrected (diffuse 0.66, drawn albedo 105.6 ->
70) and still reads far too bright. The target brings the material's
*average* to 70, but a garage texture mixes dark doors and interiors with
white walls, so the white parts stay well above it. Vertical walls facing the
sun also get N.L ~0.87 against the ground's 0.5. Look at a high percentile of
the drawn texels rather than the mean for upright surfaces, and compare
against AC's own (CSP-adjusted) relative balance. `Vehicles1` (white trucks,
103.5 -> 70) is the same case and lower priority.

### Do not repeat
- compare on-screen values with the scene light, against the last approved
  build, scene file included;
- one change per symptom, verified on the output before the hour-long build.

## 2026-10-05 (2): CSP read generically; walls by their bright part; rubber back

- **Rubber**: as AC ships it again (no copy). The 2x opacity grey copy raised
  the measured contrast but read as artificially dark. Only `ROAD_LIFT` on
  `asphalt_norm` remains, which is what was asked for.
- **CSP**: `convert_track.csp_adjustments` reads
  `extension/config/tracks/loaded/<track>.ini` (and the per-track
  `extension/ext_config.ini`), takes every `MATERIAL_ADJUSTMENT` that is
  unconditional or `SEASON_SUMMER`, matches CSP's `?` wildcard, and stores the
  values as `props["csp_ksDiffuse"]` / `["csp_ksAmbient"]`. The exporter
  applies the ratio to our factor **only where CSP darkens and only off the
  ground**: grass x0.80 / ambient x0.67, canopies x0.67 / x0.50, trunks
  x0.33 / x0.50, `tree_set_1` x0.91 / x0.50, bushes and grandstand ambient.
  Where CSP brightens (terrain, asphalt, gravel, grandstand diffuse) it is
  left out for now.
- **Terrain, not changed, and why**: CSP gives it kd 0.72 (vs 0.60) but ka
  0.40 (vs 0.70). Under our scene light (ambient 126, sun 110 on flat ground)
  that nets out about 14% *darker*, so CSP does not explain the bright rocks in
  AC. The big terrain difference is CSP's `GRASS_FX`, still open.
- **Walls**: upright opaque surfaces now aim the brightest tenth of their
  drawn texels (`albedo_p90`) at 70, not the average. Pitbox whites 104 -> 70
  (average 47), white trucks 163 -> 70 (average 30, may overshoot),
  `Bld_pitgarage` 104 -> 70. Cut-outs keep the average target plus CSP.

## 2026-10-10: relative to the road, not to the kn5; the horizon as a cut-out

### "Some grass is right, some isn't"
`BBgrass` and `BBbushes` sample the same atlas and shipped at diffuse 0.589
and 0.925. CSP gives both 0.20, so in AC they match. The rule "apply CSP only
where it darkens against the kn5" skipped the bushes, because 0.20 is above
the kn5's 0.15. Comparing CSP against the kn5 is the wrong frame.

**The right frame is relative to the road** (the signed-off surface, found as
the one the rubber lies on). AC lights by texture x coefficient, so a
material's factor is its coefficient over the road's, times the road's lift:
grass and bushes 0.524 / 0.629, canopies and trunks 0.262 / 0.471, tree
cut-outs 0.524 / 0.629. Applied to vegetation CSP configures (cut-outs, or
coefficient below the road's), off the ground.

### Terrain: ~40% too dark since the native move
Relative to the road, AC lights the terrain far harder: CSP 0.72 / 0.40
against the road's 0.42 / 0.35 (kn5: 0.60 / 0.70 against 0.38 / 0.42). Under
our light (ambient 126, sun 110 on flat ground) that is 1.41x the road per
unit albedo. Native 1.0 gave parity and the old scheme clamped to the same
result, so the hills have never had it -- the "mud", the dull rocks. Diffuse
cannot exceed 1.0, so the terrain base is lifted 1.41 x the road's 1.10 =
**1.55**: mean [107 99 80] -> [165 153 124], dried dirt; rocks (brightest
1%) [229 208 205]; 0.01% of texels clip. Off-track ground with CSP figures.

My earlier claim that CSP nets the terrain 14% *darker* compared CSP with the
kn5. Against the road it is the opposite.

### Horizon: the white band above the ridge
`horizont.dds` is four panorama strips; each strip's sky is stored as pale
blue-white [176 208 238] with alpha 0. The backdrop shipped on `L2DIFFUSET0`,
blend 2/1, no colour key, and `backdrop.py` cut the sky out by deleting
transparent triangles on a coarse 4x4-block grid -- written before the alpha
test flag was known, as its own docstring says. Triangles straddling the ridge
stayed whole and drew the stored sky colour: the white band.

Now the backdrop is a cut-out like the trees (bump shader, colour key, 191 on
a remapped copy `horizont_a128.dds` with coverage-preserving mips, point
sampled). It stays opaque, so it writes depth and sorts behind everything --
the old "mountains in front of everything" came from *blending* it. The
geometric clip still runs and only removes fully clear triangles.

Checked before building: the cylinder maps texture-top to cylinder-top (each
of four segments shows the upper half of its strip), and at the up-facing
edges the texture is clean -- crisp alpha, mountain colour directly under the
sky, a 1 px pale fringe at most. The pale band visible in a render of the
strip lies in the half the cylinder never displays.

## 2026-10: first tracks beyond Laguna (Spa, Silverstone GP)

What a second and third track exposed, all generic:

- **Blender crashed on Spa** at mesh 1151/1728 (`EXCEPTION_ACCESS_VIOLATION` in
  `UI_popup_menu_end`). The exporter add-on reports a mesh's geometry issues
  with `WindowManager.popup_menu`; in `--background` there is no window and
  Blender dies. `blender_stage.silence_popups()` replaces it and prints the
  popup's text instead. Spa needs re-running.
- **Multi-layout tracks**: models in `models_<layout>.ini`, data/ai in
  `<track>/<layout>/`. `convert_track.layout_files()` is the one place that
  knows this; `--layout` runs through build_track, convert_track, make_aiw
  and make_cam, and the output is named `<track>_<layout>`. Repeated model
  entries load once.
- **Not yet supported**: `POSITION=` / `ROTATION=` on a model in models*.ini.
  Reported as a WARNING; the objects would sit at the origin. Highlands'
  drift layout has one (`100.kn5`), so it waits on this.
- **Untextured materials / logic markers**: Silverstone's `AC_AUDIO_*` carry
  a bare 3ds Max material with no texture, and exporting them wrote `sTex0`
  as a filename -- the scene-load fault. Meshes that are neither drawn nor
  collidable are no longer exported at all (587 on Silverstone, mostly the
  far LODs already dropped for pop-in), and any untextured material gets
  `_white.dds`. `verify_install` caught this before the track was loaded.
- `--zip` writes `out/<track>/<track>_rf2.zip`, unzips straight into
  `ModDev/Locations`. `convert.bat` is drag-and-drop and asks for a layout.
- Spa's rubber vote picked three surfaces (asph, carpet, kerb_new), so the
  road lift also touches its kerbs and carpet. Silverstone picked one.

## 2026-10-10: the normals bug, and one brightness frame for every track

User report on Silverstone: glass bright blue and opaque, stand ceilings and
their posts far too bright, every white thing blown out, grass far too bright,
ground grass a bit too bright, road texture repeat more visible than in AC.

### Every upright surface was lit as if it faced the sky (root cause)
`blender_stage.build_mesh` set the mesh property `Normals = 2`. The addon's
`process_polygon` (rF2_GMT_Export.pyc, disassembled with Python 3.10's `dis`)
picks the vertex normal by that property:

| Normals | written | measured (probe_normals.py, wall facing AC +X / floor) |
|---|---|---|
| '0' | `loop.normal` (split normals, custom ones included) | -1,0,0 ok / 0,1,0 ok |
| '1' | polygon face normal, Y/Z not swapped | -1,0,0 ok / 0,0,1 WRONG |
| else | constant (0,0,1) -> straight up | 0,1,0 WRONG / 0,1,0 |

So every wall, ceiling, post and truck side on every track we have built was
lit like flat ground. The old note "Normals=1 points the wrong way, 2 matches"
was measured on ground faces only, where "up" happens to be right. All the
albedo-ceiling work on walls, seats, white trucks and tree trunks was
compensating for this. Now 0.

### AC's authored normals were thrown away
Blender rebuilt normals from the winding. Measured with the kn5 normals
(scratchpad normals_cmp.py): Silverstone's 1.38M grass billboard triangles
carry normals straight up, 90 deg from their faces on 100% of them; crowds
the same; trees > 60 deg off on 48%. `kn5.py` now reads normals,
`split_node` carries them, `build_mesh` sets them as custom split normals,
and mode 0 writes them (probe: a wall with AC "up" normals comes out 0,1,0).

### One brightness frame, anchored on Laguna's road
Per-track road anchoring hid that CSP draws Silverstone's asphalt at
0.15/0.25 vs Laguna's 0.42/0.35: on screen 36 vs 54, so Silverstone's road
(and all vegetation tied to it) came out ~1.9x too bright vs AC. Now every
material: fd = kd / 0.42 * ROAD_LIFT, fa = ka / 0.35 * ROAD_LIFT (CSP values
where present), divided by whatever lift the bake already put in the texture
(road: ROAD_LIFT; lifted terrain writes 1.0 as signed off). Upright opaque and
non-vegetation cut-outs: min(frame, old albedo ceiling) -- never brighter than
before, darker where AC says (glass 0.05/0.10 -> 0.14/0.29 instead of 0.62).
Vegetation (ksTree/ksGrass, or CSP-configured cut-outs): the frame, no
ceiling. Groove: AC's raw value as signed off. On Laguna the anchor is its own
road, so road, terrain and vegetation are unchanged by the frame.

Caveat to check in the sim: CSP's per-track "grasstree fix" values for
ksTree/ksGrass can be extreme (Silverstone trees 0.05/0.03, Spa bbgrass
kd 0.0). Laguna's 0.20/0.20 is the only one signed off.

### CSP config missing at conversion time
CSP downloads a track's config into extension/config/tracks/loaded the first
time the track is loaded in AC. Silverstone had never been loaded with CSP
when it was converted, so it got no CSP at all (trees written at 1.0). Now a
WARNING, repeated at the end of the build.

### CSP model replacement (not needed for Silverstone)
Silverstone's config hides 5 glass objects and inserts silverstoneGlass.kn5:
same geometry, same values (opaque, kd 0.05 ka 0.10), renamed so CSP can
light the windows at night. Nothing to gain by converting it.

### Spa
Five backdrops failed to export: the old geometric sky cut multiplied them
50-250x past 65536 vertices. It is redundant when the backdrop is a cut-out
(colour key trims per pixel) and is now skipped then. Two of the five were
not backdrops at all but the racing line rubber (groove1/groove2, radius
~1350 m because they follow the lap): backdrop now excludes decals.

### models.ini POSITION/ROTATION
Applied (kn5.placement_matrix). ROTATION[0] is a heading about Y: Highlands
drift's start gantry (100.kn5, -17) lands 3.3 deg off the road heading under
it with this sign, 37 deg with the other. Pitch/roll have no stock example:
warned, not applied.

## 2026-10-10 (later): repeat, grass, shadows, ranges, seasons

User report after Silverstone/Spa/Highlands in sim: asphalt pattern visibly
repeats when driving straight (least at Highlands); grass too bright on every
track; Spa grass shows as squares filled with dark blue; Spa pops far away and
the rubber vanishes for a few seconds then returns; Highlands' big rocks far
too bright (AC darker, bluish).

**Road repeat -- AC's multX are UV tiling, not layer strength.** The second
stage tiled every detail every 2 m. AC samples a detail at meshUV x multR..A
(ksMultilayer) or x detailUVMultiplier (NMDetail). Evidence: CSP's
materials_pbr.ini (DetailNMMult "UV multiplier"; parallax variant picked by
whether MultR..A are equal, meaningful only for UV scales; `_multGR` ratio),
and values like 150 / 4200 on Spa buildings. Measured AC repeat vs ours:

| track | material | AC repeat | ours was |
|---|---|---|---|
| Silverstone | asphalt (multR 1.0) | 43.7 x 132.5 m | 2 x 2 m |
| Spa | asph (multR 0.8) | 12.9 x 95.4 m | 2 x 2 m |
| Laguna | asphalt_norm (0.8) | 214 x 15 m | 2 x 2 m |
| Highlands | Road (detailUV 14) | 0.8 x 6.1 m | 2 x 2 m |

Highlands is the one AC already repeats finely, which is why it looked right.
`bake_layers.ac_detail_tiling` now gives uv_b = AC's multiplier (highest
non-zero among layers carrying the chosen texture; all zero -> 0.001, i.e.
flat as in AC). Grains blended here (no AC figure) keep the 2 m rule.
`strength()` in the bake still reads multX as a weight; the Laguna terrain
blend was signed off on that and is left alone.

**CSP conditions are blends, not switches.** Spa's config is seasonal:
SEASON_SUMMER is a LUT over YEAR_PROGRESS that peaks at 0.7 and sits ~0.5 all
summer; CSP sets OFF + (VALUE-OFF) x weight. We took VALUE outright, so Spa's
bbgrass got ksDiffuse 0.0 / ksAmbient 0.07 (lit by blue sky alone) where AC
shows ~0.10 / 0.16. Now every SEASON_* condition with a YEAR_PROGRESS LUT is
evaluated at RACE_YEAR_PROGRESS 0.5 (July 1). Side effects: Silverstone trees
0.05/0.03 -> 0.144/0.18; Highlands `costone` (the big rocks) now gets its
SEASON_MUD figures 0.185/0.195 instead of the kn5's 0.23/0.25.

**Spa grass squares.** bbgrass is ksPerPixelAT, ref 0.5, but its alpha has a
soft ramp so `cutout_ref` called it a gradient and drew the card whole. The
gradient rule exists for ground blends (Laguna gravel_brd); upright (upward <
0.5) gradients now get the hard cut AC gives them.

**No shadow casters at all.** Our .scn never set ShadowCaster; Loch Drummond
sets it on 385 instances, (Static, Solid) or (Static, Texture) for cut-outs.
So no roof shaded its seating, no tree its grass, no rock itself. Now from
AC's per-mesh cast_shadows flag (`finalize_track.shadow_caster`), skipping
hidden, blended, backdrop, decal and flat (upward >= 0.9) meshes.

**Pop-in / vanishing rubber: the exporter's default range.** The add-on
writes LOD_Out = 1000.0 into every gmt (rF2_Utilities.set_gmt_defaults /
InitCustomProperties) and we never set it. rF2 culls by distance to the mesh
centre; Spa's rubber (Loft286/Object697) is 1.35 km in radius, so it dropped
out whenever its centre was >1 km away. build_mesh now sets LOD_Out = 13000
(the far clip) + the mesh's radius on the empty and the mesh.

**Grass darker, by intent.** User asked for it even if artificial. Rationale:
CSP GrassFX covers the [GRASS_FX] GRASS_MATERIALS ground with shaded blades in
AC; rF2 has nothing like it. Grass cards (vegetation with AC up-normals) x0.50
(GRASS_CARD_DIM); GrassFX ground x0.40 (GRASS_GROUND_DIM) only where the
surface's mean colour (base x detail mean, for two stage) is green-dominant
(sand/gravel are on those lists too). First pass used 0.70/0.85 and measured
the two-stage base alone, which is near white, so the ground was never dimmed
and the season blend left Silverstone grass at 0.91/0.43 against the 0.47/0.24
the user had already called too bright. The constants are anchored to that
feedback (each track's grass darker than the build judged), not measured --
tune them if needed.

### Correction (2026-10-11): AC's multiplier stretched every detail

Applying AC's multX as one UV factor for both axes stretched every road,
sand and grass detail along the track by the mesh's UV anisotropy (measured
per-triangle: Silverstone asphalt 43.6 x 130.9 m per UV, 3.0:1; Spa asph and
Highlands Road 7.2-7.6:1; Highlands grass_near 26:1). The user saw it at once.
Whatever AC does, it does not show the grain smeared, so the second stage is
square again. `repeat_metres`: AC's repeat on the shorter axis, never finer
than the old 2 m and never coarser than 128 detail texels per metre (8 m for
a 1024, 16 m for a 2048); uv clamp back to the old [1, 512]. Result: asphalt
at Silverstone/Spa/Laguna repeats every 8 m (was 2), Highlands road stays 2 m,
buildings stay 2 m.

## 2026-10-11: specular mask, road detail one mip down, darker grass

- AC masks specular by txDiffuse alpha where there is no txMaps; rF2 got a
  flat spec map at AC's full figure. Silverstone grass ksSpecular 1.0 with
  alpha mean 0.23 (sand-bordini 0.26, Spa sand 0.30): ~4x AC's shine, read as
  "fluorescent". `spec_mask` (bake) scales the written specular; roads barely
  move (their figure was clamped at 1 anyway).
- Road repeat visible only near the car, ending at a sharp line (user): the
  detail's mip 0 band (1024 texels per 2 m = 2 mm, 20-60x finer than AC shows
  it). Track-surface details now ship at half size (`*_half.dds`), so the
  near band shows what was drawn beyond the line. Hypothesis under test.
- Grass dims 0.50/0.40 -> 0.35/0.30 ("still too fluorescent").
- Built with --hour 17:30 (GDB session starts). Clouds are an in-game
  weather setting, not a track file.

### The near-car band: the detail NORMAL map's tiling (2026-10-11)

Screenshots (Silverstone, 7): coloured glitter (blue/white/orange specks) on
the asphalt for ~10-15 m in front of the car, smooth beyond and smooth in the
mirrors. Compared with Highlands, where the user saw it least:

| track | road normal map | specular |
|---|---|---|
| Silverstone asphalt | txDetailNM tarmac-detail5_NM2, tiled with the detail at 2 m | 2.2 x mask 0.41 |
| Spa asph | same texture, same tiling | 3.0 x 0.47 -> 1.0 |
| Laguna asphalt_norm | tarmac_detail_NM_B, same tiling | 0.02 x 4 (tiny) |
| Highlands Road | flat_NM.dds (txNormal) | 4.0, nothing to catch |

AC's txDetailNM is on the mesh UVs (CSP's Kunos-multilayer replica: "mapped
with UV1" x DetailNMMult, default 1), not the detail's 2 m tiling: bumps 20-60x
too dense, glittering under specular until the mips flatten them. Now AC's
txDetailNM keeps the base mapping; only bake-derived grain normals tile with
their detail. The half-size road detail (HALVE_ROAD_DETAIL) is switched off --
it was the wrong hypothesis. Grass cards 0.35 -> 0.25.

### Same day, next test: caustics, and grass that ignores material figures

- txDetailNM on the mesh UVs: metre-wide blobs reading as frozen water
  caustics (user screenshot 20261011230622). Neither mapping matches AC, so
  AC's txDetailNM is now dropped on two stage surfaces (txNormal or flat, as
  Highlands' road always had). Bake-derived grain normals still tile.
- Grass cards: installed KSBB_HI001_KSLAYER5.gmt carries amb 0.146 / dif
  0.068 (was 0.41/0.24) and the user saw no change. rF2 lights mostly from its
  sky (IBL) onto the texture; its own content keeps material figures at 1.0.
  Lever moved to the texture: grass cards' cut-out copies are written with
  RGB x GRASS_CARD_TEXTURE (0.5), `*_a<ref>_d50.dds`. Grass card = cut-out
  vegetation under 1 m tall with up normals or an AT/ksGrass shader
  (`is_grass_card`; pines and hedges have up normals too, hence the height).

### The near band, measured: detail contrast (2026-10-12)

Flat normal map tried in sim: glare gone, band still there -> reverted to the
2 m tiled txDetailNM. Contrast (luminance std/mean) per mip, box-filtered:

| detail | m0 | m2 | m4 |
|---|---|---|---|
| Silverstone tarmac-detail5 (1024^2) | 0.52 | 0.36 | 0.16 |
| Spa tarmac-detail6 (1024^2) | 0.53 | 0.32 | 0.13 |
| Laguna tarmac_detail_B (1024^2) | 0.31 | 0.21 | 0.08 |
| Highlands Tarmac_5D_A (1024x4096) | 0.34 | 0.27 | 0.11 |

The band is the near region where the detail is still at full contrast;
Highlands' is 4x denser along the road, so its band sits near the wheels
(user's observation). Driving-surface details above DETAIL_MAX_CONTRAST 0.34
are written as `*_soft.dds`, scaled toward their per-channel mean (mean
unchanged, so the base pre-scale holds). Grass card texture 0.5 -> 0.75.
- Final choice (user: "as much like AC as possible"): asphalt under the rubber
  gets AC's exact tiling (uv_b = multR on both axes, as AC applies it); sand
  and grass keep 2 m. SOFTEN_DETAIL off (it had flattened the terrain grass).

## 2026-10-12: AC's exact asphalt tiling reverted; detail softened instead
Silverstone asphalt has multR 1, so AC's tiling spread tarmac-detail5 (and its
normal map) over 44 x 132 m: huge stretched stones with the sky glinting off
them. Back to the signed-off 2 m. The near-car band is handled by softening
the detail's contrast to 0.34 (Highlands/Laguna level), now applied only to
the asphalt under the rubber, so the terrain grass is untouched.
Softening alone left the band exactly as visible (user, same day): it scales
every mip equally, so the drop between mips is unchanged. Decoding the stored
mips showed it: tarmac-detail5 is 0.52 0.55 0.48 0.21 0.05 (std/mean, mip 0-4),
a cliff at mip 2->3. Now the asphalt detail is rewritten with an even-contrast
chain (even_mip_detail: 0.28 through mip 3, then x0.75 per mip).
Grass cards x0.875. Silverstone at 19:00 (sunset) for testing.
Even mips made the band MORE visible (user): grain held further out is the
problem, not the cliff. Reverted (EVEN_MIPS = False). Now matching Highlands on
both measured quantities: contrast 0.34 (uniform softening) and density --
Highlands packs 4 copies of its detail per 2 m tile along the road, a 0.5 m
repeat, and its band sits under the wheels. Asphalt detail now every 0.5 m
(ROAD_DETAIL_METRES); its normal map stays at 2 m via two_stage uv_nm. 18:30.
Road had no sun glare: every material without txMaps got _flat_spec.dds,
which is BLACK, so the asphalt's specular was zeroed. The asphalt under the
rubber now gets AC's actual mask (txDiffuse alpha, mean 0.41) as its spec map
(road_spec_map -> two_stage["spec"]), and spec_mask is not applied on top.
Grass cards x0.8.

## 2026-10-31: builds run side by side (--jobs)
Task Manager showed Blender and Python at 8% each on a 12-thread CPU: one core.
Measured on Spa (13 min one at a time): steps 1-3 3.5 min, AI line and
cameras 0.5 min, Blender 9 min (70%), finalize 1 s.
- texconv is single threaded: a 4096 BC3 with -keepcoverage took 16.1 s of CPU
  in 14.9 s; four at once finished in 16 s instead of ~60. In bake_layers 140
  of 172 s (Laguna, profiled) was waiting on texconv, 97 s of it the 12
  cut-out copies. Those and the darkened copies, and fix_textures' per-file
  conversions, now run in a pool (parallel.ordered_map), each job in its own
  scratch folder (Laguna's trees go out at alpha 51 and 77 from one source,
  and the helpers name temporaries after the source). Results are recorded in
  the original order, so material_map.json and the log are unchanged.
- Blender: N processes (--shard i/N). Every one walks every mesh, so names and
  order are a single run's, and exports a share chosen greedily by measured
  cost: 0.08-0.14 s per mesh plus 1.2-2.4 s per 10k triangles (fitted to the
  gmt timestamps of Spa, Silverstone and Nagao), i.e. a mesh weighs its
  triangles + 700. Each writes to its own folder, because the stage finds what
  the exporter wrote by diffing its output folder. build_track merges them in
  single-run order. Reading the models in every Blender costs 10.5 s on Spa.
- Memory: the first try took six Blenders to 3.8 GB each and the machine to
  0.2 GB free. kn5 decoded every vertex into Python tuples (~12x the file),
  and a finished model stayed alive (parent/child cycles wait for the cycle
  collector): all ten Laguna files at once, 3.3 GB. Geometry is now decoded on
  first use (kn5._lazy, identical values on all 17 Laguna and Nagao files,
  Nagao's unfold included) and blender_stage frees each model with
  gc.collect(). Now 1.6 GB per Blender (Laguna), 1.4 (Spa). default_jobs caps
  jobs at free memory / 2.5 GB.
- Result, 6 jobs: Laguna 14.5 -> 6.9 min (Blender 684 -> 236 s), Spa 13 -> 4.5
  min. Textures, material map, scene, GDB, AIW, cameras: byte identical. A few
  gmts differ (Laguna 3-4 of 1124, Spa 8 of 1393), in the last bit of some
  tangents and in a 3-float vertex field that holds garbage (NaN neighbours,
  -3e19, 1e-45) in the single-run file itself: the exporter reads memory it
  never wrote on degenerate vertices. Two single runs of Laguna differ in the
  same way (bld_tower, toilettes, vehicles), so it is not the split.
- --jobs 1 runs the old path: one Blender, no shard, conversions one by one.

## 2026-10-31: parallel builds checked on three more tracks; setup check
- Silverstone gp 15 -> 4.9 min, Highlands drift 11 -> 4.8, Nagao uphill 12 ->
  6.0, each compared with the single-Blender build of the same code. Everything
  but the gmts is byte identical. Nagao: all 6738 gmts identical too.
  Silverstone: 4 gmts differ, only in the normal and padding words of
  degenerate vertices, which hold garbage (denormals, -1e18) in the
  single-Blender file already. Highlands: the four pub_lod2_* meshes differ in
  500-700 words each (normals, tangents). A second single-Blender run differs
  from the first in the same four files by the same amount, and the 961 other
  gmts it wrote are identical, so it is the exporter, not the split.
- The rF2 Blender add-on does not come with rF2: Support\Tools\Plugins holds
  only the 3ds Max plugins. It is a download from the Studio-397 forum thread
  "Blender rFactor2 Export Scripts" (io_rf2_gmt_release_2400309.zip, 24.3.9),
  compiled for Python 3.10 (cpython-310 .pyc), so Blender 4.1+ cannot load it.
  The README said it shipped with rF2.
- Without --layout, a track whose layouts all live in models_<name>.ini (no
  models.ini, no ai\ folder: Silverstone, Highlands, Nagao) fell back to
  <track>.kn5 alone (layout_models), and a mistyped --layout did the same,
  silently. convert.bat offered Enter for "the default" on exactly those
  tracks. check_setup.py now refuses both, with the layout list.
- convert.bat printed "Done. Installed" whatever build_track returned; it now
  checks the exit code. A missing NumPy, Blender or add-on used to fail at
  step 3 or 6, minutes in; check_setup.py finds them in ~3.5 s (it asks
  Blender itself to enable the add-on, wherever that Blender keeps it).
- Steam's own folder comes from HKCU\Software\Valve\Steam\SteamPath (stored
  lower case; realpath gives the real case), so a Steam installed off
  C:\Program Files (x86) is found. --rf2 / --ac (AC2RF2_RF2_DIR /
  AC2RF2_AC_DIR) name a game folder outright.

## 2026-10-31: technical review fixes and Blender 5.2 migration

### Measurements before the changes

- All 170 installed stock KN5 files use version 6. 49 files across Barcelona,
  Brands Hatch, Nordschleife and Red Bull Ring have a nonzero extra header
  integer. Barcelona 1.kn5 stores 912125, Brands Hatch 1.kn5 781233, and
  Nordschleife 2.kn5 673425. The old reader and both texture scanners treated
  these values as payload lengths and failed with out-of-bounds reads.
  AcTools consumes the integer only, then reads the texture count:
  https://github.com/gro-ove/actools/blob/master/AcTools/Kn5File/Kn5Basic.cs
- Names are not identities. Laguna has two bushesO nodes with tree_set_1 and
  BBbushes materials. Spa has two D nodes with metals1 and trees2. Spa also
  declares asph_pitlane_old (plain shader) and asph-pitlane-old (multilayer),
  which sanitized to the same material name. 99 rendered Laguna rows differed
  from the first definition selected for their shared rF2 material name.
- Laguna merged ROAD (.970), ASPHNEW (.990), RDOLD (.940), PITS (.965) and
  other surfaces into road_PHYSICS. The generated road block used .965 for
  all of them. SAND and GRAVEL also shared one material and grip block.
- A valid skinned-node fixture failed because flags precede the bone table,
  and skinned nodes have no static-mesh bounding-sphere/renderable tail.
- A verifier fixture containing one correct cutout, another bound to the
  wrong texture, and a missing scene GMT returned zero and "all checks
  passed". A failed texture-conversion subprocess likewise returned zero.
  An installation copy failure deleted the previous venue and returned
  normally. These cases are now reproducible regression tests.
- A targeted bake of Laguna gravel_brd classifies its texture as a gradient,
  while the source row is alpha_test=True and needs_blend=True. The exporter
  previously excluded that row from both cutout and blend paths.

### Changes and measurements after the changes

The v6 integer is now consumed without skipping data in all three readers.
All 170 installed stock KN5 files now parse to exactly their file size,
including all 49 nonzero-header files. Synthetic skinned fixtures also leave
following sibling nodes aligned and retain their vertex normals.

Mapping schema 2 identifies a mesh by model/traversal ordinal, and a material
by its complete declared definition. Sanitization is followed by a stable
signature; physical materials additionally carry a distinct AC surface
prefix. Geometry measurement tables, baked albedo sampling, export records,
scene joins and verification use these identities too. Old geometry must be
rebuilt; --skip-geometry rejects records without the new chunk manifest.

Fresh mapping runs against the installed stock assets produced:

| track | unique mesh IDs | distinct rF2 materials | physical surface blocks |
|---|---:|---:|---:|
| Laguna | 1603 | 122 | 17 |
| Silverstone GP | 1959 | 92 | 16 |
| Spa | 1728 | 116 | 21 |

Every generated material name mapped to exactly one source definition and
surface prefix. Every physical surface prefix had exactly one matching TDF
block. Blocks clone the native surface behavior and retain each AC key's own
friction and track validity. In particular ROAD=.970, ASPHNEW=.990 and
RDOLD=.940 remain separate. No converted content is committed.

Geometry exports now record the chunk index/count and source identity, reject
missing/truncated files and duplicate names, and fail the build on an export
exception. Parent and finalization stages check the complete manifest before
staging. Verification checks scene references, all expected cutouts, timing
records, and required GDB/AIW/TDF files. Installation copies to a sibling first
and rolls back if publication fails; copy/publication failures are tested.

Rendering policy now distinguishes opaque, cutout and blended materials using
the bake's resolved classification. Zero coefficients remain zero. CSP's
ksSpecular overrides and LIGHTING/SPECULAR_MULT are retained (measured Laguna
multiplier .15, Silverstone/Spa 1.0). These are semantic corrections, not new
brightness or detail-density tuning. The near-car road band is still open.

### Important correction: exporter blend enums are not zero-based

The old code's 4/5 assumption was itself wrong for the current vendor release.
Read with xdis from the vendor's Blender 5.0 archive: InitCustomProperties
registers d3dBlendArray as Zero='1', One='2', Src Alpha='5', Inv Src Alpha='6'.
Put_rF2_Materials reads the RNA Blend_Source_List/Blend_Destination_List
attributes. BlendUpdate also copies the Blend Boolean to Flag_0x00000020.
The adapter now enables/disables Blend through RNA, then resolves factors by
the RNA enum labels rather than guessing numeric IDs or writing ignored custom
keys. Cutouts use One/Zero; gradients use Src Alpha/Inv Src Alpha. Adapter
policy is regression tested; resulting GMT bytes need the compatible exporter
and an in-game check described below.

### Blender 5.2, Python configuration, and remaining validation limit

The project now targets Blender 5.2 or newer and uses its custom-normal API
without the removed use_auto_smooth property. A real headless Blender 5.2.3
smoke test builds a mesh and checks its authored custom normals, four UV sets,
scaled detail UVs, and extended draw range, without an exporter add-on.

The installed Blender 5.2.3 embeds Python 3.13.13. The author's current
"Blender 5.0 plus" release (R25.11.27), linked from the updated forum post,
contains Python 3.11 .pyc files (magic a70d0d0a); importing it in 5.2.3 was
measured to fail with ImportError: bad magic number. The previous 3.6 exporter
was also bytecode-only, for Python 3.10. Source or a Python 3.13 build is
required; renaming the bytecode is not a compatibility fix. The archive was
examined locally under ignored out/_tools and is not redistributed.
https://forum.studio-397.com/index.php?threads/blender-rfactor2-export-scripts.74821/

Setup now reports this exact dependency failure before a build. Full GMT
export, serialized material behavior, driving tests, and resolution of the
near-car band have NOT been verified with Blender 5.2. The compatible-exporter
follow-up and requested README reduction are tracked in WORK_ITEMS.md (the
fork has GitHub Issues disabled).

A standard .venv and pyproject.toml provide NumPy as a runtime dependency,
pytest as a development extra, and executable ac2rf2/ac2rf2-check/ac2rf2-verify
commands after Command Prompt activation and pip install -e ".[dev]".
The regression suite uses generated fixtures, not redistributed game assets.

Final local validation: 22 regression tests pass, including the real Blender
5.2.3 geometry smoke test. pip check reports no broken requirements. A fresh
1024-cap Laguna bake (asphalt_norm, gravel_brd, BBgrass, BBbushes; jobs=2)
succeeds with signature-based names. Resolved modes are opaque, blend, cutout,
cutout respectively; grass/bush thresholds remain 26/178 remapped to 191.
The new CI workflow runs the fixture suite on Windows/Python 3.10 and 3.14;
Blender is optional there. CI results are separate from the local measurements.

## 2026-10-31: working portable Blender 5.0 conversion route

This supersedes the previous tooling blocker for conversion. Blender 5.2 remains
installed, but the tested export pair is portable Blender 5.0.1 (Python 3.11.13)
and the rFactor2 IO Group community exporter R25.11.27 (io_rfactor2_gmt).
Both import and addon registration succeed. The project now accepts Blender
5.0+, preferring the tested portable pair; 5.2 still needs a compatible exporter.

ac2rf2-tools downloads the official portable ZIP plus the author's exporter ZIP
into ignored .tools/, verifies pinned SHA256 checksums, and prepares a project-
local add-on path. It does not change the system Blender installation. Blender
archive SHA256 (also checked against the official release manifest):
921d77f6c505a35b2c2f6e67d4ad1c10b72418338ba0e0d3ea7f582a5e5fe46e.
Exporter archive SHA256:
295b676408c607b4c6cfc7f0fa8b5ce573c0a6fcdfc3151bc1c2ac6afa2877d7.

### Actual exporter interface, measured before a complete build

A first four-material export failed at the old template-parent check: the newer
add-on exposes File_Name as RNA and the parent has no custom ID keys. A direct
probe also showed its default material has Shader_Name='Invalid'. Therefore the
converter now explicitly creates L2DIFFUSET0 as its plain shader template and
sets File_Name, Normals, material colours, specular power and Fresnel values
through their actual RNA properties. Mesh Normals is the enum string '0'
(Smooth/custom), with '1'=Face and '2'=Up; writing a custom key is insufficient.

Five GMTs from a targeted Laguna export completed: asphalt, gravel_brd,
BBbushes, and both chunks of the selected BBgrass mesh. Read back from those
files, the gravel border has blend factors 5/6 and material flags 0x68902023;
opaque asphalt/cutouts have 2/1 and 0x68902003. Source/destination factors are
the two uint32s at shader-name offsets -16/-12. Foliage diffuse textures have
colour-key flags 0x88 and alpha reference 191. Material values also arrive:
gravel_brd ambient .8171428/diffuse .6809524; bush .6285714/.5238096; grass
.1571429/.1309524. These are binary checks, not a claim about the rendered look.

A new real-exporter regression test uses generated geometry and three materials.
It reads back ambient .2, diffuse .4, factors 2/1 (opaque/cutout) or 5/6 (blend),
and cutout reference 191 with colour key set. It also verifies a custom diagonal
normal distinct from both the face normal and constant up. Blender's packed
custom-normal round trip showed about 4e-5 error, so the test uses a 1e-4
component tolerance. All 25 local regression tests pass, including actual
Blender 5.0 GMT serialization and the separate 5.2 geometry smoke test.

The community exporter is a third-party add-on, not a Blender or Studio 397
component. Its compiled Python version constrains which Blender can run it;
this is why installing an arbitrary newer Blender alone does not solve export.

### Full stock Laguna Seca build and staged verification

A complete --jobs 4 build of the installed stock ks_laguna_seca completed all
seven stages with the portable pair. It ran from an ignored frozen source copy
(out/_runtime_source) to avoid changing modules during the build. Source scan:
1603 meshes, 244 physical meshes, 122 material definitions, 17 surface blocks,
216 embedded textures. Texture conversion reported 23 converted, zero failed.
The staged location contains 1124 GMTs (247 collidable), 275 textures, 592 AI
waypoints over 3553.2 m, 24 grid/pit positions, and 41 cameras.

ac2rf2-verify against the staged location returned zero (all checks passed):
- 1124 GMTs checked and zero missing textures.
- 196 alpha-tested GMTs checked: zero wrong thresholds, zero missing colour key,
  zero alpha-tested materials on shaders that cannot test alpha.
- 157 upright meshes checked: zero lit as though all normals point straight up.
- Zero GMTs retaining the exporter's default 1000 m draw range; 723 shadow casters.
- Export contracts, required location files, timing strips and hidden export
  checks passed. Of 806 source meshes marked hidden, 247 hidden instances were
  exported; non-rendered, non-collidable meshes are deliberately omitted.

One declared-surface warning remains: physical mesh RDGRAVEL008 matches no AC
surface key and uses the documented plain-road fallback. No track-specific
exception was added. The staged output is under
out/_runtime_source/out/ks_laguna_seca/rf2/ks_laguna_seca and was NOT installed
over the game's Developer Mode location. No game assets are committed.

Setup checks pass for Python 3.14.7, NumPy 2.5.4, both Steam game paths, Blender
5.0.1 and exporter R25.11.27; pip check finds no broken requirements. These
measurements validate serialized files, not the rendered appearance. A fixed
camera/time/weather comparison in rF2 against AC+CSP is still required for the
near-car road band and any remaining lighting or texture defects. See
docs/VALIDATION.md for the concrete next steps.

## 2026-10-31: source format validation and parser hardening

### Failure measurements before the change

Generated probes showed the previous reader accepting a KN5 header declaring
version 7 while interpreting it as version 6, accepting 22 unexplained bytes
after a complete KN5 node tree, and returning an empty racing line for AI
version 8. The latter silently selected generated-path behavior. Short strings
and skipped payloads were not checked at their point of consumption. The
texture scanners duplicated the KN5 prefix layout.

Before enforcing EOF rules, 42 installed stock KN5s were scanned across Laguna
Seca (10), Highlands (13), Silverstone (13), and Spa (6). All declared version 6
and consumed the entire file; none had trailing bytes. Nine stock racing lines
all declared version 7 and had matching point/extra counts and spatial grids.
Their valid data after the main points ranged from 729004 to 6692444 bytes;
rejecting all data after the position table would break these tracks.
The installed stock drift track has exactly 12 bytes representing three int32s
(3, 0, 0). This is an explicitly empty older-format stub, not an arbitrary
short-file exemption. The handling is generic and does not inspect track names.

### Implemented contract

source_formats.Reader checks every read/skip and derives count bounds from
remaining file bytes and minimum record size. SourceFormatError identifies the
file, binary format/version, record context, and byte offset. KN5 accepts only
versions 5 and 6; the header and texture table are shared by the model reader,
alpha scanner, and extractor. The full reader rejects unexplained trailing
bytes, invalid modes/booleans, ambiguous definitions, non-triangle index counts,
invalid vertex/material references, and non-finite consumed geometry/material
values. This validation also runs with lazy decoding or geometry=False.
Nesting above 256 parent levels is rejected explicitly (stock maximum: 3).
NumPy views validate geometry without decoding it into large Python lists.

Both AI consumers now use the same version-7 reader. It validates all main
20-byte records, matching extras and their full 72-byte records, and the
optional grid's nested counts/lengths before requiring EOF. Missing files,
complete empty v7 files, and the exact empty v3 stub permit generated-line
fallback; present empty representations warn. Other present unsupported,
zero-length, or truncated AI files fail. Unused extra fields and grid references
are bounds-checked but their values are not interpreted.

Recognized model/surface/camera INI records now validate required keys, finite
numbers and vector shapes; missing declared models and requested layout lists
fail instead of silently dropping geometry. Existing optional surface defaults
remain, and unknown INI sections/keys remain compatible. Binary names use
strict UTF-8; INI also accepts a BOM. Unsupported encodings fail rather than
silently replacing bytes. Unknown source shaders warn that the generic mapping
is an unverified approximation; this does not change material rendering policy.
Texture extraction also rejects output path separators and drive syntax.
See docs/FORMATS.md for the supported layouts and extension policy.

### Validation measurements

All 99 local regression cases pass (74 new cases), including the real Blender
5.0 exporter and Blender 5.2 geometry smoke tests. The generated KN5 fixture is
571 bytes and the grid-bearing AI fixture is 352 bytes. Every truncation from
zero through one byte short is rejected with SourceFormatError: 923 truncation
positions exercised. Cases cover unknown versions, bad counts/references,
non-finite geometry, duplicate definitions, invalid text and required INI fields,
valid extra sections, short headings, explicit empty AI and unsupported shaders.
A pipeline regression confirms that unsupported KN5 input stops before later
stages/export/install and leaves an existing location sentinel unchanged.
pip check reports no broken requirements.

Compared with the previous committed readers (f3e7fe1), the installed four-track
sample preserves all decoded model metadata/materials, all 1055 embedded texture
payloads byte-for-byte, all 31765 points across nine racing lines, and all 514
camera records. Nine model/layout INIs also validate. The combined old/new
comparison took 8.348 seconds locally; this is an observed validation run, not a
performance guarantee. All nine spatial grids are consumed exactly.

A fresh Laguna Seca source conversion with --textures completed: 1603 meshes,
244 physical, 122 material variants, 17 surface blocks and 216 extracted
textures. The existing unmatched RDGRAVEL008 surface warning remains. No game
location was replaced and no game assets are committed. Parser checks do not
constitute an in-game visual sign-off or prove every possible CSP/image format.
A semantic change that preserves the binary version can still require new
measurements and explicit support.

### Format references checked

The upstream AcTools reader describes the KN5 prefix, 44/76-byte vertices,
material modes and node tails. Its AI reader and structures describe the
20-byte points, 72-byte extras, and nested spatial grid. The measured stock
files agree with these layouts. References were read at AcTools commit
e5e5c94b8dee7511def0b670bfd5dbb233831c11:

- https://github.com/gro-ove/actools/blob/e5e5c94b8dee7511def0b670bfd5dbb233831c11/AcTools/Kn5File/Kn5Basic.cs
- https://github.com/gro-ove/actools/blob/e5e5c94b8dee7511def0b670bfd5dbb233831c11/AcTools/AiFile/AiSpline.cs
- https://github.com/gro-ove/actools/blob/e5e5c94b8dee7511def0b670bfd5dbb233831c11/AcTools/AiFile/AiPointExtra.cs
- https://github.com/gro-ove/actools/blob/e5e5c94b8dee7511def0b670bfd5dbb233831c11/AcTools/AiFile/AiSplineGrid.cs

## 2026-10-31: repeatable conversion/install/Developer Mode workflow

### Launch measurements before choosing the script's behavior

After the missing-track report, process inspection showed the regular
Bin64/rFactor2.exe running with +path=".." +workshopsync, and no Mod Mode
process. ModDev/UserData had no player profile yet. The installed location had
the expected layout/GDB and matched the staged file inventory.

A Launcher/Launch rFactor.exe +modmode attempt did not leave a running game
process here. Launching Bin64/rFactor2 Mod Mode.exe directly with the rFactor 2
root as its working directory and +trace=2 did leave the actual Mod Mode process
running (PID 35296 in that probe), created ModDev/UserData/player, and produced
a trace reporting HOT_RELOAD against ModDev. Its AllCarsTracks.cch subsequently
contained TrackName=ks_laguna_seca and the converted location path. This probe
occurred BEFORE the user's later instruction to leave final manual testing to
them; no new game launches were performed after that instruction.

This agrees with Studio 397's documented executable and Start In directory:
https://docs.studio-397.com/display/DG/Developer%2BMode . A bare executable launch
is insufficient evidence of entering Developer Mode, so the new launcher checks
the sustained identity/path of the actual Mod Mode process, excluding CEF
renderer children. Regular-game redirection, early exit and timeout are failures.

### Commands and lifecycle

The new pure-Python drive_track.py / installed ac2rf2-test command handles
preflight, sequential track/layout batches, conversion, staged verification,
installation, and optional Developer Mode launch. It accepts AC track names or
paths, inline TRACK::LAYOUT, --layout, and --all-layouts. Conversion parameters
are shared with build_track.py rather than maintained as two option lists.
--out-root is forwarded all the way into the initial source conversion.
--install-only uses completed artifacts; --launch-only runs the launch step;
--no-launch leaves the game stopped for manual testing; --dry-run prints a plan.

By default an existing game/launcher blocks updates. --restart-game requests
normal window shutdown, and only the additional --force-close permits killing
remaining detected processes in this installation. Neither Steam itself nor
other installations are closed. A per-game file lock excludes concurrent test
workflows from other workspaces. Finalization rechecks that the game is stopped
before verification and again immediately before replacing the location.
A failed target prevents launch; previous successful targets in the batch remain
installed. The existing rollback-on-install-failure behavior is retained.

psutil is declared as a runtime dependency (7.2.2 installed locally), installed
with the normal activated-venv pip command. The project wheel builds and pip
check reports no broken requirements. Game binaries remain external and no
converted assets are committed. docs/TESTING.md documents the options, exact
working directory, first-time Dev profile setup, and manual selection of a track.

### Regression validation

The initial complete suite passes 128 cases (29 new workflow cases), including
the real Blender exporter/geometry probes. Workflow tests cover multi-target
ordering and one final launch, failure preventing later targets/launch, complete
preflight before shutdown, install-only without source/Blender, dry-run with no
process/file effects, layout expansion/deduplication/output collisions, argument
validation, lock exclusion/release, scoped process identification, explicit
shutdown/force behavior, wrong-game detection, early-exit timeout, and forwarding
custom output paths into source conversion. Launch tests use simulated processes
and do not start the user's game.

### Completed real conversion/install run, without launching the game

After the user requested manual testing, the original automatic-launch supervisor
was stopped and validation was restarted explicitly as:

    ac2rf2-test ks_laguna_seca --jobs 4 --no-launch

The command returned zero after all seven build stages, verification and install.
It wrote the normal project out/ks_laguna_seca build (no frozen-source path is
needed for future iterations), exported 1124 GMTs with four Blenders, staged
275 textures, and installed ModDev/Locations/ks_laguna_seca. Verification found
zero missing textures; 196 correct alpha-tested GMTs with colour key and suitable
shaders; 157 upright meshes checked with none incorrectly lit straight up; zero
1000 m default draw ranges; and 723 shadow casters. AI has 592 waypoints over
3553.2 m with 24 grid/pit slots; 41 cameras were generated. The preexisting
RDGRAVEL008 unmatched-surface warning remains.

Post-install comparison found the same inventory/sizes for all 1404 staged and
installed files, matching scene/database/AI/camera/terrain content hashes, and
zero running game/launcher processes. A real two-target dry-run also resolved
ks_laguna_seca and ks_silverstone::gp to the right Steam folders, output names,
layout argument and Developer Mode destination, without changing processes.
All 128 regression cases pass after the final CLI checks. The source-format and
real Blender tests remain included. Launch/restart regression tests simulate
processes; the user retains the final in-game visual test.

## 2026-11-01: standard src package layout and clean repository root

### Baseline and migration

The previous layout had 27 Python files at the repository root: 24 runtime
modules plus three standalone probes. Normal subprocesses launched bare .py
filenames relative to that root; Blender injected it into sys.path; portable
tooling defaults were relative to the module file. Simply moving the files
would therefore break stage execution and tool discovery.

Application code now lives in src/ac_to_rf2, using qualified package imports and
Python -m subprocesses. A small packaged blender_entry.py supplies Blender's
separate interpreter with the correct import root. project_paths.py separates
installed code from writable files: editable checkouts retain their original
out/ and .tools/ defaults even from another current directory; wheel installs
use the caller's directory, with AC2RF2_WORKSPACE as an explicit override.
AC2RF2_TOOLS_DIR and --out-root continue to work.

All five ac2rf2* console command names are preserved. Root-file Python invocations
become console commands or python -m ac_to_rf2.<module>; python -m ac_to_rf2
also runs the main converter. The retained root convert.bat activates the local
standard .venv when needed and invokes the package, with CRLF preserved.
Probes moved to tools/probes with their path references updated.

Detailed notes and work items moved into docs/. The root README was reduced from
305 to 64 lines, with its complete previous guide preserved as docs/USAGE.md.
The requested README work item is marked complete. docs/DEVELOPMENT.md documents
the layout, source-command migration, package builds, workspace rules and tests.
There are zero root-level Python files; application sources, tests, diagnostics
and documentation have separate directories. No source game data was moved.

### Blender / wheel ABI regression measured and fixed

Blender 5.0.1's Python 3.11 starts without NumPy preloaded. Prepending this
project's Python 3.14 site-packages made it select NumPy 2.5.4's cp314 extension
and fail with ImportError (no numpy._core._multiarray_umath). This would affect a
wheel's Blender entry even though an editable src checkout worked.

The Blender bootstrap and setup probe now append the package import root after
Blender's own libraries, preserving its bundled NumPy. The entry also rejects
an already-importable conflicting ac_to_rf2 package instead of using stale code.
A new regression copies the package into a wheel-style site-packages directory,
places a deliberately failing foreign NumPy beside it, and runs the actual
Blender entry on a generated KN5/map/DDS. The test failed before the change
with 'foreign virtualenv NumPy was loaded' and now exports a valid GMT. The
existing actual-exporter colour/blend/alpha/custom-normal and Blender 5.2 API
smoke tests also still pass. No binary dependencies were copied into Blender.

### Functionality and distribution validation

All 138 local cases pass (128 previous cases plus 10 package-layout cases).
New checks cover unrelated-directory module commands, the verifier, editable
workspace defaults, explicit workspace overrides, wheel-style writable defaults,
and the real Blender/wheel import boundary. pip check reports no broken
requirements; ac2rf2-check still finds Blender 5.0.1 and exporter R25.11.27.

Both wheel and source distributions build. tools/check_distribution.py installs
the wheel in a fresh virtual environment, removes checkout import-path overrides,
loads all five installed entry points, runs command help outside the checkout,
checks that output/tool defaults point outside site-packages, and rebuilds a
wheel from the source archive. It rejects stale flat modules in the wheel and
checks that the sdist includes source, docs, tests, probes and the batch launcher,
while excluding out/, .venv/ and .tools/. CI now performs these checks on both
Windows/Python 3.10 and 3.14. Python packaging follows the documented src layout:
https://packaging.python.org/en/latest/tutorials/packaging-projects/ and
https://setuptools.pypa.io/en/latest/userguide/package_discovery.html .

A full stock Laguna build using the packaged stages and four Blender workers
completed all seven steps into out/_layout_validation/ks_laguna_seca. It did NOT
install over the user's location or launch the game. It produced 1124 GMTs,
275 textures, 592 waypoints over 3553.2 m, 24 grid/pit slots and 41 cameras.
Subsequent ac2rf2-verify returned zero: no missing textures, 196 correct cutout
checks, 157 upright meshes with no constant-up error, no default 1000 m ranges,
and 723 shadow casters. The existing RDGRAVEL008 source-surface warning remains.

Compared with the previous completed out/ks_laguna_seca build, all 280 non-GMT
layout files (275 textures plus scene/database/AI/camera/terrain) are byte
identical. material_map.json is also byte identical. GMTs retain the previously
documented exporter nondeterminism, so their meaningful contracts were verified
instead of claiming byte equality. Rendering/material translation was not tuned.


## Developer Mode loading warning: AIW type and connection defects (2026-11-01)

The user's trace_2026_11_01_09_20_59-31.txt records 'No pit box waypoints
found' at 70.48 s (line 10493), grid/pit waypoint resets at 77.48 s
(line 10524), four missing Skip Barber sound samples at 81.09-81.26 s
(lines 10814-10817), then onFatalError 11 at 117.51 s (line 12297).
The trace establishes a native crash after those warnings; it does not establish
that a particular warning caused the crash. Earlier notes claiming that merely
adding untyped pit stubs prevented the crash were too strong.

### Measured AIW defect and correction

The installed old Laguna AIW declared 24 PitPos records, 592 main-path points,
24 pit-lane points, and 48 nonpath stubs (664 total). None of its WP_PTRS
fourth fields identified a pit box. The main entry incorrectly used type 1,
the pit lane incorrectly used type 0, and pit stubs used team ordinals 0-23.
No lane branch pointed into those pit stubs, and grid waypoint pairs were absent.
A nonempty AIW previously passed verification despite these defects.

Primary format evidence is the bundled ModDev location data, not a guessed
number: Joesville has 15 pit positions and 30 nonpath waypoints with matching
branchID and WP_PTRS type 106-120; both Loch Drummond layouts have 20 pit
positions and 40 matching waypoints of types 106-125. All three encode main
points as type 0, pit lane as type 1, grid locations as 2+i, and pit locations
as 106+i. Location endpoints have self next links and separate approach points;
the path's third pointer connects to the approach. All three native AIWs pass
the new validator. Studio 397's AI tutorial also requires joining pit branches
and generating location connections:
https://docs.studio-397.com/display/DG/Track+AI+Tutorial .

The generic writer now emits the measured types, matching nonpath flags,
connected grid/pit pairs and both pit-lane joins. Shared nearest anchors retain
all incoming location branches through a branch chain. Missing connected pit
lanes now stop generation instead of emitting unusable fallback locations.
AIW serialization is separated from source extraction for synthetic regressions.
Generation and installation validate record count, finite positions, pointer
bounds, type/branch/flag consistency, the reciprocal main loop, graph reachability,
and typed pit pairs at each declared PitPos. Grid pairs are required for each
declared grid slot. This validates file structure, not AI driving quality.

Laguna's regenerated AIW has 712 points: 592 main, 24 lane, 48 grid and 48 pit.
All 24 grid slots and pit boxes have connected pairs. Its SHA-256 is
970d36eac7fbb75f9274d34103287564f1aa9b03889629ffe3b5d8ca29116d66 in both
out/_layout_validation/ks_laguna_seca and the installed ModDev location.
The 1404 staged/installed file paths and sizes match; AIW/SCN/GDB/CAM bytes match.
sectors.json matches the prior build exactly, so timing geometry was not changed.
The existing 1124 GMTs and 275 textures pass the complete installation verifier.
Only AI data was regenerated; materials and geometry were not rebuilt or tuned.

### Separate vehicle-audio findings and remaining manual test

The four missing samples are referenced by the bundled
ModDev/Vehicles/SkipBarber/skipbarber_snd.json: Skip_TC_in.wav,
Caterham_in_shift.wav, Caterham_ext_startup.wav, and Skip_TC_ext.wav.
The trace mounts Vehicles/SkipBarber/SkipBarber_Sounds.mas. Inspection using
the installed official Support/Tools/MAS2.exe shows 83 entries in that
27,105,288-byte archive and none of these four names. It contains the separate
skipb_in_shift.wav and skipb_ex_startup.wav names. This is a bundled vehicle
configuration/archive mismatch independent of the converter's track output.
No vehicle files or audio samples have been substituted.

A second archive at ModDev/Sounds/SkipBarber/SkipBarber_Sounds.mas is
27,633,737 bytes; the official MAS utility reports 'Unknown MAS key' when
opening it. This utility error alone does not establish corruption. Its contents were not
inferred, extracted or bypassed. Copying it
over the mounted archive is not a verified repair. Steam file verification or
an SDK update is the appropriate next check if the stock vehicle warning
persists. The corrected AIW has not been driven: no game was launched during
this change, and the native crash is NOT yet proven resolved. For isolation,
first manually test stock Skip Barber on bundled Joesville with zero AI, then
the converted Laguna with zero AI, then add AI and test pit entry/exit.

### Launcher and regression checks

Root launch_dev_mode.bat activates the checkout's standard .venv, changes to
the repository directory, delegates to the existing launch-only module, forwards
options and retains nonzero failures with a visible pause. It remains CRLF and
is included in the source distribution. Dry-run from an unrelated directory
passed; missing .venv and invalid rF2 path cases returned 1 without launching.
The launch message now explicitly confirms only a running Developer Mode
process; it does not claim the vehicle/track loaded or rendered successfully.

149 local tests pass, including 11 added cases for AIW types, shared anchors,
missing pit markers, disconnected branches, invalid indices/counts/coordinates,
PitPos mismatch and installation rejection of nonempty invalid AIW files.
Wheel/sdist builds and the isolated distribution checker pass. The regression
suite does not automate native rFactor 2 gameplay or assert crash resolution.


## Skip Barber audio workaround and crash follow-up (2026-11-02)

The latest completed trace is trace_2026_11_01_10_10_51-31.txt (794,491 bytes).
It loads ks_laguna_seca and ten vehicle slots (player plus nine AI). Unlike the
09:20 trace, it has no missing-pit-box warning and no grid/pit waypoint reset.
The four vehicle-audio warnings remain at 54.04-54.18 s. The log ends at 127.40 s
in AssignPitAndGarage during session restart, with a partial last line. There is
no new onFatalError line, normal shutdown sequence or newer rFMini.dmp. This
cannot establish whether the latest process was terminated externally or failed
without flushing its log. No game was launched to reproduce it.

The existing ModDev/UserData/rFMini.dmp is from the EARLIER 09:22 crash. Its
exception stream records 0xc0000005, a write to address zero, at executable
RVA 0x7003cb. Captured memory at the instruction is `mov dword ptr [0], 5`,
a deliberate null-address write, consistent with the logged onFatalError 11
termination path. This dump identifies the fatal termination, not its initiating
cause. It does not establish that the audio warning caused the crash; no such
claim is made. No newer crash dump or matching Windows Application Error event
was found during the follow-up.

### Verified sources for the four missing samples

The official MAS2 utility successfully exported the 83 entries of
ModDev/Vehicles/SkipBarber/SkipBarber_Sounds.mas into ignored
out/_maintenance/skipbarber-export. The separate Sounds/SkipBarber archive was
not reopened. Extraction did not change the readable archive's SHA-256:
c5acfbd69f26fe665cc42e87435e67ef2041056759b16dfae2c595818e802fce.
The original skipbarber_snd.json is also unchanged:
d8f704ed1603a44584e654f7a96dda7e702d25ca2f9c346407e76becc41f4d55.

The configuration's external shiftUp/shiftDown events reference the absent
Caterham_in_shift.wav (two references) and its external starting event references
Caterham_ext_startup.wav. The same archive provides working Skip Barber shift
and startup recordings. The absent Skip_TC_in/ext names occur in tractionControl
loop events; the base game's Secondary directory provides real tc_in/ex samples.
All four replacement sources are mono, uncompressed 16-bit PCM, with complete
frame payloads. These are existing game recordings, not generated silence.

| Requested loose filename under vehicle/sounds | Existing source | Bytes | Sample rate | Frames |
|---|---|---:|---:|---:|
| Skip_TC_in.wav | ModDev/Sounds/Secondary/tc_in.wav | 179916 | 44100 Hz | 89919 |
| Caterham_in_shift.wav | extracted skipb_in_shift.wav | 39852 | 44100 Hz | 18025 |
| Caterham_ext_startup.wav | extracted skipb_ex_startup.wav | 421900 | 48000 Hz | 209471 |
| Skip_TC_ext.wav | ModDev/Sounds/Secondary/tc_ex.wav | 148242 | 44100 Hz | 74082 |

Studio 397 explicitly supports loose samples relative to the ModDev vehicle
directory, with 16-bit PCM WAV officially supported:
https://docs.studio-397.com/display/DG/Using+the+new+sound+engine .
Four aliases (789910 total bytes) were installed under
ModDev/Vehicles/SkipBarber/sounds using this documented lookup mechanism.
This is a local SDK audio workaround using equivalent event recordings, not
recovery of the unknown original Caterham/Skip_TC assets or an official SDK fix.
The installed hashes equal their respective source hashes. No JSON, MAS,
vehicle physics, selected track, graphics or controller settings were changed.
The four missing referenced paths now resolve on disk; actual game lookup and
crash behavior remain subject to manual testing.

### Reversible tooling and validation

The generic ac_to_rf2.sound_aliases module accepts a JSON plan containing rf2,
vehicle, sound_config and target-to-source aliases. Its default mode checks only.
It checks declared sample references and full 16-bit WAV payloads, refuses existing
files with different bytes, checks that rFactor is stopped, uses exclusive file
creation and records ownership and hashes in an external receipt. Failed receipt
creation rolls back newly created aliases. Undo checks all owned-file hashes
before removing any and preserves files that existed before installation.
No track-specific behavior or sound assets are included in the package.

Local plan: out/_maintenance/skipbarber-audio-plan.json.
Ownership receipt: out/_maintenance/skipbarber-audio-receipt.json.
Original sound JSON copy: out/_maintenance/skipbarber_snd.original.json.
Reproduction, source preparation and removal commands are in docs/AUDIO.md.
The 13 new regressions cover real WAV validation, missing declarations, path
escapes, conflicts, a running game, rollback, dry-run and ownership-safe removal.

For the next manual test, select Skip Barber on bundled Joesville with ZERO AI,
then converted Laguna with ZERO AI. Check that the four file warnings disappear
and that a practice session enters the world. Only then add AI. Preserve the
resulting trace and any new rFMini.dmp if a failure remains. This separates the
bundled vehicle's loading from converted AI/path initialization without claiming
the native crash has already been fixed.

Full local suite: 162 tests pass. Wheel/sdist and isolated module-command checks
are included in the distribution validation. Native gameplay was not run.
