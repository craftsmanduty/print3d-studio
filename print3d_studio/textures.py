"""Free CC0 photo textures from Poly Haven (https://polyhaven.com), downloaded on first use.

Maps are cached in the add-on's user folder, so every texture is fetched only once per
resolution. Nothing is downloaded while Blender's "Allow Online Access" is off.
"""
import json
import os
import urllib.request

from . import palette

API = "https://api.polyhaven.com/files/%s"
MAPS = {"diff": "Diffuse", "nor": "nor_gl", "rough": "Rough"}
HEADERS = {"User-Agent": "Blender-3D-Print-Studio-Addon"}


class OfflineError(RuntimeError):
    pass


def cache_dir(asset, res):
    return os.path.join(palette.user_dir(), "textures", asset, res)


def _online_allowed():
    try:
        import bpy
        return bool(getattr(bpy.app, "online_access", True))
    except Exception:
        return True


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def ensure(asset, res="4k"):
    """Returns {"diff": path, "nor": path, "rough": path} for a Poly Haven texture, downloading
    missing maps. Falls back to any already cached resolution when offline."""
    folder = cache_dir(asset, res)
    paths = {k: os.path.join(folder, "%s_%s_%s.jpg" % (asset, k, res)) for k in MAPS}
    if all(os.path.isfile(p) for p in paths.values()):
        return paths
    if not _online_allowed():
        for other in ("8k", "4k", "2k", "1k"):
            alt = {k: os.path.join(cache_dir(asset, other), "%s_%s_%s.jpg" % (asset, k, other)) for k in MAPS}
            if all(os.path.isfile(p) for p in alt.values()):
                return alt
        raise OfflineError("Enable Preferences > System > Network > Allow Online Access "
                           "to download the '%s' texture from Poly Haven" % asset)
    files = json.loads(_get(API % asset))
    os.makedirs(folder, exist_ok=True)
    for key, ph_name in MAPS.items():
        if os.path.isfile(paths[key]):
            continue
        url = files[ph_name][res]["jpg"]["url"]
        data = _get(url, timeout=300)
        tmp = paths[key] + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, paths[key])
    return paths


def resolution():
    """Texture resolution chosen in the add-on preferences (default 4K)."""
    try:
        import bpy
        return bpy.context.preferences.addons[__package__].preferences.texture_res
    except Exception:
        return os.environ.get("P3D_TEXTURE_RES", "4k")
