"""Top-surface check: a 40 x 40 x 5 mm printed square on the desk under one grazing lamp,
like a phone photo of a calibration print.

  blender -b --factory-startup --python tools/top_test.py -- <out.png> [samples] [color_hex]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = os.path.abspath(argv[0]) if argv else os.path.join(ROOT, "renders", "top.png")
samples = int(argv[1]) if len(argv) > 1 else 256
color = argv[2] if len(argv) > 2 else "#3C3F44"

import print3d_studio  # noqa: E402
from print3d_studio import utils  # noqa: E402

print3d_studio.register()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# 40 x 40 x 5 mm square in millimeters, like an imported STL
bpy.ops.mesh.primitive_cube_add(size=1.0)
sq = bpy.context.active_object
sq.scale = (40.0, 40.0, 5.0)
bpy.ops.object.transform_apply(scale=True)
sq.data.vertices.foreach_set("co", [c + (2.5 if i % 3 == 2 else 0.0)
                                    for i, c in enumerate([x for v in sq.data.vertices for x in v.co])])
sq.rotation_euler.z = math.radians(45)

sc = bpy.context.scene
s = sc.p3d
s.quick_preset = 'DESK_EVENING'
s.quick_decor = False
p = sq.p3d
p.filament_type = 'PLA_BASIC'
p.use_custom_color = True
p.custom_color = utils.hex_to_linear(color)
bpy.ops.p3d.quick_scene()

# one warm desk lamp behind the print, grazing the top so the lines catch the light
lights = bpy.data.collections.get("P3D_Lights")
for o in list(lights.objects):
    if o.type == 'LIGHT':
        bpy.data.objects.remove(o, do_unlink=True)
c = sum((sq.matrix_world @ Vector(b) for b in sq.bound_box), Vector()) / 8
ld = bpy.data.lights.new("Lamp", 'AREA')
ld.energy, ld.size = 6.0, 0.06
ld.color = utils.kelvin_to_linear(3400)
lamp = bpy.data.objects.new("Lamp", ld)
lights.objects.link(lamp)
lamp.location = c + Vector((0.0, 0.32, 0.12))
lamp.rotation_euler = (c - lamp.location).to_track_quat('-Z', 'Y').to_euler()

s.cam_lens, s.cam_elev, s.cam_azim, s.cam_fstop, s.cam_margin = 35.0, 52.0, 0.0, 5.6, 1.3
print3d_studio.scene.camera.setup(bpy.context, s, sq)
sc.render.resolution_x, sc.render.resolution_y = 1500, 2000
sc.render.resolution_percentage = 100
sc.cycles.samples = samples
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("OK ->", out)
