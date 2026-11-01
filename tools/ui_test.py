"""Scripted UI test in a real Blender window (not background mode).

Opens the sidebar on the "3D Print" tab with every panel expanded, presses the panel
buttons through their operators, screenshots the window after each step and quits.
Any exception from a panel draw() or an operator is printed as "UI-ERROR".

  blender --factory-startup --python tools/ui_test.py -- <screenshot_folder>
"""
import os
import sys
import traceback

import bpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = os.path.abspath(argv[0]) if argv else os.path.join(ROOT, "renders", "ui")
os.makedirs(OUT, exist_ok=True)

bpy.context.preferences.view.show_splash = False

import print3d_studio  # noqa: E402
from print3d_studio import ui  # noqa: E402

# the sidebar tab can't be switched from Python, so show the panels in the default tab
ui._Base.bl_category = "Item"
for cls in ui.classes:                       # expand every sub-panel for the screenshots
    cls.bl_options = set(getattr(cls, "bl_options", set())) - {'DEFAULT_CLOSED'}
print3d_studio.register()

def view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                return win, area
    return None, None


def run(op, **kw):
    win, area = view3d()
    region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=win, area=area, region=region):
        try:
            res = op(**kw)
            print("OP", op.idname_py(), res)
        except Exception:
            print("UI-ERROR in operator", op.idname_py())
            traceback.print_exc()


def shot(name):
    win, area = view3d()
    for a in win.screen.areas:
        a.tag_redraw()
    PENDING.append(name)


def _take(name):
    win, area = view3d()
    with bpy.context.temp_override(window=win):
        bpy.ops.screen.screenshot(filepath=os.path.join(OUT, name + ".png"))
    print("SHOT", name)


STEPS = []
PENDING = []


def step(fn):
    STEPS.append(fn)
    return fn


@step
def prepare():
    win, area = view3d()
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    sp = area.spaces.active
    sp.show_region_ui = True
    for r in area.regions:
        if r.type == 'UI':
            with bpy.context.temp_override(window=win, area=area, region=r):
                try:
                    r.active_panel_category = "3D Print"
                except Exception as e:
                    print("category switch failed:", e)
                print("active category:", getattr(r, "active_panel_category", "?"))
            # widen the sidebar so labels are readable
            with bpy.context.temp_override(window=win, area=area, region=r):
                pass
    bpy.ops.mesh.primitive_monkey_add(size=60)
    mk = bpy.context.active_object
    m = mk.modifiers.new("s", 'SUBSURF')
    m.levels = 2
    bpy.ops.object.modifier_apply(modifier="s")
    shot("01_panel_initial")


@step
def quick_scene():
    run(bpy.ops.p3d.quick_scene)
    shot("02_after_one_click_scene")


@step
def filament_change():
    ob = bpy.context.active_object
    ob.p3d.filament_type = 'PLA_SILK_DUAL'
    ob.p3d.layer_height = 0.28
    ob.p3d.print_dir = 'CUSTOM'
    ob.p3d.seam = 'RANDOM'
    win, area = view3d()
    area.spaces.active.shading.type = 'MATERIAL'
    shot("03_filament_changed")


@step
def materials_props():
    s = bpy.context.scene.p3d
    s.mat_category = 'Wood'
    s.mat_item = 'walnut'
    bpy.context.scene.cursor.location = (0.3, 1.0, 0.75)
    run(bpy.ops.p3d.add_furniture, item='mug')
    run(bpy.ops.p3d.apply_surface)
    for iid, *_ in print3d_studio.scene.furniture.ITEMS:
        bpy.context.scene.cursor.location = (3.0, -3.0, 0.0)
        run(bpy.ops.p3d.add_furniture, item=iid)
    shot("04_props_and_materials")


@step
def env_light_render():
    s = bpy.context.scene.p3d
    for preset in ('STUDIO', 'EVENING', 'GOLDEN', 'WINDOW_DAY'):
        s.light_preset = preset
        run(bpy.ops.p3d.lighting)
    run(bpy.ops.p3d.build_cove)
    run(bpy.ops.p3d.build_room)
    run(bpy.ops.p3d.camera)
    run(bpy.ops.p3d.render_setup)
    run(bpy.ops.p3d.asset_refresh)
    shot("05_lighting_render_panels")


@step
def scroll_panel():
    win, area = view3d()
    for r in area.regions:
        if r.type == 'UI':
            with bpy.context.temp_override(window=win, area=area, region=r):
                for _ in range(40):
                    bpy.ops.view2d.scroll_down(page=False)
    shot("06_panel_scrolled")


@step
def scroll_more():
    win, area = view3d()
    for r in area.regions:
        if r.type == 'UI':
            with bpy.context.temp_override(window=win, area=area, region=r):
                for _ in range(60):
                    bpy.ops.view2d.scroll_down(page=False)
    shot("07_panel_bottom")


@step
def done():
    print("UI-TEST-DONE")
    bpy.ops.wm.quit_blender()


def tick():
    if PENDING:
        _take(PENDING.pop(0))
        return 1.0
    if not STEPS:
        return None
    fn = STEPS.pop(0)
    try:
        fn()
    except Exception:
        print("UI-ERROR in step", fn.__name__)
        traceback.print_exc()
    return 1.5


bpy.app.timers.register(tick, first_interval=2.0)
