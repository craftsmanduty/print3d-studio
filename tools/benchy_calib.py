"""Calibration render: a real STL at 1:1 scale on a paper sweep, like a product photo.

The model is imported in millimeters and scaled by exactly 0.001 (One-Click Scene), the layer
height stays 0.2 mm; nothing is exaggerated. Also writes a 100 % crop next to the image so the
layer lines can be judged at full resolution.

  blender -b --factory-startup --python tools/benchy_calib.py -- <stl> <out.png>
          [color_hex] [backdrop_hex] [azim] [elev] [samples] [width] [lens] [fstop] [margin]
"""
import math
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
stl, out = os.path.abspath(argv[0]), os.path.abspath(argv[1])
color = argv[2] if len(argv) > 2 else "#1F3F7A"
backdrop = argv[3] if len(argv) > 3 else "#C9AE90"
azim = float(argv[4]) if len(argv) > 4 else -35.0
elev = float(argv[5]) if len(argv) > 5 else 16.0
samples = int(argv[6]) if len(argv) > 6 else 512
width = int(argv[7]) if len(argv) > 7 else 2400
lens = float(argv[8]) if len(argv) > 8 else 100.0
fstop = float(argv[9]) if len(argv) > 9 else 8.0
margin = float(argv[10]) if len(argv) > 10 else 1.12

import print3d_studio  # noqa: E402
from print3d_studio import utils  # noqa: E402
from print3d_studio.scene import camera  # noqa: E402

print3d_studio.register()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

bpy.ops.wm.stl_import(filepath=stl)
ob = bpy.context.active_object
print("imported dims (file units):", tuple(round(v, 2) for v in ob.dimensions), "tris:", len(ob.data.polygons))

sc = bpy.context.scene
s = sc.p3d
s.quick_preset = 'STUDIO'
s.cove_color = utils.hex_to_linear(backdrop)
s.render_quality = 'FINAL'
p = ob.p3d
p.filament_type = 'PLA_BASIC'
p.use_custom_color = True
p.custom_color = utils.hex_to_linear(color)
p.layer_height = 0.2
p.line_width = 0.42
bpy.ops.p3d.quick_scene()
print("real size (mm):", tuple(round(v * 1000, 2) for v in ob.dimensions))

sc.render.resolution_x, sc.render.resolution_y = width, int(width * 3 / 4)
sc.render.resolution_percentage = 100
s.cam_lens, s.cam_elev, s.cam_azim, s.cam_fstop, s.cam_margin = lens, elev, azim, fstop, margin
camera.setup(bpy.context, s, ob)
sc.cycles.samples = samples
sc.cycles.adaptive_threshold = 0.006
sc.render.filepath = out
bpy.ops.render.render(write_still=True)

# 100 % crop around the image center (where the cabin usually is)
img = bpy.data.images.load(out)
w, h = img.size
px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
cw, ch = 1000, 750
x0, y0 = (w - cw) // 2, (h - ch) // 2 + h // 10
crop = bpy.data.images.new("crop", cw, ch, alpha=True)
crop.pixels.foreach_set(np.ascontiguousarray(px[y0:y0 + ch, x0:x0 + cw]).ravel())
crop.filepath_raw = os.path.splitext(out)[0] + "_crop.png"
crop.file_format = 'PNG'
crop.save()
bpy.ops.wm.save_as_mainfile(filepath=os.path.splitext(out)[0] + ".blend")
print("OK ->", out)
