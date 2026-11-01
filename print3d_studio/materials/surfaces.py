"""Material builders for everyday surfaces (procedural, plus scanned photo textures).

Scales are in real-world meters, so objects must be at real size.
To add a builder, write a function decorated with @builder("name") and use
"builder": "name" in data/materials.json.
"""
import json
import math
import os

import bpy

from .. import palette, utils
from ..nodes import NB

BUILDERS = {}


def builder(name):
    def deco(fn):
        BUILDERS[name] = fn
        return fn
    return deco


class P(dict):
    def c(self, k, d):
        return utils.hex_to_linear(self.get(k, d))

    def f(self, k, d):
        return float(self.get(k, d))


def get(mat_id, relief=False):
    """Returns the palette material, building it if needed. `relief` asks for the variant
    with true displacement (for materials that have a `displace` depth): it only looks right
    on objects that get adaptive subdivision, see `add_relief`."""
    spec = palette.material_spec(mat_id)
    if spec is None:
        spec = {"id": mat_id, "name": mat_id, "builder": "plastic", "params": {}}
    params = spec.get("params", {})
    if relief and params.get("displace"):
        return make("P3D_%s_Relief" % mat_id, spec["builder"], dict(params, relief=True))
    return make("P3D_" + mat_id, spec["builder"], params)


def add_relief(obj):
    """Adaptive subdivision for an object whose material has true displacement (Cycles
    dices it to about a pixel per micro face at render time, so the mesh stays light)."""
    if not any(m is not None and m.get("p3d_relief") for m in obj.data.materials):
        return
    mod = obj.modifiers.new("Relief", 'SUBSURF')
    mod.subdivision_type = 'SIMPLE'
    mod.use_adaptive_subdivision = True
    mod.adaptive_pixel_size = 1.5


def make(name, builder_name, params, rebuild=False):
    # rebuild materials saved in a .blend when their palette entry has changed since
    sig = json.dumps([builder_name, params], sort_keys=True)
    mat = bpy.data.materials.get(name)
    if mat is not None and not rebuild and mat.get("p3d_sig") == sig:
        return mat
    mat = utils.node_material(name, mat)
    mat["p3d_sig"] = sig
    nb = NB(mat.node_tree)
    fn = BUILDERS.get(builder_name, BUILDERS["plastic"])
    nb.displacement = None
    bsdf = fn(nb, P(params))
    out = nb.output(bsdf.outputs[0])
    if nb.displacement is not None:
        nb.links.new(nb.displacement, out.inputs['Displacement'])
    mat.displacement_method = 'BOTH' if nb.displacement is not None else 'BUMP'
    mat["p3d_relief"] = nb.displacement is not None
    base = params.get("base") or params.get("light") or params.get("c1") or "#CCCCCC"
    mat.diffuse_color = (*utils.hex_to_linear(base), 1.0)
    return mat


# ---------------------------------------------------------------------------
def _board_random(nb, co, board_len, board_w, offset=0.37, gap=0.0002):
    """Per-board random value (0.55..1) and glue/joint line mask, boards run along X."""
    br = nb.new('ShaderNodeTexBrick', offset=offset, offset_frequency=1, squash=1.0)
    nb.inp(br, "Vector", co)
    nb.inp(br, "Color1", (1.0, 1.0, 1.0))
    nb.inp(br, "Color2", (0.55, 0.55, 0.55))
    nb.inp(br, "Mortar", (0.0, 0.0, 0.0))
    nb.inp(br, "Scale", 1.0)
    nb.inp(br, "Mortar Size", gap)
    nb.inp(br, "Mortar Smooth", 0.3)
    nb.inp(br, "Brick Width", board_len)
    nb.inp(br, "Row Height", board_w)
    return br.outputs['Color'], br.outputs['Fac']


