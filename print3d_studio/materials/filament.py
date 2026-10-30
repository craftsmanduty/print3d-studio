"""FDM print look: layer lines, seam, top-surface skin lines.

Layers are computed in the object's local space along the chosen print direction,
so the lines stay fixed on the model even when the object is rotated in the scene.
"""
import math

import numpy as np
from mathutils import Euler, Vector

from .. import palette, utils
from ..nodes import NB
from ..scene import slicer

DIRS = {
    'Z+': (0, 0, 1), 'Z-': (0, 0, -1),
    'Y+': (0, 1, 0), 'Y-': (0, -1, 0),
    'X+': (1, 0, 0), 'X-': (-1, 0, 0),
}


def local_dir(p):
    if p.print_dir == 'CUSTOM':
        return (Euler((p.tilt_x, p.tilt_y, 0.0)).to_matrix() @ Vector((0, 0, 1))).normalized()
    return Vector(DIRS[p.print_dir])


def _basis(d):
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    u = d.cross(ref).normalized()
    v = d.cross(u).normalized()
    return u, v


def _tangent_axis(d):
    a = [abs(d.x), abs(d.y), abs(d.z)]
    return 'XYZ'[a.index(max(a))]


def make_cfg(obj, scene, d, layer_mm, width_mm, strength=1.0, variation=0.35,
             seam='ALIGNED', seam_angle=math.radians(90), top_lines=True, period_mm=25.0):
    me = obj.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    if len(co):
        hmin = float((co @ np.array(d[:])).min())
        center = Vector(((co.min(0) + co.max(0)) / 2).tolist())
    else:
        hmin, center = 0.0, Vector()
    sc = (obj.matrix_world.to_3x3() @ d).length or 1.0
    mm_world = 0.001 / (scene.unit_settings.scale_length or 1.0)
    u, v = _basis(d)
    return dict(d=d, u=u, v=v, hmin=hmin, center=center, mm_world=mm_world, mm_local=mm_world / sc,
                layer_mm=layer_mm, width_mm=width_mm, strength=strength, variation=variation,
                seam=seam, seam_angle=seam_angle, top_lines=top_lines, period_mm=period_mm,
                tangent_axis=_tangent_axis(d))


def _bead(nb, t):
    """Rounded extrusion profile across one layer, 0..1 (V grooves at the edges)."""
    x = nb.math('MULTIPLY_ADD', t, 2.0, -1.0)
    y = nb.sub(1.0, nb.mul(x, x))
    return nb.math('POWER', nb.math('MAXIMUM', y, 0.0), 0.5)


