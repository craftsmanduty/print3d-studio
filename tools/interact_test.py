"""Interactive check in a real Blender window with simulated mouse / keyboard events:
drag the model with G over the desk props (surface snapping), click a focus point,
press the camera buttons. Prints "FAIL ..." lines on problems and screenshots each step.

  blender --factory-startup --enable-event-simulate --python tools/interact_test.py -- <stl> <out folder>

Set P3D_LIBRARY to the asset library folder so the scanned plants load.
"""
import os
import sys
import time
import traceback

import bpy
from bpy_extras import view3d_utils
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
argv = sys.argv[sys.argv.index("--") + 1:]
STL, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
os.makedirs(OUT, exist_ok=True)
bpy.context.preferences.view.show_splash = False

import print3d_studio  # noqa: E402
from print3d_studio import ui, utils  # noqa: E402
ui._Base.bl_category = "Item"
print3d_studio.register()

STEPS = []


def step(fn):
    STEPS.append(fn)
    return fn


def view3d():
    win = bpy.context.window_manager.windows[0]
    area = max((a for a in win.screen.areas if a.type == 'VIEW_3D'), key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == 'WINDOW')
    return win, area, region


def override():
    win, area, region = view3d()
    return bpy.context.temp_override(window=win, area=area, region=region)


def to_window(co):
    win, area, region = view3d()
    p = view3d_utils.location_3d_to_region_2d(region, region.data, co)
    return int(p.x + region.x), int(p.y + region.y)


def ev(t, v='NOTHING', xy=None, **kw):
    win = view3d()[0]
    if xy is not None:
        kw.update(x=xy[0], y=xy[1])
    win.event_simulate(t, v, **kw)


def model():
    return bpy.data.objects["benchy"] if "benchy" in bpy.data.objects else \
        next(o for o in bpy.data.objects if o.type == 'MESH' and o.p3d.is_print)


def shot(name):
    with bpy.context.temp_override(window=view3d()[0]):
        bpy.ops.screen.screenshot(filepath=os.path.join(OUT, name + ".png"))


def surface_below(ob):
    """Highest surface under the model's footprint center, ignoring the model itself. The
    model is hidden for the ray: stepping past its own faces would also skip a support
    surface that lies exactly at the model's bottom."""
    mn, mx, c, _ = utils.world_bounds(ob)
    ob.hide_viewport = True
    try:
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        hit, loc, _, _, h, _ = bpy.context.scene.ray_cast(dg, Vector((c.x, c.y, mx.z + 0.5)), Vector((0, 0, -1)))
    finally:
        ob.hide_viewport = False
        ob.select_set(True)                      # hiding dropped it from the selection
        bpy.context.view_layer.objects.active = ob
        bpy.context.view_layer.update()
    return (loc.z, h.name) if hit else (None, None)


@step
def setup():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.ops.wm.stl_import(filepath=STL)
    ob = bpy.context.selected_objects[0]
    bpy.context.view_layer.objects.active = ob
    win, area, region = view3d()
    area.spaces.active.show_region_ui = True
    with override():
        bpy.ops.p3d.quick_scene()
    area.spaces.active.shading.type = 'SOLID'
    ts = bpy.context.scene.tool_settings
    print("SNAP", ts.use_snap, set(ts.snap_elements))
    if not ts.use_snap or 'FACE_PROJECT' not in ts.snap_elements:
        print("FAIL snapping not enabled")
    # zoom out a little so the desk props are on screen
    with override():
        bpy.ops.view3d.view_camera()


@step
def overview():
    win, area, region = view3d()
    rv3d = region.data
    rv3d.view_perspective = 'PERSP'
    ob = model()
    _, _, c, _ = utils.world_bounds(ob)
    rv3d.view_location = c + Vector((0, 0.15, 0))
    rv3d.view_distance = 1.3
    from mathutils import Euler
    rv3d.view_rotation = Euler((1.05, 0, 0.0)).to_quaternion()
    shot("01_start")


def drag_to(target, name):
    ob = model()
    start = to_window(ob.matrix_world.translation + Vector((0, 0, 0.01)))
    end = to_window(target)
    ev('MOUSEMOVE', xy=start)
    ev('G', 'PRESS', xy=start)
    ev('G', 'RELEASE', xy=start)
    for i in range(1, 11):
        f = i / 10
        ev('MOUSEMOVE', xy=(int(start[0] + (end[0] - start[0]) * f), int(start[1] + (end[1] - start[1]) * f)))
    ev('LEFTMOUSE', 'PRESS', xy=end)
    ev('LEFTMOUSE', 'RELEASE', xy=end)
    DRAGS.append(name)