def _wood_core(nb, co, p, board=None):
    """Straight-grained sawn wood: growth rings, cathedral waviness, fibre streaks and pores.

    Returns (color, height, latewood, pores). `board` is a per-board random socket.
    """
    light, dark = p.c('light', '#C8A06A'), p.c('dark', '#8A6234')
    if board is not None:
        co = nb.vadd(co, nb.vscale(nb.vec(1.3, 3.1, 1.7), board))
    # ring radius around an axis parallel to X, far below the surface -> nearly straight lines
    yz = nb.vsub(nb.vmul(co, nb.vec(0.0, 1.0, 1.0)), nb.vec(0.0, p.f('offset_y', 0.37), p.f('offset_z', -0.23)))
    r = nb.length(yz)
    wav = nb.noise(nb.vmul(co, nb.vec(1.2, 7.0, 7.0)), 1.0, detail=3.0).outputs['Fac']
    r = nb.add(r, nb.mul(nb.sub(wav, 0.5), p.f('figure', 0.012)))
    rings = p.f('rings', 230.0)
    # irregular ring widths (good and bad growth years)
    years = nb.noise(nb.vmul(co, nb.vec(0.4, 60.0, 60.0)), 1.0, detail=2.0).outputs['Fac']
    rr = nb.add(nb.mul(r, rings), nb.mul(years, 6.0))
    t = nb.math('FRACT', rr)
    width = nb.maprange(nb.white1d(nb.math('FLOOR', rr)), 0.0, 1.0, 0.72, 0.9)
    late = nb.maprange(nb.sub(t, width), -0.12, 0.0, 0.0, 1.0, smooth=True)
    late = nb.mul(late, nb.maprange(t, 0.95, 1.0, 1.0, 0.0))
    late = nb.mul(late, nb.maprange(nb.white1d(nb.add(nb.math('FLOOR', rr), 7.3)), 0.0, 1.0, 0.35, 1.0))
    col = nb.mix_col(nb.mul(late, 0.6), light, dark)

    fib = nb.noise(nb.vmul(co, nb.vec(2.5, 700.0, 700.0)), 1.0, detail=5.0, rough=0.6).outputs['Fac']
    col = nb.vscale(col, nb.maprange(fib, 0.3, 0.7, 0.8, 1.08))
    streak = nb.noise(nb.vmul(co, nb.vec(1.0, 90.0, 90.0)), 1.0, detail=3.0).outputs['Fac']
    col = nb.vscale(col, nb.maprange(streak, 0.3, 0.7, 0.9, 1.06))
    tone = nb.noise(nb.vmul(co, nb.vec(0.8, 4.0, 4.0)), 1.0, detail=2.0).outputs['Fac']
    col = nb.vscale(col, nb.maprange(tone, 0.3, 0.7, 0.9, 1.08))
    if board is not None:
        col = nb.vscale(col, nb.maprange(board, 0.55, 1.0, 0.85, 1.06))

    # open pores: short dark dashes along the grain, denser in latewood
    pn = nb.noise(nb.vmul(co, nb.vec(45.0, 2600.0, 2600.0)), 1.0, detail=1.0).outputs['Fac']
    pores = nb.mul(nb.maprange(pn, 0.6, 0.7, 0.0, 1.0), nb.add(0.35, nb.mul(late, 0.65)))
    pores = nb.mul(pores, p.f('pores', 1.0))
    col = nb.vscale(col, nb.maprange(pores, 0.0, 1.0, 1.0, 0.55))

    height = nb.sub(nb.add(nb.mul(late, 0.25), nb.mul(fib, 0.35)), nb.mul(pores, 1.2))
    return col, height, late, pores


def _wood_shader(nb, col, height, late, pores, p, extra_h=None, extra_rough=None):
    rough = nb.add(p.f('rough', 0.5), nb.mul(late, 0.06))
    rough = nb.add(rough, nb.mul(pores, 0.25))
    smudge = nb.noise(nb.obj, 6.0, detail=4.0).outputs['Fac']
    rough = nb.add(rough, nb.mul(nb.sub(smudge, 0.5), 0.12))
    if extra_rough is not None:
        rough = nb.add(rough, extra_rough)
    h = height if extra_h is None else nb.add(height, extra_h)
    nrm = nb.bump(h, 0.00012 * p.f('relief', 1.0), 1.0)
    return nb.principled(base=col, rough=rough, normal=nrm, spec=0.42,
                         coat=p.f('coat', 0.0), coat_rough=p.f('coat_rough', 0.25), coat_normal=nrm,
                         sheen=0.05)


@builder("wood")
def wood(nb, p):
    board = None
    joint = None
    if p.f('stave_w', 0.075) > 0:
        board, joint = _board_random(nb, nb.obj, p.f('stave_len', 2.6), p.f('stave_w', 0.075))
    col, height, late, pores = _wood_core(nb, nb.obj, p, board)
    extra_h = None
    if joint is not None:
        col = nb.vscale(col, nb.maprange(joint, 0.0, 1.0, 1.0, 0.7))
        extra_h = nb.mul(joint, -0.5)
    return _wood_shader(nb, col, height, late, pores, p, extra_h)


@builder("parquet")
def parquet(nb, p):
    board, groove = _board_random(nb, nb.obj, p.f('plank_len', 0.9), p.f('plank_w', 0.14), gap=0.0012)
    col, height, late, pores = _wood_core(nb, nb.obj, p, board)
    col = nb.vscale(col, nb.maprange(groove, 0.0, 1.0, 1.0, 0.25))
    return _wood_shader(nb, col, height, late, pores, p, extra_h=nb.mul(groove, -6.0),
                        extra_rough=nb.mul(groove, 0.4))


