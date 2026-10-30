bl_info = {
    "name": "3D Print Studio",
    "author": "Han",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar (N) > 3D Print",
    "description": "Photorealistic filament materials, rooms, props and render setup for 3D-print models",
    "category": "Render",
}

from . import palette, properties, operators, ui  # noqa: E402

_modules = (properties, operators, ui)


def register():
    palette.load()
    for m in _modules:
        m.register()


def unregister():
    for m in reversed(_modules):
        m.unregister()