DRAGS = []


def check_drag():
    name = DRAGS.pop(0)
    bpy.context.view_layer.update()
    ob = model()
    mn = utils.world_bounds(ob)[0]
    z, what = surface_below(ob)
    print("DRAG %-6s bottom %.4f  surface %s (%s)" % (name, mn.z, z, what))
    if z is None or abs(mn.z - z) > 0.002:
        print("FAIL drag", name, "model does not sit on the surface under it")
    shot("02_drag_" + name)


@step
def drag_mat():
    mat = next(o for o in bpy.data.objects if o.get("p3d_item") == "cutting_mat")
    drag_to(mat.matrix_world.translation + Vector((0.12, 0.05, 0.003)), "mat")


step(check_drag)


@step
def drag_books():
    books = next(o for o in bpy.data.objects if o.get("p3d_item") == "books")
    top = max(utils.world_bounds(c)[1].z for c in books.children if c.type == 'MESH')
    drag_to(books.matrix_world.translation + Vector((0, 0, top - books.matrix_world.translation.z)), "books")


step(check_drag)


@step
def drag_desk():
    desk = next(o for o in bpy.data.objects if o.get("p3d_item") == "desk")
    drag_to(desk.matrix_world.translation + Vector((-0.35, -0.2, 0.75)), "desk")


step(check_drag)


@step
def camera_view():
    win, area, region = view3d()
    bpy.context.view_layer.objects.active = model()
    with override():
        bpy.ops.p3d.camera()                     # re-aim at the model's new place
    region.data.view_perspective = 'CAMERA'
    shot("03_camera_view")


@step
def focus_pick():
    with override():
        print("PICK", bpy.ops.p3d.pick_focus('INVOKE_DEFAULT'))
    ob = model()
    _, mx, c, _ = utils.world_bounds(ob)
    FOCUS_AT.append(to_window(c))
    ev('MOUSEMOVE', xy=FOCUS_AT[0])
    ev('LEFTMOUSE', 'PRESS', xy=FOCUS_AT[0])
    ev('LEFTMOUSE', 'RELEASE', xy=FOCUS_AT[0])


FOCUS_AT = []


@step
def focus_check():
    cam = bpy.context.scene.camera
    f = cam.data.dof.focus_object
    print("FOCUS", f and f.name, f and f.parent and f.parent.name,
          f and tuple(round(v, 4) for v in f.matrix_world.translation))
    if f is None or f.parent is None or f.parent.name != model().name:
        print("FAIL focus point not on the model")


@step
def nudges():
    cam = bpy.context.scene.camera
    s = bpy.context.scene.p3d
    m0 = cam.matrix_world.copy()
    fwd = -m0.to_3x3().col[2].normalized()
    with override():
        bpy.ops.p3d.cam_nudge(mode='MOVE', axis=2, sign=-1)
    d = cam.matrix_world.translation - m0.translation
    print("MOVE forward", tuple(round(v, 5) for v in d), "dot", round(d.dot(fwd), 5))
    if abs(d.dot(fwd) - s.cam_step_move) > 1e-6:
        print("FAIL forward move")
    m1 = cam.matrix_world.copy()
    with override():
        bpy.ops.p3d.cam_nudge(mode='TURN', axis=1, sign=1)
    if (cam.matrix_world.translation - m1.translation).length > 1e-6:
        print("FAIL pan moved the camera")
    fwd2 = -cam.matrix_world.to_3x3().col[2].normalized()
    print("PAN left changes heading x", round(fwd.x, 4), "->", round(fwd2.x, 4))
    emp = cam.data.dof.focus_object
    piv = emp.matrix_world.translation
    r0 = (cam.matrix_world.translation - piv).length
    with override():
        for _ in range(10):
            bpy.ops.p3d.cam_nudge(mode='ORBIT', axis=1, sign=1)
    r1 = (cam.matrix_world.translation - piv).length
    print("ORBIT radius %.5f -> %.5f" % (r0, r1))
    if abs(r0 - r1) > 1e-5:
        print("FAIL orbit changed the distance")
    shot("04_after_nudges")