@builder("photo")
def photo(nb, p):
    """Scanned PBR texture (Poly Haven, CC0) at its true real-world size, with procedural
    sub-texel fibres and pores so close-ups stay sharp. Falls back to the procedural
    builder named in `fallback` when the texture cannot be downloaded."""
    from .. import textures
    try:
        maps = textures.ensure(p['tex'], textures.resolution())
    except Exception as e:  # offline, no network permission, server error ...
        print("3D Print Studio: texture '%s' unavailable (%s), using procedural fallback" % (p.get('tex'), e))
        return BUILDERS[p.get('fallback', 'wood')](nb, p)

    uv = nb.tc.outputs['UV']                                   # 1 UV unit = 1 m on our props
    mp = nb.new('ShaderNodeMapping')
    nb.inp(mp, "Vector", uv)
    nb.inp(mp, "Rotation", (0.0, 0.0, math.radians(p.f('rot', 90.0))))
    s = 1.0 / p.f('size', 1.0)
    nb.inp(mp, "Scale", (s, s, s))
    vec = mp.outputs[0]

    def tex(path, color):
        n = nb.new('ShaderNodeTexImage', interpolation='Cubic')
        n.image = bpy.data.images.load(path, check_existing=True)
        if not color:
            n.image.colorspace_settings.name = 'Non-Color'
        nb.inp(n, "Vector", vec)
        return n.outputs['Color']

    col = tex(maps['diff'], True)
    # oil / finish darkens and warms bare wood
    col = nb.mix_col(1.0, col, p.c('tint', '#FFFFFF'), blend='MULTIPLY') if 'tint' in p else col
    rough_map = nb.separate(tex(maps['rough'], False))[0]
    nm = nb.new('ShaderNodeNormalMap')
    nb.inp(nm, "Strength", p.f('normal', 1.0))
    nb.inp(nm, "Color", tex(maps['nor'], False))

    # fibres and pores finer than one texel, running along the grain (texture V axis)
    g = nb.vmul(vec, nb.vec(1.0, 0.04, 1.0))
    fib = nb.noise(g, 2600.0 * p.f('size', 1.0), detail=4.0, rough=0.6).outputs['Fac']
    pn = nb.noise(nb.vmul(vec, nb.vec(1.0, 0.25, 1.0)), 1900.0 * p.f('size', 1.0), detail=1.0).outputs['Fac']
    pores = nb.mul(nb.maprange(pn, 0.66, 0.72, 0.0, 1.0), p.f('pores', 0.6))
    col = nb.vscale(col, nb.maprange(pores, 0.0, 1.0, 1.0, 0.55))
    col = nb.vscale(col, nb.maprange(fib, 0.3, 0.7, 0.94, 1.04))
    micro = nb.sub(nb.mul(fib, 0.4), pores)
    nrm = nb.bump(micro, 0.00003 * p.f('relief', 1.0), 1.0, normal=nm.outputs['Normal'])

    rough = nb.maprange(rough_map, 0.0, 1.0, p.f('rough_min', 0.35), p.f('rough_max', 0.75))
    # pores hold oil and stay dark; they must not scatter more light than the surface
    smudge = nb.noise(nb.obj, 6.0, detail=4.0).outputs['Fac']
    rough = nb.add(rough, nb.mul(nb.sub(smudge, 0.5), 0.1))
    return nb.principled(base=col, rough=rough, normal=nrm, spec=0.42,
                         coat=p.f('coat', 0.0), coat_rough=p.f('coat_rough', 0.3), coat_normal=nrm,
                         sheen=0.05)


@builder("pbr")
def pbr(nb, p):
    """Texture from the local asset library (imported zip) at its real-world size `size` (m).
    Uses whatever maps the set has: color, normal, roughness or gloss, metal, AO, opacity
    mask, displacement/bump (as fine bump when there is no normal map). With `displace` (m)
    the relief variant pushes the low parts (mortar joints) really in."""
    from .. import library
    maps = library.texture_maps(p.get('lib', ''))
    if maps is None:
        print("3D Print Studio: library texture '%s' not imported, using procedural fallback" % p.get('lib'))
        return BUILDERS[p.get('fallback', 'plastic')](nb, p)

    mp = nb.new('ShaderNodeMapping')
    nb.inp(mp, "Vector", nb.tc.outputs['UV'])                  # 1 UV unit = 1 m on our props
    nb.inp(mp, "Rotation", (0.0, 0.0, math.radians(p.f('rot', 0.0))))
    sx = 1.0 / p.f('size', 1.0)
    sy = 1.0 / p.f('size_y', p.f('size', 1.0))                # non-square tiles (plank floors)
    nb.inp(mp, "Scale", (sx, sy, sx))
    vec = mp.outputs[0]

    def tex(kind, color=False):
        n = nb.new('ShaderNodeTexImage', interpolation='Cubic')
        n.image = bpy.data.images.load(maps[kind], check_existing=True)
        if not color:
            n.image.colorspace_settings.name = 'Non-Color'
        nb.inp(n, "Vector", vec)
        return n

    col = tex('col', True).outputs['Color']
    if 'tint' in p:
        col = nb.mix_col(1.0, col, p.c('tint', '#FFFFFF'), blend='MULTIPLY')
    if 'ao' in maps and p.f('ao', 0.0) > 0:
        col = nb.mix_col(p.f('ao', 0.0), col, tex('ao').outputs['Color'], blend='MULTIPLY')
    kw = {'base': col, 'spec': p.f('spec', 0.5)}

    if 'rough' in maps:
        r = nb.separate(tex('rough').outputs['Color'])[0]
    elif 'gloss' in maps:
        r = nb.sub(1.0, nb.separate(tex('gloss').outputs['Color'])[0])
    else:
        r = p.f('rough', 0.5)
    if 'rough_min' in p or 'rough_max' in p:
        r = nb.maprange(r, 0.0, 1.0, p.f('rough_min', 0.0), p.f('rough_max', 1.0))
    kw['rough'] = r
    if 'metal' in p:
        kw['metal'] = p.f('metal', 0.0)
    elif 'metal' in maps:
        kw['metal'] = nb.separate(tex('metal').outputs['Color'])[0]

    nrm = None
    if 'nor' in maps:
        nor_col = tex('nor').outputs['Color']
        nm = nb.new('ShaderNodeNormalMap')
        nb.inp(nm, "Strength", p.f('normal', 1.0))
        nb.inp(nm, "Color", nor_col)
        nrm = nm.outputs['Normal']
        if p.f('seam', 0.0) > 0:
            # board joints are only hairlines in the normal map: where it tilts sharply,
            # darken the color a little and add roughness so the joints read from a distance
            r, g, _ = nb.separate(nor_col)
            tilt = nb.add(nb.math('ABSOLUTE', nb.sub(r, 0.5)), nb.math('ABSOLUTE', nb.sub(g, 0.5)))
            seam = nb.maprange(tilt, 0.02, 0.12, 0.0, 1.0)
            kw['base'] = nb.vscale(kw['base'], nb.sub(1.0, nb.mul(seam, p.f('seam', 0.0))))
            kw['rough'] = nb.add(kw['rough'], nb.mul(seam, 0.3))
    height = 'disp' if 'disp' in maps else ('bump' if 'bump' in maps else None)
    if height and p.get('relief'):
        # true displacement: the top of the height map stays on the surface, the rest sinks in
        dn = nb.new('ShaderNodeDisplacement')
        h = nb.separate(tex(height).outputs['Color'])[0]
        if 'height_range' in p:
            # many height maps use only a narrow band of grey: stretch it so `displace`
            # is the real joint depth
            lo, hi = p['height_range']
            h = nb.maprange(h, lo, hi, 0.0, 1.0)
        nb.inp(dn, "Height", h)
        nb.inp(dn, "Midlevel", 1.0)
        nb.inp(dn, "Scale", p.f('displace', 0.01))
        nb.displacement = dn.outputs[0]
    elif height and (nrm is None or p.f('depth', 0.0) > 0):
        h = nb.separate(tex(height).outputs['Color'])[0]
        nrm = nb.bump(h, p.f('depth', 0.001), 1.0, normal=nrm)
    if nrm is not None:
        kw['normal'] = nrm
    if 'mask' in maps and p.get('use_mask', True):
        kw['alpha'] = nb.separate(tex('mask').outputs['Color'])[0]
    if p.f('coat', 0.0) > 0:
        kw.update(coat=p.f('coat', 0.0), coat_rough=p.f('coat_rough', 0.2))
        if nrm is not None:
            kw['coat_normal'] = nrm
    if p.f('sheen', 0.0) > 0:
        kw['sheen'] = p.f('sheen', 0.0)
    if p.f('trans', 0.0) > 0:
        kw['trans'] = p.f('trans', 0.0)
    return nb.principled(**kw)


