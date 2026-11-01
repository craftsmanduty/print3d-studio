"""Imports downloaded asset zips (Poliigon / ambientCG style) into the local asset library.

Usage:
  blender -b --factory-startup --python tools/import_assets.py -- <library folder> <res K> a.zip b.zip ...

The library folder is normally `<add-on user folder>/library` (Preferences > Add-ons >
3D Print Studio shows the user folder); the panel's Import Assets button does the same.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from print3d_studio import library  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
dest, want = args[0], int(args[1])
for z in args[2:]:
    name, kind, folder = library.import_zip(z, want, dest)
    print("IMPORTED %-8s %s" % (kind, name))
