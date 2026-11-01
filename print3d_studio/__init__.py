bl_info = {
    "name": "3D Print Studio",
    "author": "Han",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar (N) > 3D Print",
    "description": "Photorealistic filament materials, rooms, props and render setup for 3D-print models",
    "category": "Render",
}

import bpy  # noqa: E402
from bpy.app.handlers import persistent  # noqa: E402

from . import palette, properties, operators, ui  # noqa: E402
from .scene import carry  # noqa: E402

_modules = (properties, operators, ui)


@persistent
def on_scene_update(scene, depsgraph=None):
    """After every change: things on top follow their support (see scene/carry.py), and
    objects hidden in the viewport (eye icon / H) are hidden in the render as well and
    shown again when unhidden. Only objects hidden this way are touched, so a render
    visibility set by hand (camera icon) is kept."""
    p3d = getattr(scene, "p3d", None)
    if p3d is not None and p3d.carry_items:
        carry.update(scene)
    sync_render_visibility(scene, p3d)


def sync_render_visibility(scene, p3d):
    view_layer = bpy.context.view_layer
    if p3d is None or not p3d.hide_render_sync or view_layer is None:
        return
    for ob in scene.objects:
        if "p3d_render_only" in ob:
            continue
        try:
            hidden = not ob.visible_get(view_layer=view_layer)
        except (RuntimeError, TypeError):
            continue
        if hidden and not ob.hide_render:
            ob.hide_render = True
            ob["p3d_render_hidden"] = True
        elif not hidden and ob.get("p3d_render_hidden"):
            ob.hide_render = False
            del ob["p3d_render_hidden"]


def register():
    palette.load()
    for m in _modules:
        m.register()
    bpy.app.handlers.depsgraph_update_post.append(on_scene_update)


def unregister():
    if on_scene_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_scene_update)
    for m in reversed(_modules):
        m.unregister()