def build(mat, tdef, colors, cfg, extra_glow=None):
    mat = utils.node_material(mat.name, mat)
    nb = NB(mat.node_tree)
    co, nrm = nb.obj, nb.tc.outputs['Normal']
    d, u, v = cfg['d'], cfg['u'], cfg['v']
    mmL = cfg['mm_local']
    L = cfg['layer_mm'] * mmL
    W = cfg['width_mm'] * mmL
    lmul = tdef.get('layer_mul', 1.0)
    strength = cfg['strength'] * lmul
    var = cfg['variation']
    dvec = nb.vec(*d)

    # --- layer height ---------------------------------------------------
    h = nb.sub(nb.dot(co, dvec), cfg['hmin'])
    hl = nb.math('DIVIDE', h, L)
    n = nb.math('FLOOR', hl)
    prof = _bead(nb, nb.math('FRACT', hl))

    # small layer-to-layer differences (z-banding) and horizontal wobble
    zband = nb.mul(nb.sub(nb.white1d(n), 0.5), 0.5 * var)
    wob = nb.mul(nb.sub(nb.noise(co, 1.0 / (6.0 * mmL), detail=3.0).outputs['Fac'], 0.5), 0.6 * var)
    layer_h = nb.add(nb.add(prof, zband), wob)

    # --- angle (for the seam and multi-colour silk) ----------------------
    pc = nb.vsub(co, nb.vec(*cfg['center']))
    au, av = nb.dot(pc, nb.vec(*u)), nb.dot(pc, nb.vec(*v))
    ang = nb.math('ARCTAN2', av, au)
    radius = nb.length(nb.vec(au, av, 0.0))

    seam_mask = None
    if cfg['seam'] != 'NONE':
        wn2 = nb.white1d(nb.add(n, 17.13))
        if cfg['seam'] == 'RANDOM':
            theta = nb.math('MULTIPLY_ADD', wn2, 2 * math.pi, -math.pi)
        else:
            theta = nb.math('MULTIPLY_ADD', wn2, 0.05, cfg['seam_angle'] - 0.025)
        dd = nb.math('WRAP', nb.sub(ang, theta), math.pi, -math.pi)
        arc = nb.mul(nb.math('ABSOLUTE', dd), radius)
        seam_mask = nb.maprange(arc, 0.0, 1.6 * W, 1.0, 0.0, smooth=True)
        layer_h = nb.add(layer_h, nb.mul(seam_mask, 0.7))

    # --- near-horizontal surfaces: every layer is a flat terrace ----------
    # A sloped top is printed as horizontal steps L / tan(slope) wide (a 5.5 deg roof at
    # 0.2 mm gives ~2 mm steps) with a rounded perimeter edge. Heights below are in layer
    # heights, measured outwards from the mesh surface.
    ndot = nb.dot(nrm, dvec)
    c = nb.math('MAXIMUM', nb.math('ABSOLUTE', ndot), 0.02)
    sin_t = nb.math('SQRT', nb.math('MAXIMUM', nb.sub(1.0, nb.mul(c, c)), 0.0))
    tan_t = nb.math('MAXIMUM', nb.math('DIVIDE', sin_t, c), 1e-3)
    f = nb.math('FRACT', hl)
    up = nb.math('GREATER_THAN', ndot, 0.0)
    fe = nb.mix_float(up, nb.sub(1.0, f), f)                 # 0 at the outer edge of a step
    x = nb.math('DIVIDE', fe, tan_t)                         # distance from that edge
    # the outer perimeter bead is rounded over half its width horizontally and half a
    # layer vertically (quarter ellipse), so each step edge catches a narrow highlight
    rx = 0.5 * cfg['width_mm'] / cfg['layer_mm']
    xr = nb.sub(1.0, nb.math('DIVIDE', nb.math('MINIMUM', x, rx), rx))
    deficit = nb.mul(nb.sub(1.0, nb.math('SQRT', nb.math('MAXIMUM', nb.sub(1.0, nb.mul(xr, xr)), 0.0))), 0.5)
    terr_h = nb.sub(nb.sub(1.0, fe), deficit)
    terr_shade = nb.sub(1.0, nb.mul(deficit, 2.0))

    top_rough = None
    if cfg['top_lines']:
        # two perimeter loops along every outline, then solid infill lines at 45 degrees
        # (alternating per layer). Sliced geometry carries the true distance from the outline.
        if cfg.get('edge_attr'):
            x_mm = nb.new('ShaderNodeAttribute', attribute_name=cfg['edge_attr']).outputs['Fac']
        else:
            x_mm = nb.mul(x, cfg['layer_mm'])
        pl = nb.math('DIVIDE', x_mm, cfg['width_mm'])
        p_var = nb.math('MULTIPLY_ADD', nb.white1d(nb.add(nb.math('FLOOR', pl), nb.mul(n, 3.17))), 0.4, 0.8)
        perim = nb.mul(_bead(nb, nb.math('FRACT', pl)), p_var)
        d1, d2 = (u + v).normalized(), (u - v).normalized()
        s1 = nb.math('DIVIDE', nb.dot(co, nb.vec(*d1)), W)
        s2 = nb.math('DIVIDE', nb.dot(co, nb.vec(*d2)), W)
        parity = nb.math('MODULO', n, 2.0)
        s = nb.math('MULTIPLY_ADD', parity, nb.sub(s2, s1), s1)
        # lines are never laser straight: slow lateral wander, each line its own height
        wander = nb.sub(nb.noise(co, 1.0 / (2.5 * mmL), detail=2.0).outputs['Fac'], 0.5)
        s = nb.add(s, nb.mul(wander, 0.35 * cfg.get('flaws', 1.0)))
        li = nb.math('FLOOR', s)
        l_rand = nb.white1d(nb.add(li, nb.mul(n, 7.31)))
        l_var = nb.math('MULTIPLY_ADD', l_rand, 0.45, 0.75)
        # extrusion pulses and vibration ripple each line along its length (~0.5 mm period),
        # which breaks the reflection into short streaks instead of one mirror-like patch
        t = nb.math('MULTIPLY_ADD', parity, nb.sub(s1, s2), s2)
        rip = nb.noise(nb.vec(t, nb.mul(li, 3.1), nb.mul(n, 1.7)), 0.85, detail=1.0).outputs['Fac']
        l_var = nb.mul(l_var, nb.maprange(rip, 0.3, 0.7, 0.7, 1.15))
        infill = nb.mul(_bead(nb, nb.math('FRACT', s)), l_var)
        line_rough = nb.mul(nb.sub(l_rand, 0.5), 0.12)
        pw = 2.0 * cfg['width_mm']
        in_perim = nb.maprange(x_mm, pw - 0.02, pw + 0.02, 1.0, 0.0)
        lines = nb.mix_float(in_perim, infill, perim)
        # Like a slicer, show skin only where it is really exposed: sliced geometry marks
        # every cap face as top skin (nothing printed above), bottom skin (nothing below,
        # overhangs), bed side (first layer) or hidden/wall micro-ledge (no skin pattern).
        if cfg.get('skin_attr'):
            sk = nb.new('ShaderNodeAttribute', attribute_name=cfg['skin_attr']).outputs['Fac']
            top_w = nb.math('GREATER_THAN', sk, 0.5)
            bed_w = nb.math('LESS_THAN', sk, -1.5)
            bot_w = nb.mul(nb.math('LESS_THAN', sk, -0.5), nb.sub(1.0, bed_w))
        else:
            top_w, bot_w, bed_w = 1.0, 0.0, 0.0
        # top ridges ~0.05 mm with narrow valleys; bottom skin sags into softer, matte lines;
        # the bed side is pressed flat and glossy
        amp = nb.add(nb.mul(top_w, 0.25), nb.add(nb.mul(bot_w, 0.15), nb.mul(bed_w, 0.03)))
        terr_h = nb.add(terr_h, nb.mul(nb.sub(lines, 1.0), amp))
        dark = nb.maprange(lines, 0.0, 1.0, 0.78, 1.0)
        terr_shade = nb.mul(terr_shade, nb.mix_float(nb.add(top_w, nb.mul(bot_w, 0.6)), 1.0, dark))
        top_rough = nb.add(nb.mul(nb.mul(line_rough, nb.sub(1.0, in_perim)), top_w),
                           nb.add(nb.mul(bot_w, 0.12), nb.mul(bed_w, -0.12)))

    wall_h = nb.mul(layer_h, 0.5)                            # bead radius = half a layer
    tmask = nb.maprange(c, 0.55, 0.8, 0.0, 1.0, smooth=True)
    final_h = nb.mix_float(tmask, wall_h, terr_h)
    shade = nb.mix_float(tmask, layer_h, terr_shade)

    # --- colour ----------------------------------------------------------
    effect = tdef.get('effect', 'none')
    if len(colors) > 1 and effect == 'rainbow':
        period = cfg['period_mm'] * mmL
        f = nb.math('FRACT', nb.math('DIVIDE', h, period))
        cyc = colors + [colors[0]]
        base = nb.ramp(f, [(i / (len(cyc) - 1), c) for i, c in enumerate(cyc)])
    elif len(colors) > 1:
        f = nb.math('MULTIPLY_ADD', ang, 1.0 / (2 * math.pi), 0.5)
        k, stops = len(colors), []
        for i, c in enumerate(colors):
            stops += [(i / k + 0.03, c), ((i + 1) / k - 0.03, c)]
        base = nb.ramp(f, stops)
    else:
        base = nb.vec(*colors[0])

    # very slight tone variation between batches / along the spool
    tone = nb.maprange(nb.noise(co, 1.0 / (30.0 * mmL)).outputs['Fac'], 0.3, 0.7, 0.975, 1.025)
    base = nb.vscale(base, tone)
    # slight darkening in the layer grooves
    # (having it in the albedo too keeps the denoiser from wiping the lines out)
    base = nb.vscale(base, nb.maprange(shade, 0.0, 1.0, 1.0 - 0.3 * min(strength, 1.8), 1.0))

    rough = nb.add(tdef.get("roughness", 0.4), nb.mul(nb.sub(1.0, shade), 0.08))
    if top_rough is not None:
        rough = nb.add(rough, nb.mul(top_rough, tmask))
    if seam_mask is not None:
        rough = nb.add(rough, nb.mul(seam_mask, 0.08))
    metal = tdef.get('metallic', 0.0)

    if effect == 'sparkle':
        vor = nb.voronoi(co, 1.0 / (0.5 * mmL))
        flake = nb.maprange(vor.outputs['Distance'], 0.05, 0.18, 1.0, 0.0, smooth=True)
        flake = nb.mul(flake, nb.math('GREATER_THAN', vor.outputs['Color'], 0.55))
        glit = utils.hex_to_linear(tdef.get('glitter', '#E8E8F0'))
        base = nb.mix_col(flake, base, glit)
        metal = flake
        rough = nb.mix_float(flake, rough, 0.12)
    elif effect == 'wood':
        sp = nb.noise(co, 1.0 / (0.8 * mmL), detail=6.0).outputs['Fac']
        base = nb.vscale(base, nb.maprange(sp, 0.55, 0.75, 1.0, 0.6))
        dots = nb.maprange(nb.voronoi(co, 1.0 / (1.2 * mmL)).outputs['Distance'], 0.0, 0.08, 0.5, 1.0)
        base = nb.vscale(base, dots)
    elif effect == 'marble':
        vor = nb.voronoi(co, 1.0 / (2.0 * mmL))
        spk = nb.mul(nb.maprange(vor.outputs['Distance'], 0.0, 0.1, 1.0, 0.0),
                     nb.math('GREATER_THAN', vor.outputs['Color'], 0.6))
        base = nb.mix_col(spk, base, utils.hex_to_linear('#2A2A2A'))
    elif effect == 'carbon':
        vor = nb.voronoi(co, 1.0 / (0.15 * mmL))
        glint = nb.mul(nb.maprange(vor.outputs['Distance'], 0.0, 0.06, 1.0, 0.0),
                       nb.math('GREATER_THAN', vor.outputs['Color'], 0.7))
        metal = nb.mul(glint, 0.5)
        rough = nb.mix_float(glint, rough, 0.35)

    wear = cfg.get('wear', 0.0)
    if wear > 0:
        # faint matte smudges from handling (fingertip sized patches)
        sm = nb.noise(co, 1.0 / (9.0 * mmL), detail=4.0).outputs['Fac']
        rough = nb.add(rough, nb.maprange(sm, 0.56, 0.72, 0.0, 0.1 * wear, smooth=True))
        # sparse dust specks (~0.05 mm), settled mostly on upward faces
        vor = nb.voronoi(co, 1.0 / (1.6 * mmL))
        speck = nb.mul(nb.maprange(vor.outputs['Distance'], 0.02, 0.04, 1.0, 0.0, smooth=True),
                       nb.math('GREATER_THAN', vor.outputs['Color'], 1.0 - 0.06 * wear))
        speck = nb.mul(speck, nb.maprange(ndot, 0.1, 0.6, 0.2, 1.0))
        base = nb.mix_col(speck, base, utils.hex_to_linear('#B9B4AA'))
        rough = nb.mix_float(speck, rough, 0.95)

    # no edge of a print is knife sharp: round every corner by about a third of a layer
    bevel = nb.new('ShaderNodeBevel', samples=8)
    nb.inp(bevel, "Radius", 0.35 * cfg['layer_mm'] * cfg['mm_world'])
    # heights are in layer heights: the bump distance is one real layer (no exaggeration)
    nrm_out = nb.bump(final_h, cfg['layer_mm'] * cfg['mm_world'] * strength, 1.0,
                      normal=bevel.outputs['Normal'])

    kw = dict(base=base, rough=rough, metal=metal, normal=nrm_out,
              spec=tdef.get('specular', 0.5), ior=tdef.get('ior', 1.5),
              coat=tdef.get('coat', 0.0), coat_rough=tdef.get('coat_rough', 0.12), coat_normal=nrm_out,
              sheen=tdef.get('sheen', 0.0), trans=tdef.get('transmission', 0.0))
    if tdef.get('sss', 0.0) > 0:
        kw.update(sss=tdef['sss'], sss_radius=(1.0, 0.7, 0.5),
                  sss_scale=tdef.get('sss_mm', 0.8) * cfg['mm_world'])
    if tdef.get('anisotropic', 0.0) > 0:
        tan = nb.new('ShaderNodeTangent', direction_type='RADIAL', axis=cfg['tangent_axis'])
        kw.update(aniso=tdef['anisotropic'], tangent=tan.outputs['Tangent'])
    glow = extra_glow
    if effect == 'glow' and glow:
        kw.update(emit=glow, emit_str=tdef.get('glow_strength', 0.08))

    bsdf = nb.principled(**kw)
    nb.output(bsdf.outputs[0])

    c0 = colors[0]
    mat.diffuse_color = (*c0, 1.0)
    mat.roughness = tdef.get('roughness', 0.4)
    mat.metallic = tdef.get('metallic', 0.0) if isinstance(tdef.get('metallic', 0.0), float) else 0.0
    return mat


