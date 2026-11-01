"""Room with the library floor and library models, seen from a wide camera.

Uses the models that ship with the add-on (assets/models); P3D_LIBRARY can add a folder of
imported assets (see tools/import_assets.py).

Usage:
  blender -b --factory-startup --python tools/library_test.py -- out.png [samples] [Model1,Model2,...]
"""
import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
argv = sys.argv[sys.argv.index("--") + 1:]
out = os.path.abspath(argv[0])
samples = int(argv[1]) if len(argv) > 1 else 128
wanted = argv[2].split(",") if len(argv) > 2 else [
    "wooden_display_shelves_01", "modern_coffee_table_02", "potted_plant_02",
    "GreenChair_01", "street_lamp_02"]
places = [(-0.3, 1.2, 0.0, 0.0), (-0.3, 0.1, 0.0, 0.0), (1.35, 1.45, 0.0, 0.0),
          (1.2, 0.0, 0.0, 1.9), (-1.6, 1.45, 0.0, 0.0), (0.6, -0.6, 0.0, 0.0)]

import print3d_studio  # noqa: E402
print3d_studio.register()
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)

sc = bpy.context.scene
s = sc.p3d
s.room_w, s.room_d = 4.5, 4.0
bpy.ops.p3d.build_room()
bpy.ops.p3d.lighting()

bpy.ops.p3d.asset_refresh()
items = [e[0] for e in print3d_studio.properties._ASSETS]
for name, (x, y, z, rz) in zip(wanted, places):
    key = next((k for k in items if os.path.basename(os.path.dirname(k.split("::")[0])) == name), None)
    if key is None:
        print("MISSING", name)
        continue
    sc.cursor.location = (x, y, z)
    s.asset_item = key
    before = set(bpy.data.objects)
    bpy.ops.p3d.asset_append()
    for o in set(bpy.data.objects) - before:
        if o.parent is None:
            o.rotation_euler.z += rz
    print("APPENDED", name)

missing = [i.filepath for i in bpy.data.images if i.source == 'FILE' and i.packed_file is None
           and i.filepath and not os.path.isfile(bpy.path.abspath(i.filepath, library=i.library))]
print("MISSING IMAGES", missing)

cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
sc.collection.objects.link(cam)
cam.data.lens = 24
cam.location = (0.2, -1.95, 1.25)
d = Vector((0.0, 1.2, 0.45)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam
sc.render.engine = 'CYCLES'
print3d_studio.scene.render.enable_gpu(sc)
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
print("OK ->", out)
