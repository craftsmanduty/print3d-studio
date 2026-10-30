"""Packages the add-on as an installable Blender extension .zip -> dist/.

Usage (Blender's own Python works too):
  blender -b --factory-startup --python tools/package.py
"""
import os
import re
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "print3d_studio")
SKIP_DIRS = {"__pycache__", "user_data"}

with open(os.path.join(SRC, "blender_manifest.toml"), encoding="utf-8") as f:
    version = re.search(r'^version\s*=\s*"([^"]+)"', f.read(), re.M).group(1)

os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
out = os.path.join(ROOT, "dist", "print3d_studio-%s.zip" % version)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for base, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            full = os.path.join(base, fn)
            z.write(full, os.path.relpath(full, SRC))
print("Created:", out)