def _atlas(p):
    """(maps, sizes from <lib>.json) of a board atlas, or (None, {}) if it is missing."""
    from .. import library
    maps = library.texture_maps(p.get('lib', ''))
    info = {}
    if maps is not None:
        try:
            info = json.load(open(os.path.join(library.find(p['lib']), p['lib'] + ".json")))
        except (OSError, ValueError, KeyError):
            pass
    return maps, info


def _boards(nb, p, maps, count, u, v, seed, edge):
    """Shared end of the board floors: board `u, v` (0..1) shows a random atlas board, at
    random turned 180 degrees and slightly toned; `edge` = distance to the outline in m."""
    pick = nb.math('MINIMUM', nb.math('FLOOR', nb.mul(nb.white1d(seed), count)), count - 1)
    flip = nb.math('GREATER_THAN', nb.white1d(nb.add(seed, 3.7)), 0.5)
    uf = nb.mix_float(flip, u, nb.sub(1.0, u))
    vf = nb.mix_float(flip, v, nb.sub(1.0, v))
    vec = nb.vec(nb.math('DIVIDE', nb.add(pick, uf), count), vf, 0.0)

    def tex(kind, color=False):
        n = nb.new('ShaderNodeTexImage', interpolation='Linear', extension='EXTEND')
        n.image = bpy.data.images.load(maps[kind], check_existing=True)
        if not color:
            n.image.colorspace_settings.name = 'Non-Color'
        nb.inp(n, "Vector", vec)
        return n.outputs['Color']

    groove = nb.maprange(edge, 0.0, p.f('groove_mm', 1.2) * 0.001, 1.0, 0.0, smooth=True)
    col = tex('col', True)
    if 'tint' in p:
        col = nb.mix_col(1.0, col, p.c('tint', '#FFFFFF'), blend='MULTIPLY')
    tone = nb.maprange(nb.white1d(nb.add(seed, 7.1)), 0.0, 1.0, 0.94, 1.06)
    col = nb.vscale(col, tone)
    if 'grout' in p:                                          # tiles: filled joints
        col = nb.mix_col(groove, col, p.c('grout', '#3A2C22'))
    else:                                                     # boards: shaded bevel
        col = nb.vscale(col, nb.sub(1.0, nb.mul(groove, 0.35)))
    kw = {'base': col, 'spec': 0.5}
    rough = nb.separate(tex('rough'))[0] if 'rough' in maps else p.f('rough', 0.45)
    kw['rough'] = nb.add(rough, nb.mul(groove, 0.3))
    nrm = None
    if 'nor' in maps:
        n = tex('nor')
        r, g, b = nb.separate(n)
        turned = nb.vec(nb.sub(1.0, r), nb.sub(1.0, g), b)  # board turned 180 degrees
        nm = nb.new('ShaderNodeNormalMap')
        nb.inp(nm, "Strength", p.f('normal', 1.0))
        nb.inp(nm, "Color", nb.mix_col(flip, n, turned))
        nrm = nm.outputs['Normal']
    nrm = nb.bump(nb.sub(1.0, groove), 0.0005, 1.0, normal=nrm)
    kw['normal'] = nrm
    if p.f('coat', 0.0) > 0:
        kw.update(coat=p.f('coat', 0.0), coat_rough=p.f('coat_rough', 0.3), coat_normal=nrm)
    return nb.principled(**kw)


def _floor_xy(nb, p):
    mp = nb.new('ShaderNodeMapping')
    nb.inp(mp, "Vector", nb.tc.outputs['UV'])                  # 1 UV unit = 1 m on our props
    nb.inp(mp, "Rotation", (0.0, 0.0, math.radians(p.f('rot', 0.0))))
    x, y, _ = nb.separate(mp.outputs[0])
    return x, y


