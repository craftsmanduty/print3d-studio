"""Local asset library: PBR textures and ready-made models from downloaded zips
(Poliigon / ambientCG style file names).

Zips are unpacked into `<user folder>/library/<AssetName>/`. A zip with a .blend file is a
model and shows up under Props > My Asset Library; a zip with only maps is a texture and
becomes a material that the "pbr" builder can use. Texture maps larger than the chosen
resolution are scaled down once on import to save GPU memory.

These files often come with licenses that forbid redistribution, so they are never stored
inside the add-on or its repository. Only our own and CC0 assets ship with the add-on, in
`assets/textures` and `assets/models`, and they are found the same way.
"""
import os
import re
import shutil
import zipfile

from . import palette

# map kind -> file name tokens (upper case), most preferred first
KINDS = {
    "col": ("BASECOLOR", "COL", "COLOR", "ALBEDO", "DIFFUSE", "DIFF"),
    "nor": ("NORMAL", "NRM", "NOR", "NORMALGL", "NOR_GL"),
    "rough": ("ROUGHNESS", "ROUGH"),
    "gloss": ("GLOSS", "GLOSSINESS"),
    "metal": ("METALLIC", "METALNESS", "METAL"),
    "disp": ("DISPLACEMENT", "DISP", "HEIGHT"),
    "bump": ("BUMP",),
    "ao": ("AO", "AMBIENTOCCLUSION"),
    "mask": ("MASK", "OPACITY", "ALPHAMASKED", "ALPHA"),
    "sss": ("SSS", "SCATTERING"),
}
_TOKEN = {t: k for k, ts in KINDS.items() for t in ts}
_RES = re.compile(r"^(\d+)K$", re.I)
IMG_EXT = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr")


def root():
    return os.path.join(palette.user_dir(), "library")


BUILTIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "textures")
BUILTIN_MODELS = os.path.join(os.path.dirname(BUILTIN), "models")


def roots():
    """Every folder searched for library assets: the user library, then the textures and
    models that ship with the add-on (our own or CC0, free to redistribute)."""
    dirs = [root(), BUILTIN, BUILTIN_MODELS]
    env = os.environ.get("P3D_LIBRARY")
    if env:
        dirs.append(env)
    return [d for d in dirs if os.path.isdir(d)]


def asset_name(zip_path):
    stem = os.path.splitext(os.path.basename(zip_path))[0]
    return re.sub(r"\s*\(\d+k\)$", "", stem, flags=re.I).strip()


def find(name):
    for d in roots():
        p = os.path.join(d, name)
        if os.path.isdir(p):
            return p
    return None


def classify(fname):
    """('col'|'nor'|..., resolution in K or 0, is_16bit) for a map file name, or None."""
    stem, ext = os.path.splitext(os.path.basename(fname))
    if ext.lower() not in IMG_EXT or "preview" in stem.lower():
        return None
    toks = stem.split("_")
    res, kind, deep = 0, None, False
    for i, t in enumerate(toks):
        m = _RES.match(t)
        if m:
            res = int(m.group(1))
            if i > 0 and kind is None:
                kind, deep = _kind(toks[i - 1])
    if kind is None:
        kind, deep = _kind(toks[-1])
    if kind is None:
        return None
    if res == 0:
        m = _RES.match(os.path.basename(os.path.dirname(fname)))
        res = int(m.group(1)) if m else 0
    deep = deep or ext.lower() in (".tif", ".tiff", ".exr")
    return kind, res, deep


def _kind(tok):
    t = tok.upper()
    deep = t.endswith("16")
    if deep:
        t = t[:-2]
    return _TOKEN.get(t), deep


def pick_maps(files, want_k):
    """Chooses one file per map kind: 8-bit over 16-bit, then the resolution closest to
    `want_k` (preferring the next larger one)."""
    best = {}
    for f in files:
        c = classify(f)
        if c is None:
            continue
        kind, res, deep = c
        key = (deep, abs(res - want_k) + (0.5 if res < want_k else 0.0))
        if kind not in best or key < best[kind][0]:
            best[kind] = (key, f, res)
    return {k: (f, res) for k, (_, f, res) in best.items()}


def _downscale(path, size):
    """Scales an image file down in place to `size` px on its long side (needs bpy)."""
    import bpy
    img = bpy.data.images.load(path)
    try:
        w, h = img.size
        if max(w, h) <= size:
            return
        f = size / max(w, h)
        img.scale(max(1, round(w * f)), max(1, round(h * f)))
        img.filepath_raw = path
        img.file_format = 'PNG' if path.lower().endswith(".png") else 'JPEG'
        img.save()
    finally:
        bpy.data.images.remove(img)


