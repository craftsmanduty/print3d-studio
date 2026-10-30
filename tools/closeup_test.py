"""Close-up realism check: builds the one-click desk scene and renders a product-style shot
that also shows the cutting mat edge and the desk surface.

  blender -b --factory-startup --python tools/closeup_test.py -- out.png [samples] [filament] [margin] [elev]
"""
import math
import os
import sys

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
out = argv[0] if argv else os.path.join(ROOT, "renders", "closeup.png")
samples = int(argv[1]) if len(argv) > 1 else 256
ftype = argv[2] if len(argv) > 2 else "PLA_BASIC"
margin = float(argv[3]) if len(argv) > 3 else 2.6
elev = float(argv[4]) if len(argv) > 4 else 18.0

import print3d_studio  # noqa: E402
print3d_studio.register()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.mesh.primitive_monkey_add(size=60)
mk = bpy.context.active_object
mod = mk.modifiers.new("s", 'SUBSURF')
mod.levels = mod.render_levels = 2
bpy.ops.object.modifier_apply(modifier="s")

s = bpy.context.scene.p3d
s.quick_preset = 'DESK_DAY'
s.render_quality = 'PREVIEW'
s.res_preset = 'LAND_HD'
mk.p3d.filament_type = ftype
mk.p3d.filament_color = 'c4' if ftype == 'PLA_BASIC' else 'c0'
bpy.ops.p3d.quick_scene()

# move the model towards the mat corner so the mat edge and the desk are in frame
mk.location.x += 0.17
mk.location.y -= 0.08
s.cam_margin = margin
s.cam_elev = elev
s.cam_azim = -25
s.cam_lens = 70
s.cam_fstop = 5.6
print3d_studio.scene.camera.setup(bpy.context, s, mk)

sc = bpy.context.scene
sc.cycles.samples = samples
sc.cycles.adaptive_threshold = 0.01
sc.render.resolution_x, sc.render.resolution_y = 1280, 853
sc.render.resolution_percentage = 100
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(out)[0] + ".blend")
print("OK ->", out)
