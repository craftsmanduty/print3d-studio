import math

import bpy
from mathutils import Quaternion, Vector

from .. import utils


def setup(context, s, target_obj=None):
    scene = context.scene
    context.view_layer.update()
    ob = target_obj or context.active_object
    if ob is not None and ob.type == 'MESH':
        _, _, center, radius = utils.world_bounds(ob)
    else:
        center, radius = scene.cursor.location.copy(), 0.1

    cam_ob = bpy.data.objects.get("P3D_Camera")
    if cam_ob is None or cam_ob.type != 'CAMERA':
        cam = bpy.data.cameras.new("P3D_Camera")
        cam_ob = bpy.data.objects.new("P3D_Camera", cam)
        utils.ensure_collection("P3D_Lights").objects.link(cam_ob)
    cam = cam_ob.data
    cam.lens = s.cam_lens
    cam.sensor_width = 36.0

    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    aspect = min(rx / ry, ry / rx)
    half = math.atan((cam.sensor_width / 2) / cam.lens * aspect)
    dist = radius * s.cam_margin / math.sin(half)

    el, az = math.radians(s.cam_elev), math.radians(s.cam_azim)
    # keep the studio sweep facing the camera from any orbit angle
    backdrop = bpy.data.objects.get("Backdrop")
    if backdrop is not None:
        backdrop.rotation_euler.z = az
    pos = center + dist * Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    cam_ob.location = pos
    # a hand-set tripod is never perfectly level
    roll = Quaternion((0.0, 0.0, 1.0), math.radians(getattr(s, "cam_roll", 0.0)))
    cam_ob.rotation_euler = ((center - pos).to_track_quat("-Z", "Y") @ roll).to_euler()
    cam.clip_start = max(0.001, dist * 0.01)
    cam.clip_end = 200.0

    cam.dof.use_dof = s.use_dof
    cam.dof.focus_object = None
    cam.dof.focus_distance = (center - pos).length
    cam.dof.aperture_fstop = s.cam_fstop
    scene.camera = cam_ob
    return cam_ob
