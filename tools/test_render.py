"""Eklentiyi Blender'a kurmadan test eder ve kucuk bir render alir.

Kullanim:
  blender -b --factory-startup --python tools/test_render.py -- [cikti.png] [preset] [samples]
"""
import os
import sys
import math

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = argv[0] if len(argv) > 0 else os.path.join(ROOT, "renders", "test.png")
preset = argv[1] if len(argv) > 1 else "DESK_DAY"
samples = int(argv[2]) if len(argv) > 2 else 64
ftype = argv[3] if len(argv) > 3 else "PLA_SILK"

import print3d_studio  # noqa: E402
print3d_studio.register()

# temiz sahne
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

# STL gibi mm biriminde gelen test modeli (80 birim = 80 mm)
bpy.ops.mesh.primitive_monkey_add(size=60, location=(0, 0, 0))
mk = bpy.context.active_object
mk.rotation_euler = (math.radians(0), 0, 0)
sub = mk.modifiers.new("sub", 'SUBSURF')
sub.levels = 2
sub.render_levels = 2
bpy.ops.object.modifier_apply(modifier="sub")
bpy.ops.object.transform_apply(rotation=True, scale=True)

s = bpy.context.scene.p3d
s.quick_preset = preset
s.res_preset = 'SQUARE'
s.render_quality = 'PREVIEW'
mk.p3d.filament_type = ftype
mk.p3d.layer_height = 0.2

bpy.ops.p3d.quick_scene()

# tum esyalari da olustur (hata kontrolu)
if "--all" in sys.argv:
    for iid, *_ in print3d_studio.scene.furniture.ITEMS:
        print3d_studio.scene.furniture.add(iid, bpy.context, location=(5, 5, 0))

sc = bpy.context.scene
sc.cycles.samples = samples
sc.render.resolution_x = sc.render.resolution_y = 900
sc.render.resolution_percentage = 100
sc.render.filepath = out
print("DEVICE:", sc.cycles.device)
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(out)[0] + ".blend")
print("OK ->", out)