@builder("planks")
def planks(nb, p):
    """Plank floor laid out like the real thing: boards `board_w` wide and all `board_len`
    long, each row's end joints shifted by `stagger`. Every board shows a random board from
    the atlas (whole boards cut from a photo, see tools/make_floor_atlas.py)."""
    maps, info = _atlas(p)
    if maps is None:
        return BUILDERS[p.get('fallback', 'parquet')](nb, p)
    bw = p.f('board_w', info.get('board_width_m', 0.19))
    bl = p.f('board_len', info.get('board_length_m', 1.2))
    x, y = _floor_xy(nb, p)
    col_i = nb.math('FLOOR', nb.math('DIVIDE', x, bw))
    u = nb.math('FRACT', nb.math('DIVIDE', x, bw))
    yy = nb.math('DIVIDE', nb.sub(y, nb.mul(col_i, p.f('stagger', 0.24))), bl)
    row_j = nb.math('FLOOR', yy)
    v = nb.math('FRACT', yy)
    seed = nb.add(nb.mul(col_i, 12.9898), nb.mul(row_j, 78.233))
    du = nb.mul(nb.math('MINIMUM', u, nb.sub(1.0, u)), bw)
    dv = nb.mul(nb.math('MINIMUM', v, nb.sub(1.0, v)), bl)
    return _boards(nb, p, maps, int(info.get('boards', 1)), u, v, seed, nb.math('MINIMUM', du, dv))


@builder("chevron")
def chevron(nb, p):
    """Chevron floor: bands `band` deep along Y; in each band the boards are parallel and lean
    sideways by `slant` per unit of band depth, the lean flips every band, so the joints meet
    in V shapes on the band lines. Boards come from a chevron atlas (tools/make_chevron_atlas.py)."""
    maps, info = _atlas(p)
    if maps is None:
        return BUILDERS[p.get('fallback', 'parquet')](nb, p)
    band = p.f('band', info.get('band_m', 0.3))
    pitch = p.f('pitch', info.get('pitch_m', 0.08))
    slant = p.f('slant', info.get('slant', 0.58))
    x, y = _floor_xy(nb, p)
    b = nb.math('FLOOR', nb.math('DIVIDE', y, band))
    t = nb.math('FRACT', nb.math('DIVIDE', y, band))
    odd = nb.math('FRACT', nb.mul(b, 0.5))                    # 0 even band, 0.5 odd band
    tri = nb.mix_float(nb.mul(odd, 2.0), t, nb.sub(1.0, t))   # zig-zag: joints meet on spines
    xs = nb.sub(x, nb.mul(tri, slant * band))
    k = nb.math('FLOOR', nb.math('DIVIDE', xs, pitch))
    u = nb.math('FRACT', nb.math('DIVIDE', xs, pitch))
    seed = nb.add(nb.mul(k, 12.9898), nb.mul(b, 78.233))
    du = nb.mul(nb.math('MINIMUM', u, nb.sub(1.0, u)), pitch / math.sqrt(1.0 + slant * slant))
    dv = nb.mul(nb.math('MINIMUM', t, nb.sub(1.0, t)), band)
    return _boards(nb, p, maps, int(info.get('boards', 1)), u, t, seed, nb.math('MINIMUM', du, dv))


@builder("metal")
def metal(nb, p):
    co = nb.obj
    smudge = nb.noise(co, 8.0, detail=4.0).outputs['Fac']
    brushed = nb.noise(nb.vmul(co, nb.vec(2.0, 700.0, 700.0)), 1.0, detail=4.0).outputs['Fac']
    rough = nb.add(p.f('rough', 0.3), nb.mul(nb.sub(smudge, 0.5), 0.1))
    br = p.f('brushed', 0.0)
    if br > 0:
        rough = nb.add(rough, nb.mul(nb.sub(brushed, 0.5), 0.2 * br))
    return nb.principled(base=p.c('base', '#C0C2C4'), metal=1.0, rough=rough,
                         aniso=0.6 * br, normal=nb.bump(brushed, 0.00002, 0.3 * br))


@builder("paint")
def paint(nb, p):
    co = nb.obj
    col = nb.vscale(nb.vec(*p.c('base', '#EDEBE6')),
                    nb.maprange(nb.noise(co, 5.0, detail=3.0).outputs['Fac'], 0.3, 0.7, 0.97, 1.03))
    peel = nb.noise(co, 900.0, detail=2.0).outputs['Fac']
    return nb.principled(base=col, rough=p.f('rough', 0.85), spec=0.4,
                         normal=nb.bump(peel, 0.0003, 0.08))


@builder("plastic")
def plastic(nb, p):
    co = nb.obj
    rough = nb.add(p.f('rough', 0.4), nb.mul(nb.sub(nb.noise(co, 10.0).outputs['Fac'], 0.5), 0.06))
    fine = nb.noise(co, 1500.0, detail=1.0).outputs['Fac']
    return nb.principled(base=p.c('base', '#EEEEEE'), rough=rough, coat=p.f('coat', 0.0), coat_rough=0.05,
                         normal=nb.bump(fine, 0.0001, 0.1 * p.f('bump', 0.3)))


