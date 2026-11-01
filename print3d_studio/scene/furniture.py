"""Ready-made props. Dimensions are in meters.

To add a prop, write a function decorated with `@item("id", "Display Name", "ICON")`;
it receives (collection, root_empty, rng) and parents its objects to the root.
Easier: model it in Blender and use Props > My Asset Library > Save.
"""
import math
import random

import bpy
from mathutils import Matrix, Vector

from .. import utils
from ..materials import surfaces
from .. import library
from .mesh import MB, mat4

COLLECTION = "P3D_Props"
ITEMS = []          # (id, label, icon, function)
DESK_TOP = 0.75

BOOK_COLORS = ['#7A2E2E', '#2E4A7A', '#2F5D50', '#C9B27C', '#3B3B3B', '#8C5A3C',
               '#E6E1D6', '#5B4A7A', '#A3473A', '#486B8A', '#D4A24C', '#6B6B5E']


def item(iid, label, icon='MESH_CUBE'):
    def deco(fn):
        ITEMS.append((iid, label, icon, fn))
        return fn
    return deco


def M(mid):
    return surfaces.get(mid)


def book_mat(rng):
    h = rng.choice(BOOK_COLORS)
    return surfaces.make("P3D_Book_" + h[1:], "paper", {"base": h, "rough": 0.5, "fiber": 0.5, "coat": 0.15})


def book(mb, t, d, h, pre, cover, pages=None):
    """Hard-cover book in local space: X = thickness, Y = depth (spine at -Y), Z = height."""
    pages = pages or M('book_pages')
    c, over = 0.0022, 0.003
    for sx in (-1, 1):
        mb.box((c, d, h), (sx * (t / 2 - c / 2), 0, 0), cover, pre=pre)
    mb.box((t, c, h), (0, -d / 2 + c / 2, 0), cover, pre=pre)
    mb.box((t - 2 * c, d - c - over, h - 2 * over), (0, (c - over) / 2, 0), pages, pre=pre)


