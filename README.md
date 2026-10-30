# 3D Print Studio — Blender add-on

A Blender add-on that turns 3D-print models into photorealistic "already printed" renders:
real sliced layer geometry at true scale, slicer-accurate top/bottom skin, printer flaws,
a filament palette, scanned photo textures and ready-made rooms and props.
Requires Blender 4.2+ (tested with 5.2).

![Orange PLA Benchy, 0.2 mm layers, 1:1 scale](docs/images/benchy_orange.jpg)

| 100 % crop | Desk scene | Top layer test |
|---|---|---|
| ![](docs/images/benchy_orange_100pct.jpg) | ![](docs/images/desk_scene.jpg) | ![](docs/images/top_layer_test.jpg) |

## Installation

1. Build the zip with Blender's own Python:
   `"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/package.py`
   → creates `dist/print3d_studio-1.0.0.zip`.
2. Blender → *Edit > Preferences > Get Extensions* → ▾ in the top right → **Install from Disk…** → pick the zip.
3. In the 3D Viewport press **N** → **3D Print** tab.

To try it during development without installing:

```bash
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --python tools/dev_start.py
```

## Quick start

1. Import your STL/3MF model and select it.
2. **One-Click Scene** → the model is scaled from millimeters to real size, sliced into
   real layers and given the filament material; a room, desk and decor (cutting mat, lamp,
   spool, plant, books, mug) are built, the model is set on the mat, and lighting, a product
   camera and Cycles are configured. The viewport switches to the camera.
3. **Render > Render Image** (F12).

## Panels

| Panel | Contents |
|---|---|
| Print & Filament | Type / Color, Layer Height, Line Width, **Direction** (print orientation: Z+/Z-/X/Y/Custom Angle), Layer Visibility, Layer Irregularity, Seam, Top Surface Lines, Real Layer Geometry, Print Imperfections, Dust & Handling, Color Cycle Height. Changes apply live. |
| Material Library | Wood (incl. scanned photo woods), metal, stone, fabric, leather, glass, ceramic, walls/floors, cutting mat, PEI… Every material comes with its own surface relief (bump). |
| Room & Environment | Room built to size (walls/floor, window, ceiling, baseboard) or a curved studio backdrop. |
| Props | Desk, coffee table, chair, bookshelf, wall shelf, books (cover + page block), desk lamp (real light), succulent, mug, pen cup, cutting mat, PEI build plate, filament spool, laptop, rug, picture frame + your own asset library. |
| Lighting & Camera | Daylight (Window), Golden Hour, Studio, Evening, HDRI. Product camera: focus, aperture (bokeh), angle, roll. |
| Render | Preview / Final / Ultra, social-media sizes, GPU, Lens Effects. |
| Extend Palette | Permanently add new filament colors and materials. |

## How the realism works

### Real layer geometry
- **Real Layer Geometry** (on by default): like a slicer, the model is cut at the middle of
  every layer and rebuilt one layer height thick (`scene/slicer.py`). Sloped tops become real
  terraces (a 5.5° roof at 0.2 mm gives ~2 mm steps) and silhouettes become real stair steps.
- The original mesh is kept; turn the option off to get it back (e.g. to edit the model).
- Benchy at 0.2 mm: 240 layers, ~16 s to slice.
- On non-manifold meshes, open contours are bridged across gaps up to 5 layer heights.
- Layer caps are watertight: the perimeter band and infill share vertices, and points added
  while splitting triangles are welded into neighbouring faces, so no hairline cracks show.

### Surface rule (like a slicer)
Every cap face is classified (`p3d_skin` attribute):
- **Top skin** where nothing is printed above it: two perimeter loops along the outline, then
  45° infill alternating per layer. The true distance from the outline is stored per face
  corner (`p3d_edge`) and narrows on thin walls.
- **Bottom skin** where nothing is printed below it (overhangs): sagging, matte lines.
- **Bed side** for the first layer: pressed flat and glossy.
- Ledges narrower than ~0.25 mm (≈ 0.6 line widths) and covered faces get no skin, so the
  micro steps that Z wobble leaves on walls stay clean.