@builder("concrete")
def concrete(nb, p):
    co = nb.obj
    c = p.f('contrast', 1.0)
    big = nb.noise(co, 6.0, detail=8.0).outputs['Fac']
    col = nb.vscale(nb.vec(*p.c('base', '#9A9893')), nb.maprange(big, 0.3, 0.7, 1 - 0.25 * c, 1 + 0.15 * c))
    pores = nb.voronoi(co, 300.0).outputs['Distance']
    fine = nb.noise(co, 80.0, detail=6.0).outputs['Fac']
    h = nb.add(nb.maprange(pores, 0.0, 0.15, 0.0, 1.0), fine)
    return nb.principled(base=col, rough=p.f('rough', 0.85), spec=0.35,
                         normal=nb.bump(h, 0.0003 * p.f('bump', 1.0), 0.5))


@builder("marble")
def marble(nb, p):
    co = nb.obj
    w = nb.wave(co, 'BANDS', 'DIAGONAL', p.f('vein_scale', 3.0), distortion=14.0, detail=10.0,
                detail_scale=1.5, detail_rough=0.6).outputs['Fac']
    vein = nb.mul(nb.maprange(w, 0.0, 0.09, 1.0, 0.0, smooth=True),
                  nb.maprange(nb.noise(co, 2.0).outputs['Fac'], 0.4, 0.6, 0.3, 1.0))
    base = nb.vscale(nb.vec(*p.c('base', '#EEEDE9')),
                     nb.maprange(nb.noise(co, 5.0, detail=6.0).outputs['Fac'], 0.3, 0.7, 0.92, 1.04))
    col = nb.mix_col(vein, base, p.c('vein', '#8A8C90'))
    return nb.principled(base=col, rough=nb.add(0.07, nb.mul(vein, 0.05)), spec=0.6, coat=0.3, coat_rough=0.03)


@builder("brick")
def brick(nb, p):
    co = nb.obj
    br = nb.new('ShaderNodeTexBrick', offset=0.5, offset_frequency=2)
    nb.inp(br, "Vector", co)
    nb.inp(br, "Color1", p.c('c1', '#8E4A32'))
    nb.inp(br, "Color2", p.c('c2', '#A85F44'))
    nb.inp(br, "Mortar", p.c('mortar', '#CFC8BC'))
    nb.inp(br, "Scale", 1.0)
    nb.inp(br, "Mortar Size", 0.01)
    nb.inp(br, "Mortar Smooth", 0.1)
    nb.inp(br, "Brick Width", 0.215)
    nb.inp(br, "Row Height", 0.075)
    grime = nb.noise(co, 20.0, detail=6.0).outputs['Fac']
    col = nb.vscale(br.outputs['Color'], nb.maprange(grime, 0.3, 0.7, 0.8, 1.1))
    h = nb.add(nb.sub(1.0, br.outputs['Fac']), nb.mul(grime, 0.3))
    return nb.principled(base=col, rough=0.9, normal=nb.bump(h, 0.004, 1.0))


@builder("fabric")
def fabric(nb, p):
    co = nb.obj
    s = p.f('thread', 380.0)
    wx = nb.wave(co, 'BANDS', 'X', s, detail=0.0).outputs['Fac']
    wy = nb.wave(co, 'BANDS', 'Y', s, detail=0.0).outputs['Fac']
    weave = nb.math('MAXIMUM', wx, wy)
    fuzz = nb.noise(co, 2000.0).outputs['Fac']
    col = nb.vscale(nb.vec(*p.c('base', '#D8CDB8')), nb.maprange(nb.add(weave, nb.mul(fuzz, 0.3)), 0.0, 1.3, 0.75, 1.05))
    return nb.principled(base=col, rough=0.95, sheen=1.0, sheen_rough=0.5, spec=0.3,
                         normal=nb.bump(nb.add(weave, fuzz), 0.0003, 0.6))


@builder("leather")
def leather(nb, p):
    co = nb.obj
    edge = nb.voronoi(co, p.f('grain', 500.0), feature='DISTANCE_TO_EDGE').outputs['Distance']
    crease = nb.maprange(edge, 0.0, 0.08, 0.0, 1.0, smooth=True)
    col = nb.vscale(nb.vec(*p.c('base', '#5A3621')), nb.maprange(crease, 0.0, 1.0, 0.7, 1.0))
    rough = nb.add(0.45, nb.mul(nb.sub(1.0, crease), 0.2))
    return nb.principled(base=col, rough=rough, coat=0.1, sheen=0.2, normal=nb.bump(crease, 0.0002, 0.6))


@builder("carpet")
def carpet(nb, p):
    co = nb.obj
    h = nb.add(nb.noise(co, 1500.0, detail=1.0).outputs['Fac'], nb.voronoi(co, 400.0).outputs['Distance'])
    col = nb.vscale(nb.vec(*p.c('base', '#CBB89B')), nb.maprange(h, 0.3, 1.2, 0.7, 1.1))
    return nb.principled(base=col, rough=1.0, sheen=1.0, sheen_rough=0.4, spec=0.2,
                         normal=nb.bump(h, 0.002, 1.0))


@builder("glass")
def glass(nb, p):
    return nb.principled(base=p.c('base', '#FFFFFF'), rough=p.f('rough', 0.0), trans=1.0, ior=1.5, spec=0.5)


@builder("ceramic")
def ceramic(nb, p):
    wav = nb.noise(nb.obj, 30.0, detail=2.0).outputs['Fac']
    return nb.principled(base=p.c('base', '#F1F0EC'), rough=p.f('rough', 0.1), coat=p.f('coat', 1.0),
                         coat_rough=0.03, sss=0.03, sss_scale=0.002, normal=nb.bump(wav, 0.0002, 0.2))


