"""Things standing on a prop move with it: every object that rests on top of another one
(model on the mat, mat and books on the desk...) is parented to it, so moving the desk
carries everything on it, like real objects. The relations are checked again after every
move, so an item set down somewhere else follows its new support (or the floor: no parent).

Only parents set here (marked "p3d_rest_on") are ever changed; parenting made by hand is
left alone.
"""
import bpy
from mathutils import Vector

from . import room

TOL = 0.01                       # m between the bottom of an item and the top it stands on
MARK = "p3d_rest_on"


def _managed(scene):
    """Free objects of the scene: no parent, or a parent set by us. Room and lights out."""
    roomc = bpy.data.collections.get(room.COLLECTION)
    skip = set(roomc.all_objects) if roomc else set()
    return [o for o in scene.objects
            if o.type in {'MESH', 'EMPTY'} and o not in skip and (o.parent is None or MARK in o)]


def _bounds(ob, managed):
    """World bounds of the object's own meshes (children carried by it left out), or None."""
    pts = []
    stack = [ob]
    while stack:
        o = stack.pop()
        if o.type == 'MESH' and o.visible_get():
            pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
        stack += [c for c in o.children if c not in managed]
    if not pts:
        return None
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


def _support(ob, box, boxes):
    """The object `ob` stands on: the highest top level with its footprint center, or None."""
    mn, mx = box
    cx, cy = (mn.x + mx.x) / 2, (mn.y + mx.y) / 2
    best = None
    for other, (omn, omx) in boxes.items():
        if other is ob or not (omn.x <= cx <= omx.x and omn.y <= cy <= omx.y):
            continue
        if abs(mn.z - omx.z) <= TOL and (best is None or omx.z > boxes[best][1].z):
            best = other
    return best


def _set_parent(ob, parent):
    mw = ob.matrix_world.copy()
    ob.parent = parent
    ob.matrix_world = mw
    if parent is None:
        ob.pop(MARK, None)
    else:
        ob[MARK] = parent.name


def _transforming():
    wm = bpy.context.window_manager
    return wm is not None and any(op.bl_idname.startswith("TRANSFORM_OT")
                                  for w in wm.windows for op in w.modal_operators)


def update(scene):
    """Parents every free object to what it stands on. Waits while something is being moved."""
    if _transforming():
        if not bpy.app.timers.is_registered(_retry):
            bpy.app.timers.register(_retry, first_interval=0.25)
        return
    managed = set(_managed(scene))
    boxes = {o: b for o in managed if (b := _bounds(o, managed)) is not None}
    for ob, box in boxes.items():
        sup = _support(ob, box, boxes)
        if sup is not None and (sup is ob or sup in ob.children_recursive):
            continue                                   # would be a parenting loop
        if ob.parent is not sup:
            _set_parent(ob, sup)


def _retry():
    scene = bpy.context.scene
    if scene is not None and scene.p3d.carry_items:
        update(scene)
    return None


def release_all(scene):
    for o in list(scene.objects):
        if MARK in o:
            _set_parent(o, None)


def keep_wall_gaps(scene, old, new):
    """After a room resize (old/new = (width, depth)), floor standing objects keep their
    distance to the nearest wall (desk 45 cm from the back wall...) and never end up
    inside a wall. Objects near the middle are moved in proportion."""
    managed = set(_managed(scene))
    for ob in managed:
        if ob.parent is not None:
            continue
        box = _bounds(ob, managed)
        if box is None or box[0].z > 0.05:
            continue                                   # not standing on the floor
        mn, mx = box
        shift = Vector()
        for i, (h0, h1) in enumerate(((old[0] / 2, new[0] / 2), (old[1] / 2, new[1] / 2))):
            c, ext = (mn[i] + mx[i]) / 2, (mx[i] - mn[i]) / 2
            gap = h0 - abs(c) - ext
            if abs(c) > h0 / 2:
                nc = (h1 - ext - max(gap, 0.0)) * (1 if c > 0 else -1)
            else:
                nc = c * h1 / h0
            lim = max(h1 - ext - 0.005, 0.0)
            nc = max(-lim, min(lim, nc))
            shift[i] = nc - c
        if shift.length > 1e-6:
            ob.location += shift
