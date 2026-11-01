"""Furnishing of the one-click scene: things on the desk and furniture around the room.

Room furniture sits in slots measured from the walls. When the room is resized the slots are
laid out again: a piece that no longer fits is hidden (with whatever stands on it) and comes
back when the room is big enough again. A piece the user has moved by hand leaves its slot
and is treated like any other object (it keeps its distance to the walls, see carry.py).
"""
import math

import bpy
from mathutils import Matrix, Vector

from . import carry, furniture

DESK_W, DESK_D = 1.4, 0.7          # furniture.desk
SLOT = "p3d_slot"                   # slot name on the root of a placed piece
SLOT_LOC = "p3d_slot_loc"           # where the slot put it (moved by hand if it differs)
HIDDEN = "p3d_slot_hidden"


def _slots(W, D):
    """{slot: (item, location, rotation) or None if it does not fit} for a W x D room with
    the desk centered against the back wall (+Y)."""
    back, desk_r = D / 2, DESK_W / 2
    shelf_x = desk_r + 0.15 + 0.54
    return {
        # display shelves to the right of the desk, against the back wall
        "shelves": ("display_shelves", (shelf_x, back - 0.2), 0.0)
        if W / 2 >= shelf_x + 0.54 + 0.05 else None,
        # floor plant in the corner by the window, left of the desk
        "plant_floor": ("plant_floor", (-W / 2 + 0.6, back - 0.55), 0.6)      # leaves reach ~56 cm
        if W / 2 >= desk_r + 1.0 else None,
        # reading corner at the front right: armchair and a coffee table with a chess set
        "armchair": ("chair_green", (W / 2 - 0.6, -D / 2 + 1.1), -math.pi / 2 - 0.5)
        if W >= 3.2 and D >= 3.0 else None,
        "coffee_table": ("coffee_table", (W / 2 - 1.45, -D / 2 + 0.95), 0.0)
        if W >= 3.2 and D >= 3.0 else None,
    }


def furnish(context, desk):
    """Puts the desk decor and the room furniture into the scene."""
    s = context.scene.p3d
    add = furniture.add
    base = desk.location + Vector((0, 0, furniture.DESK_TOP))
    # on the desk, around the mat the model stands on
    add("cutting_mat", context, location=base + Vector((0.0, -0.08, 0.0)))
    lamp = add("desk_lamp", context, rotation_z=math.pi / 2,
               location=base + Vector((-0.5, DESK_D / 2 - furniture.LAMP_THROAT, furniture.LAMP_JAW)))
    if lamp is not None:
        carry.fix_parent(lamp, desk)               # clamped to the back edge of the desk
    add("plant", context, location=base + Vector((0.55, 0.2, 0.0)), rotation_z=0.8)
    add("book_stack_scanned", context, location=base + Vector((0.42, -0.14, 0.0)), rotation_z=0.2, seed=7)
    add("mug", context, location=base + Vector((0.3, 0.12, 0.0)), rotation_z=2.2, seed=1)
    add("postcards", context, location=base + Vector((-0.4, -0.18, 0.0)), seed=4)
    add("stapler", context, location=base + Vector((-0.25, 0.17, 0.0)), rotation_z=0.35)

    # the room around it: what the camera sees behind the desk, out of focus
    for name, slot in _slots(s.room_w, s.room_d).items():
        if slot is None:
            continue                       # does not fit this room
        item, (x, y), rz = slot
        root = add(item, context, location=Vector((x, y, 0.0)), rotation_z=rz)
        if root is None:
            continue
        root[SLOT] = name
        root[SLOT_LOC] = (x, y)
        if name == "shelves":
            _dress_shelves(context, root)
        elif name == "coffee_table":
            add("chess", context, location=root.location + Vector((0, 0, root["p3d_surface"])), rotation_z=0.3)
    carry.update(context.scene)


def _show(root, show):
    for o in [root] + list(root.children_recursive):
        o.hide_viewport = not show
        o.hide_render = not show
    if show:
        root.pop(HIDDEN, None)
    else:
        root[HIDDEN] = True


def relayout(scene, W, D):
    """Puts the room furniture back into its slots for a W x D room, hiding what no longer
    fits. Returns the roots it handled (pieces moved by hand are left to the caller)."""
    carry.update(scene)                 # things on the shelves / table go along with them
    slots = _slots(W, D)
    done = set()
    for root in [o for o in scene.objects if SLOT in o and o.parent is None]:
        name = root[SLOT]
        if name not in slots:
            continue
        sx, sy = root.get(SLOT_LOC, (root.location.x, root.location.y))
        if abs(root.location.x - sx) > 1e-4 or abs(root.location.y - sy) > 1e-4:
            del root[SLOT]                 # moved by hand: an ordinary object from now on
            if HIDDEN in root:
                _show(root, True)
            continue
        slot = slots[name]
        if slot is None:
            if HIDDEN not in root:
                _show(root, False)
        else:
            _, (x, y), rz = slot
            root.location.x, root.location.y = x, y
            root.rotation_euler.z = rz
            root[SLOT_LOC] = (x, y)
            if HIDDEN in root:
                _show(root, True)
        done.add(root)
    return done


def _shelf_levels(context, root):
    """(z, free height above) of every board of a shelf unit, bottom to top."""
    context.view_layer.update()
    dg = context.evaluated_depsgraph_get()
    obs = [o for o in root.children_recursive if o.type == 'MESH']
    pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
    if not pts:
        return []
    top = max(p.z for p in pts)
    c = root.matrix_world.translation
    names = {o.name for o in obs}
    origin, levels = Vector((c.x, c.y, top + 0.01)), []
    for _ in range(40):
        hit, loc, nrm, _, ob, _ = context.scene.ray_cast(dg, origin, Vector((0, 0, -1)))
        if not hit or ob is None or ob.name not in names:
            break
        if nrm.z > 0.9:
            levels.append(loc.z)
        origin = loc - Vector((0, 0, 0.005))
    levels.sort()
    return [(z, (levels[i + 1] if i + 1 < len(levels) else top + 0.3) - z) for i, z in enumerate(levels)]


def _dress_shelves(context, shelves):
    """Books, a small plant and a few objects on the boards of the display shelves."""
    add = furniture.add
    rz = shelves.rotation_euler.z
    rot = Matrix.Rotation(rz, 3, 'Z')
    c = shelves.matrix_world.translation
    levels = _shelf_levels(context, shelves)
    col = 0.36                      # the unit has three cubbies side by side
    # (board from the bottom, cubby -1/0/1, prop, its height); boards 0 and 1 close the drawers
    things = [(2, -1, "plant", 0.27), (2, 0, "book_stack_scanned", 0.12), (2, 1, "books_few", 0.24),
              (3, -1, "lighter", 0.06), (3, 0, "books_few", 0.24),
              (4, -1, "book_stack_scanned", 0.12), (4, 1, "books_few", 0.24)]
    for lvl, cub, iid, h in things:
        if lvl >= len(levels) or levels[lvl][1] < h + 0.02:
            continue
        add(iid, context, location=Vector((c.x, c.y, levels[lvl][0])) + rot @ Vector((cub * col, 0.0, 0.0)),
            rotation_z=rz + (0.4 if iid == "lighter" else 0.0), seed=lvl * 10 + cub)
