import math

import bpy
from mathutils import Matrix, Quaternion, Vector

from .. import utils

FOCUS = "P3D_Focus"


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
    cam.dof.focus_object = bpy.data.objects.get(FOCUS)     # a picked focus point stays
    cam.dof.focus_distance = (center - pos).length
    cam.dof.aperture_fstop = s.cam_fstop
    scene.camera = cam_ob
    return cam_ob


def focus_at_pixel(context, region, rv3d, xy):
    """Puts the focus point where the view ray through pixel `xy` hits a surface. The point is
    parented to the object it lies on, so it follows that object. Returns (name, cm) or None."""
    from bpy_extras import view3d_utils
    scene = context.scene
    origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, xy)
    ray = view3d_utils.region_2d_to_vector_3d(region, rv3d, xy)
    hit, loc, _, _, ob, _ = scene.ray_cast(context.evaluated_depsgraph_get(), origin, ray)
    if not hit:
        return None
    ob = bpy.data.objects.get(ob.name) or ob
    emp = bpy.data.objects.get(FOCUS)
    if emp is None:
        emp = bpy.data.objects.new(FOCUS, None)
        emp.empty_display_type = 'SPHERE'
        emp.hide_render = True
        utils.ensure_collection("P3D_Lights").objects.link(emp)
    emp.empty_display_size = 0.003
    emp.parent = ob
    emp.matrix_parent_inverse = ob.matrix_world.inverted()
    emp.matrix_world = Matrix.Translation(loc)
    cam = scene.camera
    cam.data.dof.use_dof = True
    cam.data.dof.focus_object = emp
    return ob.name, (loc - cam.matrix_world.translation).length * 100.0


def clear_focus(scene):
    emp = bpy.data.objects.get(FOCUS)
    if emp is not None:
        bpy.data.objects.remove(emp)
    if scene.camera is not None and scene.camera.type == 'CAMERA':
        scene.camera.data.dof.focus_object = None


# held-button camera controls: id -> (mode, camera axis, direction), see `nudge`
DRIVES = {
    "MOVE_FWD": ('MOVE', 2, -1), "MOVE_UP": ('MOVE', 1, 1), "MOVE_LEFT": ('MOVE', 0, -1),
    "MOVE_BACK": ('MOVE', 2, 1), "MOVE_DOWN": ('MOVE', 1, -1), "MOVE_RIGHT": ('MOVE', 0, 1),
    "PAN_LEFT": ('TURN', 1, 1), "TILT_UP": ('TURN', 0, 1), "ROLL_LEFT": ('TURN', 2, 1),
    "PAN_RIGHT": ('TURN', 1, -1), "TILT_DOWN": ('TURN', 0, -1), "ROLL_RIGHT": ('TURN', 2, -1),
    "ORBIT_LEFT": ('ORBIT', 1, -1), "ORBIT_UP": ('ORBIT', 0, -1),
    "ORBIT_DOWN": ('ORBIT', 0, 1), "ORBIT_RIGHT": ('ORBIT', 1, 1),
}


def nudge(scene, mode, axis, amount):
    """One step of camera control, in the camera's own axes (0 = X right, 1 = Y up, 2 = Z back).
    MOVE slides, TURN pans / tilts / rolls in place, ORBIT circles around the focus point."""
    cam = scene.camera
    mw = cam.matrix_world.copy()
    rot = mw.to_3x3().normalized()
    ax = rot.col[axis].to_3d().normalized()
    if mode == 'MOVE':
        cam.matrix_world = Matrix.Translation(ax * amount) @ mw
        return
    if mode == 'TURN':
        q = Quaternion(ax, amount)
        pos = mw.translation.copy()
        cam.matrix_world = Matrix.Translation(pos) @ q.to_matrix().to_4x4() @             Matrix.Translation(-pos) @ mw
        return
    # ORBIT: left/right around the world Z axis, up/down around the camera X axis
    emp = cam.data.dof.focus_object
    if emp is not None:
        pivot = emp.matrix_world.translation.copy()
    else:
        pivot = mw.translation - rot.col[2].to_3d().normalized() * cam.data.dof.focus_distance
    q = Quaternion(Vector((0, 0, 1)) if axis == 1 else ax, amount)
    cam.matrix_world = Matrix.Translation(pivot) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pivot) @ mw
    if emp is None:
        cam.data.dof.focus_distance = (pivot - cam.matrix_world.translation).length
