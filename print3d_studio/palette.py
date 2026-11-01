"""Loads the filament and material palettes from JSON files.

The built-in palette lives in `data/`; user additions are written to
`user_filaments.json` / `user_materials.json` in a separate user folder,
so they survive add-on updates.
"""
import json
import os

from . import utils

_DIR = os.path.dirname(os.path.abspath(__file__))

DATA = {"types": {}, "materials": {}, "mat_order": [], "categories": []}

# Lists returned by EnumProperty callbacks must be kept alive.
_ENUM = {"types": [], "colors": {}, "cats": [], "mats_by_cat": {}, "all_mats": [], "mat_index": {},
         "room": {}}
_EMPTY = [("NONE", "-", "", 0)]


def user_dir():
    try:
        import bpy
        p = bpy.utils.extension_path_user(__package__, path="", create=True)
        if p:
            return p
    except Exception:
        pass
    p = os.path.join(_DIR, "user_data")
    os.makedirs(p, exist_ok=True)
    return p


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print("[3D Print Studio] could not read JSON:", path, e)
        return {}


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load():
    base = _read(os.path.join(_DIR, "data", "filaments.json"))
    user = _read(os.path.join(user_dir(), "user_filaments.json"))
    types = {}
    for k, t in base.get("types", {}).items():
        types[k] = dict(t, colors=list(t.get("colors", [])))
    for k, t in user.get("types", {}).items():
        if k not in types:
            types[k] = dict(t, colors=list(t.get("colors", [])))
    for k, cols in user.get("colors", {}).items():
        if k in types:
            types[k]["colors"].extend(cols)
    DATA["types"] = types

    mats, order, cats = {}, [], []
    base_m = _read(os.path.join(_DIR, "data", "materials.json")).get("materials", [])
    user_m = _read(os.path.join(user_dir(), "user_materials.json")).get("materials", [])
    for m in base_m + user_m:
        if m["id"] not in mats:
            order.append(m["id"])
        mats[m["id"]] = m
        if m.get("category", "Other") not in cats:
            cats.append(m.get("category", "Other"))
    DATA["materials"], DATA["mat_order"], DATA["categories"] = mats, order, cats
    _rebuild_enums()


def _rebuild_enums():
    _ENUM["types"] = [(k, t.get("label", k), "", i) for i, (k, t) in enumerate(DATA["types"].items())]
    _ENUM["colors"] = {
        k: [("c%d" % i, c["name"], c.get("hex") or " / ".join(c.get("hexes", [])), i)
            for i, c in enumerate(t["colors"])]
        for k, t in DATA["types"].items()
    }
    _ENUM["cats"] = [(c, c, "", i) for i, c in enumerate(DATA["categories"])]
    _ENUM["mat_index"] = {mid: i for i, mid in enumerate(DATA["mat_order"])}
    by_cat = {}
    for i, mid in enumerate(DATA["mat_order"]):
        m = DATA["materials"][mid]
        by_cat.setdefault(m.get("category", "Other"), []).append((mid, m["name"], "", i))
    _ENUM["mats_by_cat"] = by_cat
    _ENUM["all_mats"] = [
        (mid, "%s > %s" % (DATA["materials"][mid].get("category", ""), DATA["materials"][mid]["name"]), "", i)
        for i, mid in enumerate(DATA["mat_order"])
    ]
    _ENUM["room"] = {role: _room_items(role) for role in ("wall", "floor")}


def is_external(m):
    """True for a material whose maps come from the local asset library (downloaded,
    usually licensed) rather than from textures that ship with the add-on."""
    lib = m.get("params", {}).get("lib")
    return bool(lib) and not os.path.isdir(os.path.join(_DIR, "assets", "textures", lib))


_ROOM_CATS = ("Walls & Floors", "Stone & Concrete", "Wood")


def _room_items(role):
    """Wall or floor choices: the add-on's own materials for that role, then the library
    textures under their own heading."""
    own, ext = [], []
    for i, mid in enumerate(DATA["mat_order"]):
        m = DATA["materials"][mid]
        if is_external(m):
            if m.get("category") in _ROOM_CATS:
                ext.append((mid, m["name"], "", i))
        elif m.get("room") == role:
            own.append((mid, m["name"], "", i))
    if ext:
        own += [("", "Asset Library (local only)", "")] + ext
    return own


# --- queries ---------------------------------------------------------------
def get_type(key):
    return DATA["types"].get(key) or next(iter(DATA["types"].values()))


def get_color_entry(type_key, color_id):
    cols = get_type(type_key)["colors"]
    try:
        idx = int(color_id[1:])
    except (TypeError, ValueError):
        idx = 0
    return cols[min(idx, len(cols) - 1)] if cols else {"name": "White", "hex": "#F0F0F0"}


def colors_linear(entry):
    hexes = entry.get("hexes") or [entry.get("hex", "#F0F0F0")]
    return [utils.hex_to_linear(h) for h in hexes]


def material_spec(mid):
    return DATA["materials"].get(mid)


def mat_number(mid):
    return _ENUM["mat_index"].get(mid, 0)


# --- enum callbacks -------------------------------------------------------
def enum_types(self, context):
    return _ENUM["types"] or _EMPTY


def enum_colors(self, context):
    return _ENUM["colors"].get(self.filament_type) or _EMPTY


def enum_nf_colors_dummy(self, context):
    return _EMPTY


def enum_categories(self, context):
    return _ENUM["cats"] or _EMPTY


def enum_mats_in_cat(self, context):
    return _ENUM["mats_by_cat"].get(self.mat_category) or _EMPTY


def enum_all_mats(self, context):
    return _ENUM["all_mats"] or _EMPTY


def enum_wall_mats(self, context):
    return _ENUM["room"].get("wall") or _EMPTY


def enum_floor_mats(self, context):
    return _ENUM["room"].get("floor") or _EMPTY


# --- user additions -------------------------------------------------------
def add_user_color(type_key, name, hexcode):
    path = os.path.join(user_dir(), "user_filaments.json")
    data = _read(path)
    data.setdefault("colors", {}).setdefault(type_key, []).append({"name": name, "hex": hexcode})
    _write(path, data)
    load()


def add_user_material(entry):
    path = os.path.join(user_dir(), "user_materials.json")
    data = _read(path)
    data.setdefault("materials", []).append(entry)
    _write(path, data)
    load()


load()