@builder("paper")
def paper(nb, p):
    co = nb.obj
    fib = nb.noise(co, 600.0, detail=4.0).outputs['Fac']
    fs = p.f('fiber', 0.3)
    col = nb.vscale(nb.vec(*p.c('base', '#F2F0EA')), nb.maprange(fib, 0.3, 0.7, 1 - 0.12 * fs, 1.0))
    return nb.principled(base=col, rough=p.f('rough', 0.9), sss=0.2, sss_scale=0.002,
                         coat=p.f('coat', 0.0), coat_rough=0.3, normal=nb.bump(fib, 0.0001, 0.3 * fs))


@builder("cork")
def cork(nb, p):
    co = nb.obj
    vor = nb.voronoi(co, 900.0)
    col = nb.mix_col(nb.math('GREATER_THAN', vor.outputs['Color'], 0.5), p.c('base', '#B88A5A'), p.c('dark', '#8A5A35'))
    return nb.principled(base=col, rough=0.95, normal=nb.bump(vor.outputs['Distance'], 0.0004, 0.8))


@builder("leaf")
def leaf(nb, p):
    co = nb.obj
    vein = nb.wave(co, 'BANDS', 'Y', 40.0, distortion=3.0).outputs['Fac']
    col = nb.vscale(nb.vec(*p.c('base', '#3E6B2E')),
                    nb.maprange(nb.noise(co, 30.0).outputs['Fac'], 0.3, 0.7, 0.85, 1.1))
    return nb.principled(base=col, rough=0.38, sss=0.25, sss_scale=0.003, spec=0.5, sheen=0.1,
                         normal=nb.bump(vein, 0.0002, 0.3))


