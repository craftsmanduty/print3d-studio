import math

import bpy


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex_to_linear(h):
    """'#RRGGBB' -> lineer RGB tuple. Zaten tuple ise aynen dondurur."""
    if isinstance(h, (tuple, list)):
        return tuple(h[:3])
    h = h.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def linear_to_hex(c):
    return "#" + "".join("%02X" % round(linear_to_srgb(v) * 255) for v in c[:3])


def kelvin_to_linear(k):
    """Renk sicakligi (K) -> yaklasik lineer RGB (en parlak kanal 1.0)."""
    t = k / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255.0
    rgb = [srgb_to_linear(max(0.0, min(255.0, v)) / 255.0) for v in (r, g, b)]
    m = max(rgb)
    return tuple(v / m for v in rgb)


def ensure_collection(name, parent=None):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if coll.name not in parent.children:
        parent.children.link(coll)
    return coll


def clear_collection(coll):
    for ob in list(coll.all_objects):
        bpy.data.objects.remove(ob, do_unlink=True)


def node_material(name, existing=None):
    """Bos (temizlenmis) bir dugum agaci olan malzeme dondurur."""
    mat = existing or bpy.data.materials.get(name) or bpy.data.materials.new(name)
    if mat.node_tree is None:
        try:
            mat.use_nodes = True
        except Exception:
            pass
    mat.node_tree.nodes.clear()
    return mat


def world_tree(scene):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("P3D_World")
        scene.world = world
    if world.node_tree is None:
        try:
            world.use_nodes = True
        except Exception:
            pass
    world.node_tree.nodes.clear()
    return world


def world_bounds(obj):
    """Nesnenin dunya uzayindaki (min, max, merkez, yaricap) degerleri."""
    from mathutils import Vector
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (mn + mx) / 2
    return mn, mx, center, max((mx - mn).length / 2, 1e-4)


def is_print_object(obj):
    return obj is not None and obj.type == 'MESH'