- Cap triangles that straddle the exposed/covered border are bisected along their longest
  edge until the class is clear.

### Lines and printer flaws
- Layer lines are computed at real scale (bump distance = one real layer, no exaggeration).
  They become visible in close-ups and at 2K+ resolution.
- Top lines are never laser straight: every line has its own height and gloss, wanders
  slightly and ripples along its length with ~0.5 mm extrusion pulses.
- **Print Imperfections** (1 = a well-tuned hobby printer): ~0.01 mm Z wobble from an 8 mm
  lead screw, ~0.008 mm width variation between layers, 0.15 mm elephant foot on the first layer.
- **Dust & Handling**: sparse dust specks on upward faces and faint matte handling marks.
- All edges are rounded by ~0.07 mm (Bevel).
- With Real Layer Geometry off, the shader fakes the same terraces (flat steps
  `layer / tan(slope)` wide, rounded perimeter edge, two perimeter lines, diagonal infill).
- STLs arrive flat shaded; when the material is applied, curved areas are smoothed and edges
  sharper than 35° stay crisp.

### Camera
- **Lens Effects** (Render panel): slight lens distortion and chromatic aberration, bloom,
  vignetting and sensor grain.
- **Camera Roll**: a natural 0.6° tilt of the horizon.

### Scene materials
- **Photo textures (Poly Haven, CC0):** the "(Photo)" materials under Material Library > Wood
  and the desk use real scanned wood (color + normal + roughness at true size, e.g. Oak Veneer
  1.83 m).
  - They are downloaded on first use and cached in the user folder. This needs
    *Preferences > System > Network > Allow Online Access*. When it is off, another cached
    resolution is used; if none exists, procedural wood is used instead.
  - Resolution is set in the add-on preferences under *Photo Texture Resolution*
    (default 4K ≈ 43 MB per wood, 8K ≈ 150 MB).
  - Fibres and pores smaller than one texel are added procedurally.
  - Props are built with real-scale box-projected UVs (1 UV unit = 1 m).
- **Cutting mat:** matte PVC micro texture, mint grid, ruler ticks along the edges, diagonal
  guide lines, light knife marks and a lighter core layer visible on the edge.

## Extending the palette

- From the panel: **Extend Palette**. Additions are written to the user folder
  (`user_filaments.json`, `user_materials.json`) and survive updates.
- Your own props: select them → **Props > My Asset Library > Save**, or put `.blend` files in
  `print3d_studio/assets/` or in the *Extra Asset Folder* set in the preferences.
- In code: `data/filaments.json`, `data/materials.json`, material builders in
  `materials/surfaces.py`, props in `scene/furniture.py` (`@item(...)`).

## Tests and calibration

```bash
# full scene + every prop, in the background
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/test_render.py -- renders/test.png DESK_DAY 64 PLA_SILK --all
# close-up realism check on the desk
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/closeup_test.py -- renders/close.png 384 PLA_BASIC 1.15 14
# 1:1 calibration render of a real STL on a studio backdrop
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --python tools/benchy_calib.py -- samples/benchy.stl renders/benchy.png "#F2621B" "#D6D3CE" 145 18 512 2400
# top-surface check: a 40 x 40 x 5 mm square on the desk under a grazing lamp
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup --online-mode --python tools/top_test.py -- renders/top.png 256
# UI test in a real Blender window (screenshots go to renders/ui)
"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --factory-startup --python tools/ui_test.py -- renders/ui
```

## License and credits

- Add-on code: [GPL-3.0-or-later](LICENSE) (required for Blender add-ons).
- Photo textures: [Poly Haven](https://polyhaven.com), CC0. Not stored in this repository;
  they are downloaded on first use.
- Sample model: #3DBenchy by Creative Tools, CC BY-ND 4.0 — see [samples/README.md](samples/README.md).