def import_zip(zip_path, want_k=4, dest_root=None):
    """Unpacks one asset zip into the library. Returns (name, 'model'|'texture', folder)."""
    name = asset_name(zip_path)
    dest = os.path.join(dest_root or root(), name)
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.namelist() if not m.endswith("/")]
        is_model = any(m.lower().endswith(".blend") for m in members)
        if is_model:
            # the .blend references its maps relative to itself: keep the flat layout
            keep = [m for m in members if "preview" not in os.path.basename(m).lower()
                    or m.lower().endswith(".blend")]
        else:
            picked = pick_maps(members, want_k)
            if "col" not in picked:
                raise ValueError("no .blend model or color map found - not an asset zip")
            keep = [f for f, _ in picked.values()]
        os.makedirs(dest, exist_ok=True)
        for m in keep:
            out = os.path.join(dest, os.path.basename(m))
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                continue
            with z.open(m) as src, open(out + ".part", "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            os.replace(out + ".part", out)
            if not is_model:
                c = classify(m)
                if c and c[1] > want_k:
                    _downscale(out, want_k * 1024)
        prev = [m for m in members if "preview" in m.lower() and m.lower().endswith((".png", ".jpg"))]
        if prev:
            out = os.path.join(dest, "preview" + os.path.splitext(prev[0])[1].lower())
            if not os.path.isfile(out):
                with z.open(prev[0]) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
    return name, ("model" if is_model else "texture"), dest


def texture_maps(name):
    """{kind: path} for an imported texture asset, or None if it is not in the library."""
    folder = find(name)
    if folder is None:
        return None
    files = [os.path.join(folder, f) for f in os.listdir(folder)]
    maps = {k: f for k, (f, _) in pick_maps(files, 4).items()}
    return maps if "col" in maps else None


# name keyword -> (category, real-world size of one texture tile in m)
_GUESS = (
    (("floor", "parquet", "laminate", "plank"), "Walls & Floors", 2.0),
    (("brick", "tile", "mosaic", "plaster", "wallpaper"), "Walls & Floors", 1.0),
    (("wood", "veneer"), "Wood", 1.0),
    (("metal", "steel", "iron", "brass", "copper", "alumin", "chrome", "gold"), "Metal", 1.0),
    (("fabric", "linen", "cotton", "wool", "velvet", "leather", "rattan", "weave", "carpet"),
     "Fabric & Leather", 0.5),
    (("stone", "concrete", "asphalt", "marble", "granite", "rock", "gravel"), "Stone & Concrete", 2.0),
)


def _pretty(name):
    n = re.sub(r"^(Poliigon_)", "", name)
    n = re.sub(r"_?\d+$", "", n)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", n).replace("_", " ").strip()


def register_texture(name):
    """Adds an imported texture to the user material palette (builder "pbr") unless a
    palette entry already uses it. Returns the material id."""
    for mid, m in palette.DATA["materials"].items():
        if m.get("params", {}).get("lib") == name:
            return mid
    low = name.lower()
    cat, size = "Other", 1.0
    for keys, c, s in _GUESS:
        if any(k in low for k in keys):
            cat, size = c, s
            break
    mid = "lib_" + re.sub(r"\W+", "_", low).strip("_")
    palette.add_user_material({"id": mid, "name": _pretty(name) + " (Library)", "category": cat,
                               "builder": "pbr", "params": {"lib": name, "size": size}})
    return mid


def model_files():
    """Every .blend in the library folders (one level of sub folders)."""
    out = []
    for d in roots():
        for sub in sorted(os.listdir(d)):
            p = os.path.join(d, sub)
            if os.path.isdir(p):
                out += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.lower().endswith(".blend")]
    return out


class MissingAsset(RuntimeError):
    pass


def model_collection(path, names):
    """The collection of a library .blend that holds the model (named like its folder)."""
    stem = os.path.basename(os.path.dirname(path))
    return next((n for n in names if n == stem), names[-1])


def model_path(name):
    folder = find(name)
    blends = [f for f in os.listdir(folder) if f.lower().endswith(".blend")] if folder else []
    if not blends:
        raise MissingAsset("'%s' is not in the asset library - import its zip with "
                           "Props > My Asset Library > Import Asset Zips" % name)
    return os.path.join(folder, blends[0])


def object_names(name):
    """Names of the objects in the library model `name` (without loading them)."""
    import bpy
    with bpy.data.libraries.load(model_path(name), link=False) as (src, _):
        return list(src.objects)


def append_objects(name, names, coll, parent):
    """Appends only the objects `names` of the library model `name` (a set of many props, such
    as single books), linked into `coll` and parented to `parent`. Returns them in that order."""
    import bpy
    with bpy.data.libraries.load(model_path(name), link=False) as (src, dst):
        dst.objects = [n for n in names if n in src.objects]
    objs = [o for o in dst.objects if o is not None]
    for o in objs:
        coll.objects.link(o)
        o.parent = parent
    fix_missing_images(bpy.data.images)
    return objs


def append_model(name, coll, parent):
    """Appends the library model `name` into `coll`, parented to `parent` at its origin."""
    import bpy
    path = model_path(name)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = [model_collection(path, list(src.collections))]
    tmp = dst.collections[0]
    objs = list(tmp.all_objects)
    for o in objs:
        coll.objects.link(o)
        if o.parent is None:
            o.parent = parent
    bpy.data.collections.remove(tmp)
    fix_missing_images(bpy.data.images)
    return objs


def fix_missing_images(images):
    """Points images whose file is missing to the same map at another resolution
    (some downloads ship a .blend that references a resolution the zip lacks)."""
    import bpy
    for img in images:
        if img is None or img.packed_file is not None or img.source != 'FILE':
            continue
        path = bpy.path.abspath(img.filepath, library=img.library)
        if not path or os.path.isfile(path):
            continue
        folder, base = os.path.split(path)
        parts = re.split(r"_\d+K(?=[_.])", base, flags=re.I)
        pat = re.compile(r"_\d+K".join(re.escape(x) for x in parts), re.I)
        try:
            cands = [f for f in os.listdir(folder) if pat.fullmatch(f)]
        except OSError:
            continue
        if cands:
            cands.sort(key=lambda f: -int(re.search(r"_(\d+)K", f, re.I).group(1)))
            img.filepath = os.path.join(folder, cands[0])
            img.reload()