def add(iid, context, location=None, rotation_z=0.0, seed=None):
    """Creates the prop at the 3D cursor (or the given location) and returns its root empty."""
    spec = next((i for i in ITEMS if i[0] == iid), None)
    if spec is None:
        return None
    coll = utils.ensure_collection(COLLECTION)
    root = bpy.data.objects.new("P3D_" + spec[1], None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 0.1
    coll.objects.link(root)
    root.location = location if location is not None else context.scene.cursor.location.copy()
    root.rotation_euler.z = rotation_z
    root["p3d_item"] = iid
    rng = random.Random(seed)
    try:
        spec[3](coll, root, rng)
    except library.MissingAsset as e:
        bpy.data.objects.remove(root)
        print("[3D Print Studio]", e)
        return None
    return root


# ---------------------------------------------------------------------------
@item("desk", "Desk", 'MESH_PLANE')
def desk(coll, root, rng):
    mb = MB()
    top, metal = M('oak_photo'), M('metal_black')
    W, D, H, T = 1.4, 0.7, DESK_TOP, 0.03
    mb.box((W, D, T), (0, 0, H - T / 2), top)
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box((0.04, 0.04, H - T), (sx * (W / 2 - 0.06), sy * (D / 2 - 0.06), (H - T) / 2), metal)
        mb.box((0.03, D - 0.12, 0.03), (sx * (W / 2 - 0.06), 0, 0.12), metal)
    mb.box((W - 0.12, 0.03, 0.05), (0, D / 2 - 0.06, H - T - 0.025), metal)
    ob = mb.to_object("Desk", coll, root, bevel=0.002)
    root["p3d_surface"] = H


@item("coffee_table", "Coffee Table", 'MESH_CYLINDER')
def coffee_table(coll, root, rng):
    mb = MB()
    mb.cyl(0.4, 0.025, (0, 0, 0.4375), M('walnut'), segs=96)
    mb.cyl(0.03, 0.41, (0, 0, 0.22), M('brass'))
    mb.cyl(0.2, 0.015, (0, 0, 0.0075), M('brass'), segs=64)
    mb.to_object("Coffee_Table", coll, root, bevel=0.003)
    root["p3d_surface"] = 0.45


@item("chair", "Chair", 'OUTLINER_OB_POINTCLOUD')
def chair(coll, root, rng):
    mb = MB()
    wood = M('oak_raw')
    mb.box((0.44, 0.42, 0.03), (0, 0, 0.45), wood)
    for sx in (-1, 1):
        mb.cyl(0.016, 0.435, (sx * 0.19, -0.17, 0.2175), wood, r2=0.012, segs=24)
        mb.cyl(0.016, 0.86, (sx * 0.19, 0.18, 0.43), wood, r2=0.013, segs=24)
        mb.cyl(0.009, 0.36, (sx * 0.19, 0.005, 0.15), wood, rot=(math.pi / 2, 0, 0), segs=16)
    mb.box((0.40, 0.022, 0.14), (0, 0.185, 0.78), wood, rot=(math.radians(-6), 0, 0))
    mb.box((0.38, 0.02, 0.05), (0, 0.185, 0.6), wood)
    mb.to_object("Chair", coll, root, bevel=0.003)


def _books_row(mb, rng, x0, x1, y, z, depth, fill=0.85):
    x = x0
    end = x0 + (x1 - x0) * fill
    while x < end:
        t = rng.uniform(0.018, 0.045)
        h = rng.uniform(0.17, 0.27)
        dpt = rng.uniform(0.13, min(0.22, depth))
        book(mb, t, dpt, h, Matrix.Translation((x + t / 2, y - (depth - dpt) / 2 + 0.01, z + h / 2)), book_mat(rng))
        x += t + 0.0008


@item("bookshelf", "Bookshelf", 'MENU_PANEL')
def bookshelf(coll, root, rng):
    mb = MB()
    wood = M('walnut')
    W, D, H, t = 0.8, 0.3, 1.8, 0.018
    for sx in (-1, 1):
        mb.box((t, D, H), (sx * (W / 2 - t / 2), 0, H / 2), wood)
    levels = 6
    for i in range(levels):
        z = t / 2 + i * (H - t) / (levels - 1)
        mb.box((W - 2 * t, D, t), (0, 0, z), wood)
    mb.box((W, 0.006, H), (0, D / 2 - 0.003, H / 2), wood)
    for i in range(levels - 1):
        z = t + i * (H - t) / (levels - 1)
        if rng.random() < 0.85:
            _books_row(mb, rng, -W / 2 + t + 0.01, W / 2 - t - 0.01, -0.01, z, D - 0.02, rng.uniform(0.5, 0.95))
    mb.to_object("Bookshelf", coll, root, bevel=0.0006)


@item("wall_shelf", "Wall Shelf", 'REMOVE')
def wall_shelf(coll, root, rng):
    mb = MB()
    mb.box((0.6, 0.2, 0.025), (0, 0, 0.0125), M('oak_photo'))
    mb.to_object("Wall_Shelf", coll, root, bevel=0.002)
    root["p3d_surface"] = 0.025


@item("books", "Book Stack", 'BOOKMARKS')
def books(coll, root, rng):
    mb = MB()
    z = 0.0
    for _ in range(rng.randint(3, 5)):
        w, d, h = rng.uniform(0.15, 0.24), rng.uniform(0.21, 0.3), rng.uniform(0.02, 0.045)
        pre = (Matrix.Translation((rng.uniform(-0.01, 0.01), rng.uniform(-0.01, 0.01), z + h / 2))
               @ Matrix.Rotation(math.radians(rng.uniform(-10, 10)), 4, 'Z')
               @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
        book(mb, h, d, w, pre, book_mat(rng))
        z += h
    mb.to_object("Book_Stack", coll, root, bevel=0.0006)
    root["p3d_surface"] = z


def _ground(objs, root):
    """Moves the appended objects so the lowest point of their meshes is at the root."""
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == 'MESH' for c in o.bound_box]
    if not pts:
        return
    dz = min(p.z for p in pts) - root.matrix_world.translation.z
    for o in objs:
        if o.parent == root:
            o.location.z -= dz


def _library(name, surface=None, ground=True):
    def build(coll, root, rng):
        objs = library.append_model(name, coll, root)
        if ground:
            _ground(objs, root)
        if surface is not None:
            root["p3d_surface"] = surface
    return build


# CC0 models from Poly Haven, shipped with the add-on (assets/models)
for _iid, _label, _icon, _name, _surface in (
        ("plant", "Potted Plant (Desk)", 'OUTLINER_OB_FORCE_FIELD', "potted_plant_04", None),
        ("plant_floor", "Potted Plant (Floor)", 'OUTLINER_OB_FORCE_FIELD', "potted_plant_02", None),
        ("chair_green", "Green Armchair (Floor)", 'MESH_CUBE', "GreenChair_01", None),
        ("chair_dining", "Dining Chair (Floor)", 'MESH_CUBE', "dining_chair_02", None),
        ("wooden_table", "Wooden Table (Low)", 'MESH_PLANE', "WoodenTable_01", 0.549),
        ("coffee_table_modern", "Modern Coffee Table", 'MESH_CYLINDER', "modern_coffee_table_02", 0.369),
        ("display_shelves", "Display Shelves", 'MENU_PANEL', "wooden_display_shelves_01", None),
        ("chess", "Chess Set", 'MESH_GRID', "chess_set", None),
        ("stapler", "Vintage Stapler", 'MESH_CUBE', "vintage_stapler", None),
        ("lighter", "Vintage Lighter", 'MESH_CUBE', "vintage_lighter", None),
        ("street_lamp", "Street Lamp (Outdoor)", 'LIGHT', "street_lamp_01", None)):
    item(_iid, _label, _icon)(_library(_name, _surface))

# hangs on a wall: the back plate is at the root, the arm reaches out along -Y
item("wall_lantern", "Wall Lantern", 'LIGHT')(_library("street_lamp_02", ground=False))

LAMP_W = 60.0       # W of the spot light in the desk lamp (Blender watts of a ~800 lm bulb)


@item("desk_lamp", "Desk Lamp (Arm)", 'LIGHT_SPOT')
def desk_lamp(coll, root, rng):
    objs = library.append_model("desk_lamp_arm_01", coll, root)
    # the cables are curves hooked to helper empties; once the lamp is moved off the origin
    # they stretch up to the ceiling, so they are left out
    for o in [o for o in objs if "wire" in o.name]:
        objs.remove(o)
        bpy.data.objects.remove(o)
    rig = next((o for o in objs if o.type == 'ARMATURE'), None)
    if rig is not None:
        # pose: the arm reaches about 30 cm out (along the root's -X/-Y diagonal) and the
        # shade looks straight down onto the desk
        pb = rig.pose.bones
        for n in ("ctrl_top_rotation_A", "ctrl_top_rotation_B"):
            if n in pb:
                pb[n].rotation_euler = (0.0, 0.0, 0.0)
        if "ctrl_top-position" in pb:
            pb["ctrl_top-position"].location = (-0.05, 0.15, 0.0)
    _ground(objs, root)
    head = next((o for o in objs if o.name.startswith("geo_lamp-head") and "button" not in o.name), None)
    if head is None:
        return
    import numpy as np
    bpy.context.view_layer.update()
    # the shade is a cone: its long axis is the main direction of its vertices, and the open
    # end is the one with the wide rim
    ev = head.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    P = np.array([(head.matrix_world @ v.co)[:] for v in me.vertices])
    ev.to_mesh_clear()
    c = P.mean(0)
    axis = np.linalg.svd(P - c)[2][0]
    t = (P - c) @ axis

    def rim(sel):
        q = (P - c)[sel]
        return np.linalg.norm(q - np.outer(q @ axis, axis), axis=1).mean()
    if rim(t < t.min() + 0.01) > rim(t > t.max() - 0.01):
        axis, t = -axis, -t
    c, axis, mouth = Vector(c), Vector(axis), float(t.max())
    ld = bpy.data.lights.new("Desk_Lamp_Bulb", 'SPOT')
    ld.energy = LAMP_W
    ld.color = utils.kelvin_to_linear(2700)
    ld.spot_size = math.radians(110)
    ld.spot_blend = 0.6
    ld.shadow_soft_size = 0.025
    light = bpy.data.objects.new("Desk_Lamp_Bulb", ld)
    coll.objects.link(light)
    light.location = c + axis * (mouth - 0.02)     # just inside the rim, in front of the bulb
    light.rotation_euler = axis.to_track_quat('-Z', 'Y').to_euler()
    light.parent = head
    light.matrix_parent_inverse = head.matrix_world.inverted()
    light["p3d_lamp"] = LAMP_W          # switched on by the evening lighting, off in daylight


BOOKS = "decorative_book_set_01"


def _local_bounds(o):
    co = [Vector(c) for c in o.bound_box]
    return (Vector((min(c.x for c in co), min(c.y for c in co), min(c.z for c in co))),
            Vector((max(c.x for c in co), max(c.y for c in co), max(c.z for c in co))))


def _scanned_books(coll, root, rng, n, kinds=("book_",)):
    names = [x for x in library.object_names(BOOKS) if x.startswith(kinds)]
    rng.shuffle(names)
    objs = library.append_objects(BOOKS, names[:n], coll, root)
    for o in objs:
        o.rotation_euler = (0.0, 0.0, 0.0)
    return objs


def _book_row(coll, root, rng, n):
    """Upright books side by side, spines in line at the front, centered on the root."""
    objs = _scanned_books(coll, root, rng, n, ("book_", "catalogue_"))
    x = 0.0
    for o in objs:
        mn, mx = _local_bounds(o)
        o.location = (x - mn.x, -mn.y - 0.1, -mn.z)
        x += mx.x - mn.x + 0.001
    for o in objs:
        o.location.x -= x / 2


@item("book_row", "Book Row (Scanned)", 'BOOKMARKS')
def book_row(coll, root, rng):
    _book_row(coll, root, rng, rng.randint(7, 12))


@item("books_few", "Book Row, Short (Scanned)", 'BOOKMARKS')
def books_few(coll, root, rng):
    _book_row(coll, root, rng, rng.randint(4, 6))


@item("book_stack_scanned", "Book Stack (Scanned)", 'BOOKMARKS')
def book_stack_scanned(coll, root, rng):
    """Books lying flat, biggest at the bottom, each turned a little."""
    objs = _scanned_books(coll, root, rng, rng.randint(3, 5))
    objs.sort(key=lambda o: -o.dimensions.y * o.dimensions.z)
    z = 0.0
    for o in objs:
        mn, mx = _local_bounds(o)
        rot = Matrix.Rotation(rng.uniform(-0.2, 0.2), 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'Y')
        corners = [rot @ Vector((x, y, zz)) for x in (mn.x, mx.x) for y in (mn.y, mx.y) for zz in (mn.z, mx.z)]
        lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
        hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
        o.matrix_basis = Matrix.Translation(Vector((rng.uniform(-0.01, 0.01) - (lo.x + hi.x) / 2,
                                                    rng.uniform(-0.01, 0.01) - (lo.y + hi.y) / 2,
                                                    z - lo.z))) @ rot
        z += hi.z - lo.z
    root["p3d_surface"] = z


@item("postcards", "Postcards", 'IMAGE_DATA')
def postcards(coll, root, rng):
    """A few postcards lying loosely on top of each other."""
    names = ["postcard_%02d" % i for i in rng.sample(range(1, 21), rng.randint(2, 4))]
    objs = library.append_objects("postcard_set_01", names, coll, root)
    for i, o in enumerate(objs):
        mn, mx = _local_bounds(o)
        rot = Matrix.Rotation(rng.uniform(-0.6, 0.6), 4, 'Z') @ Matrix.Rotation(-math.pi / 2, 4, 'X')
        c = rot @ ((mn + mx) / 2)
        o.matrix_basis = Matrix.Translation(Vector((rng.uniform(-0.04, 0.04) - c.x,
                                                    rng.uniform(-0.03, 0.03) - c.y,
                                                    0.0004 * (i + 1) - c.z))) @ rot


@item("mug", "Mug", 'MOD_SOLIDIFY')
def mug(coll, root, rng):
    mb = MB()
    m = M(rng.choice(['ceramic_white', 'ceramic_black', 'ceramic_sage']))
    mb.lathe([(0.0, 0.006), (0.036, 0.006), (0.037, 0.095), (0.041, 0.095), (0.041, 0.004),
              (0.039, 0.0), (0.0, 0.0)], (0, 0, 0), m)
    mb.torus(0.026, 0.006, (0.041, 0, 0.05), m, rot=(math.pi / 2, 0, 0), arc=math.pi, arc_start=-math.pi / 2)
    mb.to_object("Mug", coll, root, bevel=0.0)


@item("pen_cup", "Pen Cup", 'GREASEPENCIL')
def pen_cup(coll, root, rng):
    mb = MB()
    mb.lathe([(0.0, 0.004), (0.036, 0.004), (0.036, 0.1), (0.04, 0.1), (0.04, 0.0), (0.0, 0.0)],
             (0, 0, 0), M('metal_alu'))
    for i in range(5):
        a = 2 * math.pi * i / 5 + rng.uniform(-0.3, 0.3)
        r = rng.uniform(0.01, 0.022)
        tilt = math.radians(rng.uniform(4, 12))
        col = surfaces.make("P3D_Pen_" + str(i), "plastic",
                            {"base": rng.choice(['#1F4FD1', '#C8102E', '#141414', '#F2C200', '#EFEFEC']), "rough": 0.3})
        mb.cyl(0.0045, 0.145, (math.cos(a) * r, math.sin(a) * r, 0.075), col,
               rot=(tilt * math.sin(a), -tilt * math.cos(a) * -1, 0), segs=12)
    mb.to_object("Pen_Cup", coll, root, bevel=0.0)


@item("cutting_mat", "Cutting Mat (A3)", 'GRID')
def cutting_mat(coll, root, rng):
    mb = MB()
    mb.box((0.45, 0.30, 0.003), (0, 0, 0.0015), M('cutting_mat'))
    mb.to_object("Cutting_Mat", coll, root, bevel=0.0008)
    root["p3d_surface"] = 0.003


@item("pei_plate", "PEI Build Plate", 'MESH_GRID')
def pei_plate(coll, root, rng):
    mb = MB()
    mb.box((0.257, 0.257, 0.0015), (0, 0, 0.00075), M('pei_textured'))
    mb.to_object("PEI_Plate", coll, root, bevel=0.0005)
    root["p3d_surface"] = 0.0015


@item("laptop", "Laptop", 'DESKTOP')
def laptop(coll, root, rng):
    mb = MB()
    alu, blk = M('metal_alu'), M('plastic_black')
    mb.box((0.32, 0.22, 0.012), (0, 0, 0.006), alu)
    mb.box((0.28, 0.1, 0.001), (0, 0.03, 0.0122), blk)
    mb.box((0.11, 0.07, 0.0004), (0, -0.06, 0.0121), M('steel_brushed'))
    hinge = Matrix.Translation((0, 0.11, 0.012)) @ Matrix.Rotation(math.radians(-15), 4, 'X')
    mb.box((0.32, 0.006, 0.21), (0, -0.003, 0.105), alu, pre=hinge)
    mb.box((0.30, 0.0008, 0.19), (0, -0.0062, 0.107), M('screen'), pre=hinge)
    mb.to_object("Laptop", coll, root, bevel=0.0015)


@item("rug", "Rug", 'SNAP_FACE')
def rug(coll, root, rng):
    mb = MB()
    mb.box((2.0, 1.4, 0.008), (0, 0, 0.004), M(rng.choice(['carpet_beige', 'carpet_gray'])))
    mb.to_object("Rug", coll, root, bevel=0.003)


@item("frame", "Picture Frame", 'IMAGE_PLANE')
def frame(coll, root, rng):
    mb = MB()
    fr = M('plastic_black')
    W, H, b, dpt = 0.5, 0.4, 0.03, 0.025
    mb.box((W, dpt, b), (0, 0, b / 2), fr)
    mb.box((W, dpt, b), (0, 0, H - b / 2), fr)
    mb.box((b, dpt, H - 2 * b), (-W / 2 + b / 2, 0, H / 2), fr)
    mb.box((b, dpt, H - 2 * b), (W / 2 - b / 2, 0, H / 2), fr)
    mb.box((W - 2 * b, 0.004, H - 2 * b), (0, 0.004, H / 2), M('canvas_art'))
    mb.to_object("Picture_Frame", coll, root, bevel=0.002)
