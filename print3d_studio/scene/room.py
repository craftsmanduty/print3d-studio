"""Builds the room (walls, floor, ceiling, window) and the studio backdrop."""
import math

import bpy
from mathutils import Vector

from .. import utils
from ..materials import surfaces
from .mesh import MB, lines

COLLECTION = "P3D_Room"


# displaced walls and floors are cut into cells no bigger than this, and Cycles may split a
# cell at most 2^8 times per side (render.py): the finest relief is ~1.6 mm wherever the
# camera is, instead of one huge face diced to millions of micro faces near the lens
RELIEF_CELL = 0.4


def _wall(mb, along, fixed, u0, u1, H, T, mat, hole=None, cell=None):
    if hole is None:
        us, zs = (lines(u0, u1, cell), lines(0.0, H, cell)) if cell else ([u0, u1], [0.0, H])
        mb.slab(along, fixed, us, zs, T, mat)
        return
    uc, w, sill, h = hole
    a, b = max(uc - w / 2, u0), min(uc + w / 2, u1)
    top = min(sill + h, H)
    step = cell or 1e9
    us = lines(u0, u1, step, keep=(a, b))
    zs = lines(0.0, H, step, keep=(sill, top))
    empty = [(i, j) for i in range(len(us) - 1) for j in range(len(zs) - 1)
             if a <= us[i] < b and sill <= zs[j] < top]
    mb.slab(along, fixed, us, zs, T, mat, empty=empty)


def build_room(context, s):
    coll = utils.ensure_collection(COLLECTION)
    old = tuple(coll.get("p3d_dims", ()))
    utils.clear_collection(coll)
    W, D, H, T = s.room_w, s.room_d, s.room_h, 0.12
    coll["p3d_dims"] = (W, D)
    if len(old) == 2 and (abs(old[0] - W) > 1e-6 or abs(old[1] - D) > 1e-6):
        from . import carry, decor
        # room furniture goes back into its slots (or hides if it no longer fits); the rest
        # keeps its distance to the walls
        placed = decor.relayout(context.scene, W, D)
        carry.keep_wall_gaps(context.scene, old, (W, D), skip=placed)
    wall_m = surfaces.get(s.room_wall_mat, relief=True)
    floor_m = surfaces.get(s.room_floor_mat, relief=True)
    trim = surfaces.get('paint_white')

    mb = MB()
    # the walking surface is a fine grid (for the relief); the slab below it stays one box
    mb.grid(lines(-W / 2 - T, W / 2 + T, RELIEF_CELL), lines(-D / 2 - T, D / 2 + T, RELIEF_CELL), 0.0, floor_m)
    mb.box((W + 2 * T, D + 2 * T, 0.038), (0, 0, -0.031), trim)     # top below the deepest relief
    floor = mb.to_object("Floor", coll, bevel=0.0)
    surfaces.add_relief(floor)

    win = s.room_window
    ww, wh, sill = s.window_w, s.window_h, s.window_sill
    walls = {
        'BACK': ('X', D / 2 + T / 2, -W / 2 - T, W / 2 + T, Vector((0, 1, 0))),
        'LEFT': ('Y', -W / 2 - T / 2, -D / 2, D / 2, Vector((-1, 0, 0))),
        'RIGHT': ('Y', W / 2 + T / 2, -D / 2, D / 2, Vector((1, 0, 0))),
    }
    if s.room_front:
        walls['FRONT'] = ('X', -D / 2 - T / 2, -W / 2 - T, W / 2 + T, Vector((0, -1, 0)))

    mb = MB()
    for key, (along, fixed, u0, u1, nrm) in walls.items():
        hole = (0.0, ww, sill, wh) if key == win else None
        _wall(mb, along, fixed, u0, u1, H, T, wall_m, hole, cell=RELIEF_CELL)
        if s.room_baseboard:
            inner = fixed - nrm.x * (T / 2 + 0.006) if along == 'Y' else fixed - nrm.y * (T / 2 + 0.006)
            _wall(mb, along, inner, u0 + (T if along == 'X' else 0), u1 - (T if along == 'X' else 0),
                  0.08, 0.012, trim, None)
    if s.room_ceiling:
        mb.box((W + 2 * T, D + 2 * T, 0.05), (0, 0, H + 0.025), surfaces.get('paint_white'))
    surfaces.add_relief(mb.to_object("Walls", coll, bevel=0.0))

    if win in walls:
        along, fixed, u0, u1, nrm = walls[win]
        _window(coll, along, fixed, ww, wh, sill, T, nrm, s)

    # outdoor ground seen through the window
    mb = MB()
    mb.box((80, 80, 0.02), (0, 0, -0.08), surfaces.get('concrete'))
    outside = mb.to_object("Outside_Ground", coll, bevel=0.0)
    return coll