@step
def panel():
    win, area, region = view3d()
    for r in area.regions:
        if r.type == 'UI':
            with bpy.context.temp_override(window=win, area=area, region=r):
                bpy.ops.view2d.scroll_up(page=True)
    shot("05_panel")


HOLD = []


@step
def hold_press():
    """Holds a camera Move button: a real click on it when P3D_BTN="x,y" (window pixels of
    the Forward button, read off 05_panel.png) is set, else the same property change."""
    cam = bpy.context.scene.camera
    HOLD[:] = [cam.matrix_world.copy(), time.monotonic()]
    btn = os.environ.get("P3D_BTN")
    if btn:
        xy = tuple(int(v) for v in btn.split(","))
        ev('MOUSEMOVE', xy=xy)
        ev('LEFTMOUSE', 'PRESS', xy=xy)
    else:
        win, area, _ = view3d()
        ui_region = next(r for r in area.regions if r.type == 'UI')
        with bpy.context.temp_override(window=win, area=area, region=ui_region):
            bpy.context.scene.p3d.cam_drive = 'MOVE_FWD'
    print("HOLD drive state", bpy.context.scene.p3d.cam_drive)


@step
def hold_release():
    cam = bpy.context.scene.camera
    s = bpy.context.scene.p3d
    m0, t0 = HOLD
    held = time.monotonic() - t0
    d = (cam.matrix_world.translation - m0.translation).dot(-m0.to_3x3().col[2].normalized())
    ev('LEFTMOUSE', 'RELEASE', xy=tuple(int(v) for v in os.environ.get("P3D_BTN", "5,5").split(",")))
    want = s.cam_step_move * (1 + (held - 0.3) * 10)
    print("HOLD %.2f s moved %.4f m (expected about %.4f)" % (held, d, want))
    if abs(d - want) > s.cam_step_move * 3:
        print("FAIL hold did not move at the steady speed")
    HOLD.append(cam.matrix_world.copy())


@step
def hold_stopped():
    cam = bpy.context.scene.camera
    moved = (cam.matrix_world.translation - HOLD[2].translation).length
    print("AFTER RELEASE moved %.5f, drive %s" % (moved, bpy.context.scene.p3d.cam_drive))
    if moved > 1e-6 or bpy.context.scene.p3d.cam_drive != 'NONE':
        print("FAIL camera kept moving after the release")