def _smooth_facets(obj):
    """STL files arrive flat shaded; smooth curved areas but keep real edges sharp (once)."""
    me = obj.data
    if not me.polygons or me.get("p3d_smoothed"):
        return
    flags = np.zeros(len(me.polygons), dtype=bool)
    me.polygons.foreach_get("use_smooth", flags)
    if not flags.any():
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(35))
    me["p3d_smoothed"] = True


MAX_LAYERS = 5000


def source_mesh(obj):
    """The model's original mesh (the object shows the sliced copy while Real Layers is on)."""
    import bpy
    return bpy.data.meshes.get(obj.get("p3d_source", "")) or obj.data


def restore_source(obj):
    """Puts the original mesh back and deletes the sliced copy."""
    import bpy
    src = source_mesh(obj)
    if obj.data != src:
        sliced = obj.data
        obj.data = src
        bpy.data.meshes.remove(sliced)


def _update_layers(obj, scene, d, p):
    """Swaps the object's mesh between the original and its real sliced layer stack."""
    import bpy
    src = source_mesh(obj)
    sliced = obj.data if obj.data != src else None
    if not p.real_layers:
        restore_source(obj)
        _smooth_facets(obj)
        return
    mm_world = 0.001 / (scene.unit_settings.scale_length or 1.0)
    sc = (obj.matrix_world.to_3x3() @ d).length or 1.0
    layer = p.layer_height * mm_world / sc                    # layer height in mesh units
    key = "%.6g|%.4f,%.4f,%.4f|%.3f|%.3f" % (layer, *d, p.flaws, p.line_width)
    if sliced is not None and obj.get("p3d_slice_key") == key:
        return
    co = np.empty(len(src.vertices) * 3)
    src.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ np.array(d[:])
    height = float(co.max() - co.min()) if len(co) else 0.0
    if height / layer > MAX_LAYERS:
        # model not at real size yet (e.g. still in mm units): keep the original for now
        restore_source(obj)
        return
    src.use_fake_user = True
    obj["p3d_source"] = src.name
    seed = sum(map(ord, src.name)) % 9973
    new, _ = slicer.slice_mesh(src, d, layer, p.layer_height, p.flaws, seed, p.line_width)
    new["p3d_layers_of"] = src.name
    obj.data = new
    obj["p3d_slice_key"] = key
    if sliced is not None:
        bpy.data.meshes.remove(sliced)


