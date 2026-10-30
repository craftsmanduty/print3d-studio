"""Starts Blender with the add-on loaded straight from this folder (no install needed).

  blender --python tools/dev_start.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import print3d_studio  # noqa: E402

print3d_studio.register()