@builder("cutting_mat")
def cutting_mat(nb, p):
    """Self-healing PVC cutting mat: printed grid, ruler ticks, diagonals, mottled colour,
    micro grain, light knife wear and a lighter core visible on the edges."""
    co = nb.obj
    x, y, z = nb.separate(co)
    W2, H2, m = p.f('half_w', 0.225), p.f('half_h', 0.15), 0.012
    ax, ay = nb.math('ABSOLUTE', x), nb.math('ABSOLUTE', y)

    def lines(c, period, thick):
        f = nb.math('FRACT', nb.math('DIVIDE', c, period))
        dd = nb.mul(nb.math('MINIMUM', f, nb.sub(1.0, f)), period)
        return nb.maprange(dd, thick * 0.3, thick * 0.5, 1.0, 0.0)

    def inside(v, lo, hi):
        return nb.mul(nb.math('GREATER_THAN', v, lo), nb.math('LESS_THAN', v, hi))

    inner = nb.mul(nb.math('LESS_THAN', ax, W2 - m), nb.math('LESS_THAN', ay, H2 - m))
    grid = nb.math('MAXIMUM', lines(x, 0.01, 0.00035), lines(y, 0.01, 0.00035))
    grid = nb.math('MAXIMUM', grid, nb.mul(nb.math('MAXIMUM', lines(x, 0.05, 0.0008), lines(y, 0.05, 0.0008)), 1.0))
    diag = nb.math('MAXIMUM', lines(nb.sub(x, y), 0.3, 0.0004), lines(nb.add(x, y), 0.3, 0.0004))
    grid = nb.mul(nb.math('MAXIMUM', grid, nb.mul(diag, 0.55)), inner)

    # ruler ticks in the margin (5 mm short, 10 mm long)
    edge_y = nb.mul(inside(ay, H2 - m, H2 - m + 0.005), nb.math('LESS_THAN', ax, W2 - m))
    edge_y2 = nb.mul(inside(ay, H2 - m, H2 - m + 0.008), nb.math('LESS_THAN', ax, W2 - m))
    ticks = nb.math('MAXIMUM', nb.mul(edge_y, lines(x, 0.005, 0.0003)), nb.mul(edge_y2, lines(x, 0.01, 0.0003)))
    edge_x = nb.mul(inside(ax, W2 - m, W2 - m + 0.005), nb.math('LESS_THAN', ay, H2 - m))
    edge_x2 = nb.mul(inside(ax, W2 - m, W2 - m + 0.008), nb.math('LESS_THAN', ay, H2 - m))
    ticks = nb.math('MAXIMUM', ticks, nb.mul(edge_x, lines(y, 0.005, 0.0003)))
    ticks = nb.math('MAXIMUM', ticks, nb.mul(edge_x2, lines(y, 0.01, 0.0003)))
    frame = nb.mul(nb.math('MAXIMUM', inside(ax, W2 - m - 0.0004, W2 - m), inside(ay, H2 - m - 0.0004, H2 - m)),
                   nb.mul(nb.math('LESS_THAN', ax, W2 - m), nb.math('LESS_THAN', ay, H2 - m)))
    ink = nb.math('MAXIMUM', nb.math('MAXIMUM', grid, ticks), frame)
    ink = nb.mul(ink, nb.maprange(nb.noise(co, 900.0).outputs['Fac'], 0.3, 0.7, 0.75, 1.0))

    # mottled PVC colour
    m1 = nb.noise(co, 7.0, detail=6.0).outputs['Fac']
    m2 = nb.noise(co, 35.0, detail=4.0).outputs['Fac']
    base = nb.mix_col(nb.maprange(m1, 0.35, 0.7, 0.0, 0.6), p.c('base', '#14785F'), p.c('base2', '#16636A'))
    base = nb.vscale(base, nb.maprange(m2, 0.3, 0.7, 0.92, 1.05))

    # light wear: long knife cuts and short scratches
    cuts = nb.voronoi(nb.vmul(co, nb.vec(1.0, 1.6, 1.0)), 16.0, feature='DISTANCE_TO_EDGE').outputs['Distance']
    cuts = nb.mul(nb.maprange(cuts, 0.0, 0.004, 1.0, 0.0),
                  nb.maprange(nb.noise(co, 5.0).outputs['Fac'], 0.58, 0.64, 0.0, 1.0))
    scr = nb.voronoi(nb.vmul(co, nb.vec(1.0, 2.5, 1.0)), 55.0, feature='DISTANCE_TO_EDGE').outputs['Distance']
    scr = nb.mul(nb.maprange(scr, 0.0, 0.003, 1.0, 0.0),
                 nb.maprange(nb.noise(nb.vadd(co, nb.vec(3.1, 1.7, 0.0)), 9.0).outputs['Fac'], 0.6, 0.66, 0.0, 1.0))
    wear = nb.mul(nb.math('MAXIMUM', cuts, nb.mul(scr, 0.7)), p.f('wear', 1.0))

    col = nb.mix_col(ink, base, p.c('line', '#78DCC8'))
    col = nb.mix_col(nb.mul(wear, 0.45), col, p.c('cut', '#9CC9BC'))

    # edges: layered sheet with a lighter core
    nz = nb.math('ABSOLUTE', nb.separate(nb.tc.outputs['Normal'])[2])
    side = nb.maprange(nz, 0.4, 0.8, 1.0, 0.0)
    t = p.f('thickness', 0.003)
    core = inside(z, t * 0.42, t * 0.58)
    col = nb.mix_col(nb.mul(side, core), col, p.c('core', '#B9D3C4'))

    # pebbled (orange-peel) skin of the PVC: dense rounded blobs about `pebble_mm` across with
    # irregular outlines, glossier tops and darker, rougher pits between them
    size = p.f('pebble_mm', 0.8) * 0.001
    warp = nb.vsub(nb.noise(co, 0.6 / size, detail=2.0).outputs['Color'], nb.vec(0.5, 0.5, 0.5))
    pc = nb.vadd(co, nb.vscale(warp, size * 0.9))
    d1 = nb.voronoi(pc, 1.0 / size, feature='F1', randomness=0.9).outputs['Distance']
    d2 = nb.voronoi(nb.vadd(pc, nb.vec(0.37, 0.11, 0.0)), 1.6 / size, feature='F1').outputs['Distance']
    blob = nb.math('MAXIMUM', nb.maprange(d1, 0.05, 0.62, 1.0, 0.0, smooth=True),
                   nb.mul(nb.maprange(d2, 0.05, 0.55, 1.0, 0.0, smooth=True), 0.7))
    fine = nb.noise(co, 6.0 / size, detail=2.0).outputs['Fac']
    peb = nb.mul(nb.add(nb.mul(blob, 0.85), nb.mul(fine, 0.15)), p.f('pebble', 1.0))
    pit = nb.sub(1.0, blob)
    col = nb.vscale(col, nb.maprange(pit, 0.4, 1.0, 1.0, 0.8))

    peel = nb.noise(co, 350.0, detail=3.0).outputs['Fac']
    h = nb.sub(nb.add(peb, nb.mul(peel, 0.15)), nb.mul(wear, 2.0))
    rough = nb.add(nb.add(0.62, nb.mul(nb.sub(m2, 0.5), 0.12)), nb.mul(wear, 0.12))
    rough = nb.add(rough, nb.mul(nb.sub(pit, 0.5), 0.3))
    rough = nb.mix_float(ink, rough, 0.52)
    return nb.principled(base=col, rough=rough, spec=0.3, sheen=0.06, sheen_rough=0.5,
                         normal=nb.bump(h, size * 0.35, 1.0))


@builder("pei")
def pei(nb, p):
    co = nb.obj
    t = p.f('textured', 1.0)
    h = nb.add(nb.voronoi(co, 2500.0).outputs['Distance'], nb.noise(co, 4000.0).outputs['Fac'])
    col = nb.vscale(nb.vec(*p.c('base', '#9C7A3C')), nb.maprange(nb.noise(co, 40.0).outputs['Fac'], 0.3, 0.7, 0.93, 1.05))
    return nb.principled(base=col, rough=p.f('rough', 0.55), metal=0.3, coat=0.3 * (1 - t),
                         normal=nb.bump(h, 0.00015 * t, 1.0))


@builder("emission")
def emission(nb, p):
    c = p.c('base', '#FFD9A0')
    return nb.principled(base=c, emit=c, emit_str=p.f('strength', 20.0), rough=0.3)


@builder("canvas_art")
def canvas_art(nb, p):
    co = nb.obj
    f = nb.noise(co, 1.5, detail=4.0, distortion=1.5).outputs['Fac']
    col = nb.ramp(f, [(0.3, p.c('c1', '#1F3B57')), (0.45, p.c('c2', '#E2B65B')),
                      (0.55, p.c('c3', '#C2553A')), (0.7, p.c('c4', '#EDE6D8'))], interp='CONSTANT')
    canvas = nb.noise(co, 2500.0).outputs['Fac']
    return nb.principled(base=col, rough=0.6, normal=nb.bump(canvas, 0.0001, 0.4))
