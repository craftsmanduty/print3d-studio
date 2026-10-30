"""Isik hazir ayarlari: stüdyo, gun isigi, altin saat, aksam, HDRI."""
import math
import os

import bpy
from mathutils import Vector

from .. import utils
from . import room

COLLECTION = "P3D_Lights"


def _target(context):
    ob = context.active_object
    if ob is not None and ob.type == 'MESH' and ob.select_get():
        _, _, c, r = utils.world_bounds(ob)
        return c, r
    return context.scene.cursor.location.copy(), 0.1


def _light(coll, name, typ, energy, loc, aim=None, size=0.5, color=(1, 1, 1), direction=None):
    ld = bpy.data.lights.new(name, typ)
    ld.energy = energy
    ld.color = color
    if typ == 'AREA':
        ld.shape = 'RECTANGLE' if isinstance(size, tuple) else 'SQUARE'
        if isinstance(size, tuple):
            ld.size, ld.size_y = size
        else:
            ld.size = size
    elif typ in ('POINT', 'SPOT'):
        ld.shadow_soft_size = size
    ob = bpy.data.objects.new(name, ld)
    coll.objects.link(ob)
    ob.location = loc
    if direction is None and aim is not None:
        direction = Vector(aim) - Vector(loc)
    if direction is not None:
        ob.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    return ob


def _sky_world(scene, elev, rot, strength):
    world = utils.world_tree(scene)
    nt = world.node_tree
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = strength
    sky = nt.nodes.new('ShaderNodeTexSky')
    types = [i.identifier for i in sky.bl_rna.properties['sky_type'].enum_items]
    for t in ('NISHITA', 'MULTIPLE_SCATTERING', 'SINGLE_SCATTERING', 'HOSEK_WILKIE', 'PREETHAM'):
        if t in types:
            sky.sky_type = t
            break
    for attr, val in (('sun_disc', False), ('sun_elevation', elev), ('sun_rotation', rot),
                      ('sun_direction', (math.sin(rot) * math.cos(elev), math.cos(rot) * math.cos(elev), math.sin(elev)))):
        try:
            setattr(sky, attr, val)
        except Exception:
            pass
    nt.links.new(sky.outputs[0], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs['Surface'])


def _flat_world(scene, color, strength):
    world = utils.world_tree(scene)
    nt = world.node_tree
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (*color, 1.0)
    bg.inputs['Strength'].default_value = strength
    nt.links.new(bg.outputs[0], out.inputs['Surface'])


def _hdri_world(scene, path, strength, rot):
    world = utils.world_tree(scene)
    nt = world.node_tree
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = strength
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(path, check_existing=True)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Rotation'].default_value[2] = rot
    nt.links.new(tc.outputs['Generated'], mp.inputs['Vector'])
    nt.links.new(mp.outputs[0], env.inputs['Vector'])
    nt.links.new(env.outputs['Color'], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs['Surface'])


def _sun_direction(elev, azim):
    """Gunes isinlarinin ilerleme yonu (gokyuzunden sahneye)."""
    win = room.find_window()
    if win is not None:
        _, n_out, _ = win
        h = Vector((-n_out.x, -n_out.y, 0)).normalized()
        c, s = math.cos(azim), math.sin(azim)
        h = Vector((h.x * c - h.y * s, h.x * s + h.y * c, 0))
    else:
        h = Vector((-math.sin(azim), math.cos(azim), 0))
    return Vector((h.x * math.cos(elev), h.y * math.cos(elev), -math.sin(elev))).normalized()


def _portal(coll):
    win = room.find_window()
    if win is None:
        return
    c, n_out, size = win
    ob = _light(coll, "Window_Portal", 'AREA', 0.0, c - n_out * 0.01, size=(size[0], size[1]),
                direction=-n_out)
    try:
        ob.data.cycles.is_portal = True
    except Exception:
        pass
    ob.rotation_euler = n_out.to_track_quat('Z', 'Y').to_euler()
    ob.data.size, ob.data.size_y = size[0], size[1]


def setup(context, s):
    scene = context.scene
    coll = utils.ensure_collection(COLLECTION)
    utils.clear_collection(coll)
    target, r = _target(context)
    k = s.light_strength
    preset = s.light_preset
    elev, azim = math.radians(s.sun_elev), math.radians(s.sun_azim)

    if preset == 'STUDIO':
        _flat_world(scene, (0.55, 0.56, 0.58), 0.12 * k)
        # alan isigi isinimi ~ P / (pi * d^2): gunes (~4.5 W/m2) ile ayni pozlamada kalsin
        d = max(0.4, r * 7)
        pw = d * d
        _light(coll, "Key_Softbox", 'AREA', 11 * pw * k, target + Vector((-0.8, -0.9, 0.9)).normalized() * d,
               aim=target, size=d * 0.9, color=utils.kelvin_to_linear(5200))
        _light(coll, "Fill_Light", 'AREA', 3.5 * pw * k, target + Vector((1.0, -0.6, 0.3)).normalized() * d,
               aim=target, size=d * 1.2, color=utils.kelvin_to_linear(5600))
        _light(coll, "Rim_Light", 'AREA', 9 * pw * k, target + Vector((0.4, 1.0, 0.8)).normalized() * d,
               aim=target, size=(d * 0.25, d * 0.9), color=utils.kelvin_to_linear(6000))
    elif preset in ('WINDOW_DAY', 'GOLDEN'):
        if preset == 'GOLDEN':
            elev = math.radians(min(s.sun_elev, 10.0))
            col, sun_e = utils.kelvin_to_linear(3300), 3.2 * k
        else:
            col, sun_e = utils.kelvin_to_linear(5600), 4.5 * k
        tdir = _sun_direction(elev, azim)
        sun = _light(coll, "Sun", 'SUN', sun_e, target - tdir * 5, direction=tdir, color=col)
        sun.data.angle = math.radians(1.2)
        sky_rot = math.atan2(-tdir.x, -tdir.y)
        _sky_world(scene, elev, sky_rot, 0.35 * k)
        _portal(coll)
    elif preset == 'EVENING':
        _flat_world(scene, (0.02, 0.03, 0.06), 0.6 * k)
        _light(coll, "Ceiling_Light", 'AREA', 22 * k, target + Vector((0.3, -0.2, 1.4)), aim=target, size=0.5,
               color=utils.kelvin_to_linear(3200))
        _light(coll, "Warm_Side_Light", 'POINT', 10 * k, target + Vector((-0.6, 0.3, 0.45)), size=0.08,
               color=utils.kelvin_to_linear(3000))
    elif preset == 'HDRI':
        path = bpy.path.abspath(s.hdri_path)
        if not path or not os.path.isfile(path):
            raise FileNotFoundError("HDRI file not found")
        _hdri_world(scene, path, s.hdri_strength * k, math.radians(s.hdri_rot))