@step
def hide_mat():
    mat = next(o for o in bpy.data.objects if o.get("p3d_item") == "cutting_mat")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    mat.select_set(True)
    bpy.context.view_layer.objects.active = mat
    win, area, region = view3d()
    region.data.view_perspective = 'PERSP'
    xy = (region.x + region.width // 2, region.y + region.height // 2)
    ev('MOUSEMOVE', xy=xy)
    ev('H', 'PRESS', xy=xy)
    ev('H', 'RELEASE', xy=xy)


@step
def hide_check():
    mat = next(o for o in bpy.data.objects if o.get("p3d_item") == "cutting_mat")
    print("HIDE mat hidden %s render hidden %s" % (mat.hide_get(), mat.hide_render))
    if not mat.hide_get() or not mat.hide_render:
        print("FAIL hidden mat still renders")
    win, area, region = view3d()
    xy = (region.x + region.width // 2, region.y + region.height // 2)
    ev('MOUSEMOVE', xy=xy)
    ev('H', 'PRESS', xy=xy, alt=True)
    ev('H', 'RELEASE', xy=xy, alt=True)


@step
def unhide_check():
    mat = next(o for o in bpy.data.objects if o.get("p3d_item") == "cutting_mat")
    print("UNHIDE mat hidden %s render hidden %s" % (mat.hide_get(), mat.hide_render))
    if mat.hide_get() or mat.hide_render:
        print("FAIL unhidden mat stays out of the render")


def item(iid):
    return next(o for o in bpy.data.objects if o.get("p3d_item") == iid)


CARRY = {}


@step
def carry_parents():
    desk = item("desk")
    rels = {o.name: o.parent.name if o.parent else None
            for o in [model()] + [item(i) for i in ("cutting_mat", "books", "mug", "plant", "plant_orchid")]}
    print("PARENTS", rels)
    for i in ("cutting_mat", "books", "mug", "plant", "plant_orchid"):
        if item(i).parent is not desk:
            print("FAIL", i, "is not carried by the desk")
    region = view3d()[2]
    region.data.view_perspective = 'PERSP'
    # drag the desk with G over the floor, Face Project snapping on: the desk has to stay
    # on the floor (not climb onto the mat or books it carries) and its load has to follow
    CARRY["before"] = {o.name: o.matrix_world.translation.copy()
                       for o in [desk, model(), item("books"), item("cutting_mat")]}
    for o in bpy.context.selected_objects:
        o.select_set(False)
    desk.select_set(True)
    bpy.context.view_layer.objects.active = desk
    from mathutils import Euler
    rv3d = region.data
    rv3d.view_location = desk.matrix_world.translation + Vector((0.3, -0.6, 0.3))
    rv3d.view_distance = 3.5
    rv3d.view_rotation = Euler((1.0, 0, 0)).to_quaternion()


@step
def desk_drag():
    desk = item("desk")
    start = to_window(desk.matrix_world.translation + Vector((0, -0.45, 0)))
    end = to_window(desk.matrix_world.translation + Vector((0.3, -0.45, 0)))
    ev('MOUSEMOVE', xy=start)
    ev('G', 'PRESS', xy=start)
    ev('G', 'RELEASE', xy=start)
    for i in range(1, 21):
        f = i / 20
        ev('MOUSEMOVE', xy=(int(start[0] + (end[0] - start[0]) * f), int(start[1] + (end[1] - start[1]) * f)))
    ev('LEFTMOUSE', 'PRESS', xy=end)
    ev('LEFTMOUSE', 'RELEASE', xy=end)


@step
def carry_check():
    desk = item("desk")
    dd = desk.matrix_world.translation - CARRY["before"][desk.name]
    for name, p0 in CARRY["before"].items():
        d = bpy.data.objects[name].matrix_world.translation - p0
        print("CARRY %-26s moved %s" % (name, tuple(round(v, 4) for v in d)))
        if dd.length < 0.05 or (d - dd).length > 1e-4:
            print("FAIL", name, "did not move along with the desk")
    if abs(desk.matrix_world.translation.z) > 1e-4:
        print("FAIL desk left the floor (z %.4f)" % desk.matrix_world.translation.z)
    shot("05b_desk_moved")


@step
def room_resize():
    s = bpy.context.scene.p3d
    desk = item("desk")
    from print3d_studio import utils as u
    CARRY["gap"] = s.room_d / 2 - u.world_bounds(bpy.data.objects["Desk"])[1].y
    CARRY["d"] = s.room_d
    win, area, _ = view3d()
    with bpy.context.temp_override(window=win, area=area):
        for d in (3.3, 3.1, 2.9, 2.7):                         # like a drag on the field
            s.room_d = d


@step
def room_check():
    s = bpy.context.scene.p3d
    walls = bpy.data.objects.get("Walls")
    from print3d_studio import utils as u
    desk = item("desk")
    gap = s.room_d / 2 - u.world_bounds(bpy.data.objects["Desk"])[1].y
    back = u.world_bounds(walls)[1].y if walls else None
    print("ROOM depth %.2f -> %.2f, walls rebuilt to y %.3f, desk gap to back wall %.4f -> %.4f"
          % (CARRY["d"], s.room_d, back or 0, CARRY["gap"], gap))
    if walls is None or abs(back - (s.room_d / 2 + 0.12)) > 1e-3:
        print("FAIL room was not rebuilt after the size change")
    if abs(gap - CARRY["gap"]) > 1e-3:
        print("FAIL desk did not keep its distance to the wall")
    shot("06_room_resized")


@step
def mug_to_floor():
    mug = item("mug")
    for o in bpy.context.selected_objects:
        o.select_set(False)
    mug.select_set(True)
    bpy.context.view_layer.objects.active = mug
    m = mug.matrix_world.copy()
    m.translation.z = 0.0                                   # set down on the floor
    mug.matrix_world = m


@step
def mug_check():
    mug = item("mug")
    print("MUG parent", mug.parent and mug.parent.name)
    if mug.parent is not None:
        print("FAIL mug on the floor is still carried by", mug.parent.name)


@step
def done():
    print("INTERACT-TEST-DONE")
    bpy.ops.wm.quit_blender()


def tick():
    if not STEPS:
        return None
    fn = STEPS.pop(0)
    try:
        fn()
    except Exception:
        print("FAIL exception in", fn.__name__)
        traceback.print_exc()
    return 2.0


bpy.app.timers.register(tick, first_interval=2.0)
