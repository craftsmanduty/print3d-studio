"""Turns a top-down photo of a plank floor into a board atlas for the "planks" shader.

  blender -b --factory-startup --python tools/make_floor_atlas.py -- <photo> <out folder> <name> [board width mm] [board length mm]

The floor itself is laid out by the shader (equal boards, fixed end-joint stagger, random board
per position), so only real, whole boards are taken from the photo:
1. Finds the long seams (straight dark lines over the whole height) and fits a line to each,
   so camera tilt and perspective are removed: every board is resampled to the same width.
2. Removes light falloff and color cast (smooth 2D fit per channel).
3. Finds the end joints; the longest piece between two joints gives the board length (or
   pass it in mm). Every piece at least 85 % that long becomes one atlas column, stretched
   to the exact board length, with the old joint lines trimmed off.
4. Writes <name>_COL.jpg, _NRM.jpg (OpenGL), _ROUGHNESS.jpg and <name>.json (sizes).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from floorlib import LUMW, blur, flatten, load, sample, write_maps  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT, NAME = argv[0], argv[1], argv[2]
PLANK_MM = float(argv[3]) if len(argv) > 3 else 190.0
LEN_MM = float(argv[4]) if len(argv) > 4 else None
os.makedirs(OUT, exist_ok=True)


# --- 1. long seams -------------------------------------------------------------------
im = load(SRC)
h, w = im.shape[:2]
lum = im @ LUMW
dark = blur(lum, 6) - lum                                    # thin dark lines > 0
band = max(64, h // 16)
centers, peaks = [], []
for y0 in range(0, h - band + 1, band):
    prof = dark[y0:y0 + band].mean(0)
    pk = [x for x in range(4, w - 4) if prof[x] == prof[x - 4:x + 5].max() and prof[x] > 0.02]
    centers.append(y0 + band / 2)
    peaks.append(pk)
mid = len(peaks) // 2
tracks = []
for x in peaks[mid]:
    pts = {mid: x}
    for step in (1, -1):
        cur, i = x, mid + step
        while 0 <= i < len(peaks):
            near = [p for p in peaks[i] if abs(p - cur) <= w * 0.01]
            if not near:
                break
            cur = min(near, key=lambda p: abs(p - cur))
            pts[i] = cur
            i += step
    if len(pts) == len(peaks):                               # seen in every band: a real seam
        ys = np.array([centers[i] for i in pts]); xs = np.array([pts[i] for i in pts], float)
        a, b = np.polyfit(ys, xs, 1)
        if np.abs(xs - (a * ys + b)).max() < w * 0.004:      # straight: not a wood crack
            tracks.append((a, b))
tracks.sort(key=lambda t: t[1])
gaps = np.diff([t[1] for t in tracks])
print("SEAMS", len(tracks), "spacing px", np.round(gaps))
med = np.median(gaps)
# keep the longest run of seams with plank-width spacing
runs, cur = [], [tracks[0]]
for t, g in zip(tracks[1:], gaps):
    if abs(g - med) < med * 0.15:
        cur.append(t)
    else:
        runs.append(cur); cur = [t]
runs.append(cur)
seams = max(runs, key=len)
n = len(seams) - 1
print("PLANKS", n)

# --- 2. resample planks to equal width ------------------------------------------------
PW = int(round(med * 0.85 / 8)) * 8                         # output plank width in px
W = PW * n
H = int(round(h * PW / med / 8)) * 8
Y = np.linspace(0, h - 1, H)
cols = []
for k in range(n):
    (a0, b0), (a1, b1) = seams[k], seams[k + 1]
    u = (np.arange(PW) + 0.5) / PW
    xl, xr = a0 * Y + b0, a1 * Y + b1
    xs = xl[:, None] + u[None, :] * (xr - xl)[:, None]
    cols.append(sample(im, xs, np.repeat(Y[:, None], PW, 1)))
rect = np.concatenate(cols, 1)

flatten(rect)

# --- 3. end joints and vertical tiling --------------------------------------------------
L = rect @ LUMW
dark = blur(L, 5) - L
joints = []
for k in range(n):
    prof = dark[:, k * PW + PW // 8:(k + 1) * PW - PW // 8].mean(1)
    across = (dark[:, k * PW + PW // 8:(k + 1) * PW - PW // 8] > 0.01).mean(1)
    pk = [y for y in range(6, H - 6) if prof[y] == prof[y - 6:y + 7].max() and prof[y] > 0.014 and across[y] > 0.25]
    merged = []                                             # both edges of one joint -> one
    for y in pk:
        if merged and y - merged[-1][-1] < 15:
            merged[-1].append(y)
        else:
            merged.append([y])
    joints.append([int(round(np.mean(m))) for m in merged])
print("JOINTS", joints)

# --- 3. whole boards -> atlas -------------------------------------------------------------
# a board runs from one end joint to the next; the longest such piece is a complete board and
# gives the board length (photos rarely show more than one full board per column)
pieces = []
for k in range(n):
    cuts = [0] + joints[k] + [H]
    for a, b in zip(cuts, cuts[1:]):
        closed = a in joints[k] and b in joints[k]
        pieces.append((b - a, k, a, b, closed))
full = [p for p in pieces if p[4]]
if LEN_MM:
    LP = int(round(LEN_MM / PLANK_MM * PW))
elif full:
    LP = max(full)[0]
else:
    LP = max(pieces)[0]
print("BOARD LENGTH px", LP, "=", round(LP / PW * PLANK_MM), "mm")
TRIM = 4                                                     # leave the old joint line out
use = sorted([p for p in pieces if p[0] >= 0.85 * LP], reverse=True)
print("BOARDS", [(p[1], p[2], p[3], round(p[0] / LP, 2)) for p in use])
atlas = np.zeros((LP, PW * len(use), 3), np.float32)
for i, (_, k, a, b, _) in enumerate(use):
    a2 = a + (TRIM if a in joints[k] else 0)
    b2 = b - (TRIM if b in joints[k] else 0)
    ys = a2 + (np.arange(LP) + 0.5) * (b2 - a2) / LP - 0.5   # stretch short pieces (<= 15%)
    i0 = np.clip(np.floor(ys).astype(np.int64), 0, H - 2)
    f = (ys - i0)[:, None, None]
    src = rect[:, k * PW:(k + 1) * PW]
    atlas[:, i * PW:(i + 1) * PW] = src[i0] * (1 - f) + src[i0 + 1] * f

# --- 4. maps ------------------------------------------------------------------------
write_maps(atlas, OUT, NAME, {"boards": len(use), "board_width_m": PLANK_MM / 1000.0,
                              "board_length_m": round(LP / PW * PLANK_MM / 1000.0, 4),
                              "px": [PW * len(use), LP]})