def apply(obj, scene=None):
    """Builds the filament material from the object's p3d settings and assigns it."""
    import bpy
    if obj is None or obj.type != 'MESH':
        return None
    scene = scene or bpy.context.scene
    p = obj.p3d
    tdef = palette.get_type(p.filament_type)
    entry = palette.get_color_entry(p.filament_type, p.filament_color)
    colors = [tuple(p.custom_color)] if p.use_custom_color else palette.colors_linear(entry)
    glow = utils.hex_to_linear(entry["glow"]) if entry.get("glow") else None

    d = local_dir(p)
    _update_layers(obj, scene, d, p)
    cfg = make_cfg(obj, scene, d, p.layer_height, p.line_width, p.layer_strength, p.variation,
                   p.seam, p.seam_angle, p.top_lines, p.rainbow_period)
    cfg['wear'] = p.wear
    cfg['flaws'] = p.flaws if p.real_layers else 1.0
    cfg['edge_attr'] = slicer.EDGE_ATTR if slicer.EDGE_ATTR in obj.data.attributes else None
    cfg['skin_attr'] = slicer.SKIN_ATTR if slicer.SKIN_ATTR in obj.data.attributes else None

    mat = p.material or bpy.data.materials.new("P3D_Print_" + obj.name)
    mat = build(mat, tdef, colors, cfg, glow)
    p.material = mat
    p.is_print = True

    mats = obj.data.materials
    if not mats:
        mats.append(mat)
    else:
        for i in range(len(mats)):
            mats[i] = mat
    return mat
