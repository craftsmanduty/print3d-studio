"""Turns a top-down photo of a chevron floor into a board atlas for the "chevron" shader.

  blender -b --factory-startup --python tools/make_chevron_atlas.py -- <photo> <out folder> <name> [board width mm]

A chevron floor is a stack of bands; in every band the boards are parallel and slanted, and
the slant flips from band to band, so the boards meet in V joints on the band lines (spines).
1. Removes light falloff and color cast.
2. Finds the spines (dark lines across the whole photo) and the bands between them.
3. In every band finds the slant (the shear that lines the joints up best) and the joints.
4. Cuts out every whole board as a sheared parallelogram, straightened into an atlas column
   (u across the board along the spine, v from spine to spine), joint lines trimmed off.
Board width (measured square to the long edges) sets the real scale.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from floorlib import LUMW, blur, flatten, load, sample, write_maps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, NAME = argv[0], argv[1], argv[2]
WIDTH_MM = float(argv[3]) if len(argv) > 3 else 70.0

im = flatten(load(SRC))
h, w = im.shape[:2]
lum = im @ LUMW
dark = blur(lum, 4) - lum                                    # thin dark lines > 0


def peaks(prof, gap, thr):
    pk = [i for i in range(1, len(prof) - 1) if prof[i] >= prof[i - 1] and prof[i] >= prof[i + 1] and prof[i] > thr]
    pk.sort(key=lambda i: -prof[i])
    keep = []
    for i in pk:
        if all(abs(i - k) > gap for k in keep):
            keep.append(i)
    return sorted(keep)


# --- spines -----------------------------------------------------------------------------
across = (dark > 0.02).mean(1)
spines = peaks(across, h // 20, 0.5)
print("SPINES", spines)

# --- slant and joints of every whole band ----------------------------------------------------
bands = []
for top, bot in zip(spines, spines[1:]):
    hb = bot - top
    ys = np.arange(top + 6, bot - 6)
    best = None
    for s in np.arange(-1.5, 1.5, 0.004):
        xs = (np.arange(w)[None, :] - s * (ys[:, None] - top)).ravel()
        hist = np.bincount(np.clip(xs, -w * 2, w * 3).astype(np.int64) + w * 2,
                           weights=np.maximum(dark[ys], 0).ravel(), minlength=w * 5)
        score = (hist ** 2).sum()
        if best is None or score > best[0]:
            best = (score, s, hist)
    _, s, hist = best
    prof = np.convolve(hist, np.ones(3) / 3, mode='same')
    offs = [p - w * 2 for p in peaks(prof, 25, prof.max() * 0.3)]
    bands.append((top, bot, s, offs))
    print("BAND", top, bot, "slant %.3f" % s, "joints", offs)

pitch = np.median([d for _, _, _, o in bands for d in np.diff(o) if d > 20])
slant = np.median([abs(s) for _, _, s, _ in bands])
hb = int(np.median([b - t for t, b, _, _ in bands]))
print("PITCH px %.1f  SLANT %.3f  BAND px %d" % (pitch, slant, hb))

# --- cut whole boards ---------------------------------------------------------------------
PW, LP = int(round(pitch)), hb
TRIM = 3
boards = []
for top, bot, s, offs in bands:
    for x0, x1 in zip(offs, offs[1:]):
        if abs((x1 - x0) - pitch) > pitch * 0.12:
            continue
        xs_all = [x0, x1, x0 + s * (bot - top), x1 + s * (bot - top)]
        if min(xs_all) < 0 or max(xs_all) > w - 1:
            continue                                          # board runs out of the photo
        u = TRIM / PW + (np.arange(PW) + 0.5) / PW * (1 - 2 * TRIM / PW)
        v = TRIM / LP + (np.arange(LP) + 0.5) / LP * (1 - 2 * TRIM / LP)
        yy = top + v[:, None] * (bot - top) + 0 * u[None, :]
        xx = x0 + u[None, :] * (x1 - x0) + s * (yy - top)
        boards.append(sample(im, xx, yy))
print("BOARDS", len(boards))
atlas = np.concatenate(boards, 1)

px_mm = WIDTH_MM / (pitch / np.sqrt(1 + slant ** 2))         # board width is square to its edges
write_maps(atlas, OUT, NAME, {
    "boards": len(boards), "board_width_m": WIDTH_MM / 1000.0,
    "pitch_m": round(float(pitch * px_mm) / 1000.0, 5),           # joint spacing along the spine
    "band_m": round(float(hb * px_mm) / 1000.0, 5),               # spine to spine
    "slant": round(float(slant), 4),                       # sideways shift per unit of band height
    "px": [PW * len(boards), LP]})