def _window(coll, along, fixed, ww, wh, sill, T, nrm, s):
    mb = MB()
    fm = surfaces.get('plastic_white')
    fw, fd = 0.055, 0.07
    zc = sill + wh / 2

    def bx(du, dz, su, sz, depth, mat, dn=0.0):
        if along == 'X':
            mb.box((su, depth, sz), (du, fixed + dn, dz), mat)
        else:
            mb.box((depth, su, sz), (fixed + dn, du, dz), mat)

    bx(0, sill + fw / 2, ww, fw, fd, fm)
    bx(0, sill + wh - fw / 2, ww, fw, fd, fm)
    bx(-ww / 2 + fw / 2, zc, fw, wh, fd, fm)
    bx(ww / 2 - fw / 2, zc, fw, wh, fd, fm)
    bx(0, zc, fw * 0.8, wh, fd, fm)
    # inner window sill
    inward = -1.0 * (nrm.x if along == 'Y' else nrm.y)
    bx(0, sill - 0.012, ww + 0.1, 0.025, T + 0.06, surfaces.get('marble_white'), dn=inward * 0.03)
    mb.to_object("Window_Frame", coll, bevel=0.002)

    mb = MB()
    bx(0, zc, ww - fw, wh - fw, 0.006, surfaces.get('glass_clear'))
    glass = mb.to_object("Window_Glass", coll, bevel=0.0)
    glass.visible_shadow = False
    glass["p3d_normal"] = tuple(nrm)
    glass["p3d_size"] = (ww - fw, wh - fw)
    c = Vector((0, fixed, zc)) if along == 'X' else Vector((fixed, 0, zc))
    glass["p3d_center"] = tuple(c)


def find_window():
    g = bpy.data.objects.get("Window_Glass")
    if g is None or "p3d_normal" not in g:
        return None
    return Vector(g["p3d_center"]), Vector(g["p3d_normal"]), tuple(g["p3d_size"])


def build_cove(context, s):
    """Curved seamless backdrop (for product shots)."""
    coll = utils.ensure_collection(COLLECTION)
    utils.clear_collection(coll)
    W, D, H, R = s.cove_w, s.cove_d, s.cove_h, s.cove_r
    yb = D / 2
    prof = [(-D / 2, 0.0)]
    segs = 24
    for i in range(segs + 1):
        a = math.pi / 2 * i / segs
        prof.append((yb - R + R * math.sin(a), R - R * math.cos(a)))
    prof.append((yb, H))

    me = bpy.data.meshes.new("Backdrop")
    verts = []
    for x in (-W / 2, W / 2):
        verts += [(x, y, z) for y, z in prof]
    n = len(prof)
    faces = [(j, j + 1, n + j + 1, n + j) for j in range(n - 1)]
    me.from_pydata(verts, [], faces)
    for p in me.polygons:
        p.use_smooth = True
    mat = surfaces.make("P3D_Backdrop", "paper", {"base": tuple(s.cove_color), "rough": 0.8, "fiber": 0.1}, rebuild=True)
    me.materials.append(mat)
    ob = bpy.data.objects.new("Backdrop", me)
    coll.objects.link(ob)
    return coll
