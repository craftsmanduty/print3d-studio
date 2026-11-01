import math
import os
import time

import bpy
from bpy.props import CollectionProperty, StringProperty
from mathutils import Matrix, Vector

from . import library, palette, properties, utils
from .materials import filament, surfaces
from .scene import camera, carry, decor, furniture, lighting, render, room

UNIT_SCALE = {'MM': 0.001, 'CM': 0.01, 'IN': 0.0254, 'M': 1.0}


def _meshes(context):
    return [o for o in context.selected_objects if o.type == 'MESH']


# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------
class P3D_OT_apply_filament(bpy.types.Operator):
    """Apply the 3D-print look to selected objects (using the active object's settings)"""
    bl_idname = "p3d.apply_filament"
    bl_label = "Apply 3D Print Look"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        act = context.active_object
        objs = _meshes(context)
        if not objs:
            self.report({'WARNING'}, "Select a mesh object")
            return {'CANCELLED'}
        src = act.p3d if act in objs else objs[0].p3d
        keys = [k for k in src.bl_rna.properties.keys() if k not in ('rna_type', 'name', 'material', 'is_print')]
        for o in objs:
            if o != act:
                for k in keys:
                    try:
                        setattr(o.p3d, k, getattr(src, k))
                    except Exception:
                        pass
            o.p3d.is_print = True
            filament.apply(o, context.scene)
        return {'FINISHED'}


class P3D_OT_remove_filament(bpy.types.Operator):
    """Remove the 3D-print material from the selected objects"""
    bl_idname = "p3d.remove_filament"
    bl_label = "Remove 3D Print Look"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for o in _meshes(context):
            o.p3d.is_print = False
            filament.restore_source(o)
            if o.p3d.material:
                for i, m in enumerate(o.data.materials):
                    if m == o.p3d.material:
                        o.data.materials[i] = None
        return {'FINISHED'}


class P3D_OT_scale_real(bpy.types.Operator):
    """Scale imported models to real-world size (STL files are usually in millimeters)"""
    bl_idname = "p3d.scale_real"
    bl_label = "Scale to Real Size"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        f = UNIT_SCALE[context.scene.p3d.scale_unit] / (context.scene.unit_settings.scale_length or 1.0)
        for o in _meshes(context):
            o.scale = o.scale * f
            o.location = o.location * f
            if o.p3d.is_print:
                filament.apply(o, context.scene)
            origin_to_bottom(o)
        render.setup_units(context.scene)
        return {'FINISHED'}


def origin_to_bottom(obj):
    """Moves the model's origin to the center of its underside without moving the model, so
    surface snapping (Face Project) sets it down on whatever is under the cursor."""
    meshes = {obj.data, filament.source_mesh(obj)}
    if not obj.data.vertices:
        return
    co = [v.co for v in obj.data.vertices]
    lo = Vector((min(c.x for c in co), min(c.y for c in co), min(c.z for c in co)))
    hi = Vector((max(c.x for c in co), max(c.y for c in co), max(c.z for c in co)))
    off = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    if off.length < 1e-9:
        return
    for me in meshes:
        me.transform(Matrix.Translation(-off))
        me.update()
    obj.location += obj.matrix_basis.to_3x3() @ off


def surface_snap(scene, enable=True):
    """Drag (G / Move tool) objects over the surfaces under the cursor: desk, mat, floor..."""
    ts = scene.tool_settings
    ts.use_snap = enable
    if enable:
        ts.snap_elements = {'FACE_PROJECT'}
        ts.use_snap_translate = True
        ts.use_snap_rotate = False
        ts.use_snap_scale = False
        ts.use_snap_align_rotation = False
        ts.use_snap_peel_object = False


def drop_to_surface(context, obj):
    """Sets the object down on the surface below it (desk, floor...)."""
    context.view_layer.update()
    dg = context.evaluated_depsgraph_get()
    mn, mx, c, _ = utils.world_bounds(obj)
    best = None
    for fx, fy in ((0, 0), (0.3, 0.3), (-0.3, 0.3), (0.3, -0.3), (-0.3, -0.3)):
        origin = Vector((c.x + fx * (mx.x - mn.x), c.y + fy * (mx.y - mn.y), mx.z + 0.001))
        # a sliced model has a cap per layer: step through all of its own surfaces
        for _ in range(20000):
            hit, loc, _, _, ob, _ = context.scene.ray_cast(dg, origin, Vector((0, 0, -1)))
            if not hit:
                break
            if ob is not None and (ob == obj or ob.name == obj.name):
                origin = loc - Vector((0, 0, 1e-4))
                continue
            best = loc.z if best is None else max(best, loc.z)
            break
    if best is None:
        best = 0.0
    obj.location.z += best - mn.z
    return best


class P3D_OT_drop(bpy.types.Operator):
    """Drop the selected objects onto the surface below them"""
    bl_idname = "p3d.drop"
    bl_label = "Drop to Surface"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        for o in _meshes(context):
            origin_to_bottom(o)
            drop_to_surface(context, o)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
class P3D_OT_apply_surface(bpy.types.Operator):
    """Apply the chosen library material (with its surface relief) to selected objects"""
    bl_idname = "p3d.apply_surface"
    bl_label = "Apply Material"
    bl_options = {'REGISTER', 'UNDO'}

    mat_id: StringProperty()

    def execute(self, context):
        mid = self.mat_id or context.scene.p3d.mat_item
        mat = surfaces.get(mid)
        objs = [o for o in context.selected_objects if o.type in {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}]
        for o in objs:
            if o.type == 'MESH':
                o.p3d.is_print = False
            if not o.data.materials:
                o.data.materials.append(mat)
            else:
                o.active_material = mat
        return {'FINISHED'}


class P3D_OT_add_filament_color(bpy.types.Operator):
    """Permanently add a new color to the filament palette"""
    bl_idname = "p3d.add_filament_color"
    bl_label = "Add Color to Palette"

    def execute(self, context):
        s = context.scene.p3d
        palette.add_user_color(s.nf_type, s.nf_name, utils.linear_to_hex(s.nf_color))
        self.report({'INFO'}, "Added: %s" % s.nf_name)
        return {'FINISHED'}


class P3D_OT_add_custom_material(bpy.types.Operator):
    """Permanently add a new material to the material library"""
    bl_idname = "p3d.add_custom_material"
    bl_label = "Add Material to Library"

    def execute(self, context):
        s = context.scene.p3d
        mid = "user_" + bpy.path.clean_name(s.nm_name).lower()
        hx = utils.linear_to_hex(s.nm_color)
        params = {"base": hx, "light": hx, "rough": round(s.nm_rough, 3)}
        if s.nm_builder == 'wood':
            dark = utils.linear_to_hex(tuple(c * 0.45 for c in s.nm_color))
            params["dark"] = dark
        palette.add_user_material({"id": mid, "name": s.nm_name, "category": s.nm_category,
                                   "builder": s.nm_builder, "params": params})
        old = bpy.data.materials.get("P3D_" + mid)
        if old:
            surfaces.make("P3D_" + mid, s.nm_builder, params, rebuild=True)
        self.report({'INFO'}, "Added: %s" % s.nm_name)
        return {'FINISHED'}


class P3D_OT_reload_palette(bpy.types.Operator):
    """Reload the JSON palette files"""
    bl_idname = "p3d.reload_palette"
    bl_label = "Reload Palette"

    def execute(self, context):
        palette.load()
        return {'FINISHED'}


class P3D_OT_open_user_dir(bpy.types.Operator):
    """Open the user palette / asset folder"""
    bl_idname = "p3d.open_user_dir"
    bl_label = "Open User Folder"

    def execute(self, context):
        bpy.ops.wm.path_open(filepath=palette.user_dir())
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Room & props
# ---------------------------------------------------------------------------
class P3D_OT_build_room(bpy.types.Operator):
    """(Re)build the room from the settings"""
    bl_idname = "p3d.build_room"
    bl_label = "Build Room"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        room.build_room(context, context.scene.p3d)
        return {'FINISHED'}


class P3D_OT_build_cove(bpy.types.Operator):
    """Create a curved seamless backdrop for product shots"""
    bl_idname = "p3d.build_cove"
    bl_label = "Build Studio Backdrop"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        room.build_cove(context, context.scene.p3d)
        return {'FINISHED'}


class P3D_OT_clear_room(bpy.types.Operator):
    """Delete the room / backdrop objects"""
    bl_idname = "p3d.clear_room"
    bl_label = "Clear Room"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        coll = bpy.data.collections.get(room.COLLECTION)
        if coll:
            utils.clear_collection(coll)
        return {'FINISHED'}


class P3D_OT_add_furniture(bpy.types.Operator):
    """Add the prop at the 3D cursor"""
    bl_idname = "p3d.add_furniture"
    bl_label = "Add Prop"
    bl_options = {'REGISTER', 'UNDO'}

    item: StringProperty()

    def execute(self, context):
        iid = self.item or context.scene.p3d.furniture_item
        root = furniture.add(iid, context)
        if root is None:
            self.report({'WARNING'}, "Could not add '%s' - is its model imported into the asset library?" % iid)
            return {'CANCELLED'}
        for o in context.selected_objects:
            o.select_set(False)
        root.select_set(True)
        context.view_layer.objects.active = root
        return {'FINISHED'}


def asset_dirs():
    dirs = [os.path.join(os.path.dirname(__file__), "assets"), os.path.join(palette.user_dir(), "assets")]
    try:
        extra = bpy.context.preferences.addons[__package__].preferences.asset_dir
        if extra:
            dirs.append(bpy.path.abspath(extra))
    except (KeyError, AttributeError):
        pass
    return [d for d in dirs if os.path.isdir(d)]


class P3D_OT_asset_refresh(bpy.types.Operator):
    """Scan the asset library folders for .blend files"""
    bl_idname = "p3d.asset_refresh"
    bl_label = "Refresh Library"

    def execute(self, context):
        entries = []
        files = [os.path.join(d, fn) for d in asset_dirs() for fn in sorted(os.listdir(d))
                 if fn.lower().endswith(".blend")]
        lib_files = set(library.model_files())
        for path in files + sorted(lib_files):
            try:
                with bpy.data.libraries.load(path) as (src, _):
                    names = list(src.collections)
            except Exception as e:
                print("[3D Print Studio] could not read:", path, e)
                continue
            if path in lib_files and names:
                # downloaded models: one entry, the collection named like the asset if any
                stem = os.path.basename(os.path.dirname(path))
                names = [next((n for n in names if n == stem), names[-1])]
            entries += ["%s::%s" % (path, n) for n in names]
        properties.set_assets(entries)
        self.report({'INFO'}, "%d assets found" % len(entries))
        return {'FINISHED'}


class P3D_OT_asset_append(bpy.types.Operator):
    """Append the library asset at the 3D cursor"""
    bl_idname = "p3d.asset_append"
    bl_label = "Append from Library"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        key = context.scene.p3d.asset_item
        if "::" not in key:
            self.report({'WARNING'}, "Refresh the library first")
            return {'CANCELLED'}
        path, name = key.rsplit("::", 1)
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.collections = [name]
        library.fix_missing_images(bpy.data.images)
        cur = context.scene.cursor.location
        target = utils.ensure_collection(furniture.COLLECTION)
        for coll in dst.collections:
            if coll is None:
                continue
            target.children.link(coll)
            for o in coll.all_objects:
                if o.parent is None:
                    o.location += cur
        return {'FINISHED'}


class P3D_OT_asset_import(bpy.types.Operator):
    """Import downloaded asset zips (Poliigon / ambientCG style): models go to the asset
    library, textures become materials in the Material Library"""
    bl_idname = "p3d.asset_import"
    bl_label = "Import Asset Zips"

    directory: StringProperty(subtype='DIR_PATH')
    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    filter_glob: StringProperty(default="*.zip", options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        from . import textures
        want = int(textures.resolution().rstrip("kK") or 4)
        done = {"model": 0, "texture": 0}
        for f in self.files:
            path = os.path.join(self.directory, f.name)
            try:
                name, kind, _ = library.import_zip(path, want)
            except Exception as e:
                self.report({'WARNING'}, "%s: %s" % (f.name, e))
                continue
            done[kind] += 1
            if kind == "texture":
                library.register_texture(name)
        palette.load()
        bpy.ops.p3d.asset_refresh()
        self.report({'INFO'}, "Imported %d models, %d textures" % (done["model"], done["texture"]))
        return {'FINISHED'}


class P3D_OT_asset_save(bpy.types.Operator):
    """Save the selected objects to the asset library permanently"""
    bl_idname = "p3d.asset_save"
    bl_label = "Save Selection to Library"

    def execute(self, context):
        objs = list(context.selected_objects)
        if not objs:
            self.report({'WARNING'}, "Select the objects to save")
            return {'CANCELLED'}
        name = bpy.path.clean_name(context.scene.p3d.asset_name) or "Asset"
        folder = os.path.join(palette.user_dir(), "assets")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, name + ".blend")
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(folder, "%s_%d.blend" % (name, n))
        pivot = Vector((sum(o.location.x for o in objs) / len(objs), sum(o.location.y for o in objs) / len(objs),
                        min(utils.world_bounds(o)[0].z for o in objs)))
        coll = bpy.data.collections.new(name)
        roots = [o for o in objs if o.parent not in objs]
        for o in objs:
            coll.objects.link(o)
        for o in roots:
            o.location -= pivot
        try:
            bpy.data.libraries.write(path, {coll}, fake_user=True)
        finally:
            for o in roots:
                o.location += pivot
            bpy.data.collections.remove(coll)
        bpy.ops.p3d.asset_refresh()
        self.report({'INFO'}, "Saved: " + path)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Lighting / camera / render
# ---------------------------------------------------------------------------
class P3D_OT_lighting(bpy.types.Operator):
    """Set up the selected lighting preset"""
    bl_idname = "p3d.lighting"
    bl_label = "Set Up Lighting"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            lighting.setup(context, context.scene.p3d)
        except FileNotFoundError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        return {'FINISHED'}


class P3D_OT_camera(bpy.types.Operator):
    """Create a product camera aimed at the selected object"""
    bl_idname = "p3d.camera"
    bl_label = "Set Up Product Camera"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        camera.setup(context, context.scene.p3d)
        return {'FINISHED'}


class P3D_OT_pick_focus(bpy.types.Operator):
    """Click a point on any object: the camera keeps that exact point in focus, even when the
    camera or the object moves"""
    bl_idname = "p3d.pick_focus"
    bl_label = "Pick Focus Point"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D' and context.scene.camera

    def invoke(self, context, event):
        context.window.cursor_modal_set('EYEDROPPER')
        context.area.header_text_set("Click the point to focus on  -  Esc / right click: cancel")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _end(self, context):
        context.window.cursor_modal_restore()
        context.area.header_text_set(None)

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self._end(context)
            return {'CANCELLED'}
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
            x, y = event.mouse_x - region.x, event.mouse_y - region.y
            if not (0 <= x < region.width and 0 <= y < region.height):
                return {'RUNNING_MODAL'}
            hit = camera.focus_at_pixel(context, region, region.data, (x, y))
            self._end(context)
            if hit is None:
                self.report({'WARNING'}, "Nothing under the cursor")
                return {'CANCELLED'}
            context.scene.p3d.use_dof = True
            self.report({'INFO'}, "Focus on %s (%.1f cm from the camera)" % hit)
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


class P3D_OT_clear_focus(bpy.types.Operator):
    """Remove the picked focus point (focus goes back to the model's center)"""
    bl_idname = "p3d.clear_focus"
    bl_label = "Clear Focus Point"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        camera.clear_focus(context.scene)
        return {'FINISHED'}


class P3D_OT_cam_nudge(bpy.types.Operator):
    """Move or turn the camera one step (steps are set below the buttons)"""
    bl_idname = "p3d.cam_nudge"
    bl_label = "Nudge Camera"
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.EnumProperty(items=[('MOVE', "Move", ""), ('TURN', "Turn", ""), ('ORBIT', "Orbit", "")])
    axis: bpy.props.IntProperty(min=0, max=2)
    sign: bpy.props.IntProperty(default=1, min=-1, max=1)

    @classmethod
    def poll(cls, context):
        return context.scene.camera is not None

    def execute(self, context):
        s = context.scene.p3d
        step = s.cam_step_move if self.mode == 'MOVE' else math.radians(s.cam_step_turn)
        camera.nudge(context.scene, self.mode, self.axis, self.sign * step)
        return {'FINISHED'}


class P3D_OT_cam_drive(bpy.types.Operator):
    """Held camera button: one step at once, then after a short pause the camera keeps
    moving at a constant speed until the mouse button is released"""
    bl_idname = "p3d.cam_drive"
    bl_label = "Drive Camera"
    bl_options = {'UNDO', 'INTERNAL'}

    HOLD_DELAY = 0.3                                          # s before the steady motion
    RATE = 10.0                                               # steps per second while held

    def invoke(self, context, event):
        s = context.scene.p3d
        if context.scene.camera is None or s.cam_drive not in camera.DRIVES:
            s.cam_drive = 'NONE'
            return {'CANCELLED'}
        self.mode, self.axis, self.sign = camera.DRIVES[s.cam_drive]
        self._step(context, 1.0)
        self._t0 = self._last = time.monotonic()
        wm = context.window_manager
        self._timer = wm.event_timer_add(1 / 60, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _step(self, context, n):
        s = context.scene.p3d
        step = s.cam_step_move if self.mode == 'MOVE' else math.radians(s.cam_step_turn)
        camera.nudge(context.scene, self.mode, self.axis, self.sign * step * n)
        for a in context.screen.areas if context.screen else ():
            if a.type == 'VIEW_3D':
                a.tag_redraw()

    def modal(self, context, event):
        now = time.monotonic()
        if event.type == 'TIMER':
            if now - self._t0 > self.HOLD_DELAY:
                self._step(context, (now - self._last) * self.RATE)
            self._last = now
            return {'PASS_THROUGH'}
        if ((event.type == 'LEFTMOUSE' and event.value == 'RELEASE')
                or event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'} or now - self._t0 > 120):
            context.window_manager.event_timer_remove(self._timer)
            context.scene.p3d.cam_drive = 'NONE'
            return {'FINISHED'}
        return {'PASS_THROUGH'}


class P3D_OT_render_setup(bpy.types.Operator):
    """Apply photorealistic Cycles render settings"""
    bl_idname = "p3d.render_setup"
    bl_label = "Apply Render Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        render.setup(context, context.scene.p3d)
        return {'FINISHED'}


class P3D_OT_render(bpy.types.Operator):
    """Render the image (F12)"""
    bl_idname = "p3d.render"
    bl_label = "Render Image"

    def execute(self, context):
        bpy.ops.render.render('INVOKE_DEFAULT')
        return {'FINISHED'}


class P3D_OT_quick_scene(bpy.types.Operator):
    """Place the active model in a complete photorealistic scene with one click"""
    bl_idname = "p3d.quick_scene"
    bl_label = "One-Click Scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'WARNING'}, "Select your 3D-print model (mesh) first")
            return {'CANCELLED'}
        s = context.scene.p3d
        scene = context.scene
        render.setup_units(scene)
        scene.unit_settings.scale_length = 1.0

        if max(obj.dimensions) > 3.0:
            obj.scale = obj.scale * 0.001
            self.report({'INFO'}, "Model assumed to be in mm and scaled to real size")
        context.view_layer.update()

        if not obj.p3d.is_print:
            obj.p3d.is_print = True
        filament.apply(obj, scene)
        origin_to_bottom(obj)
        if s.surface_snap:
            surface_snap(scene)

        # the model is placed in world space below: let go of whatever it was resting on
        if obj.parent is not None and carry.MARK in obj:
            carry.release_all_of(obj)
        props = bpy.data.collections.get(furniture.COLLECTION)
        if props is not None:
            # the room furniture has no place on a studio sweep; it comes back with the room
            props.hide_viewport = props.hide_render = s.quick_preset == 'STUDIO'

        if s.quick_preset == 'STUDIO':
            room.build_cove(context, s)
            _, _, c, _ = utils.world_bounds(obj)
            obj.location.x -= c.x
            obj.location.y -= c.y
            drop_to_surface(context, obj)
            s.light_preset = 'STUDIO'
        else:
            coll = bpy.data.collections.get(room.COLLECTION)
            if coll is None or not any(o.name.startswith("Walls") for o in coll.objects):
                room.build_room(context, s)
            desk = next((o for o in bpy.data.objects if o.get("p3d_item") == "desk"), None)
            if desk is None:
                desk = furniture.add("desk", context, location=Vector((0.0, s.room_d / 2 - 0.45, 0.0)))
                if s.quick_decor:
                    decor.furnish(context, desk)
            top = desk.location + Vector((0, -0.08, furniture.DESK_TOP))
            _, _, c, _ = utils.world_bounds(obj)
            mn = utils.world_bounds(obj)[0]
            obj.location += Vector((top.x - c.x, top.y - c.y, top.z + 0.05 - mn.z))
            drop_to_surface(context, obj)
            s.light_preset = {'DESK_CINEMATIC': 'CINEMATIC', 'DESK_DAY': 'WINDOW_DAY',
                              'DESK_GOLDEN': 'GOLDEN', 'DESK_EVENING': 'EVENING'}[s.quick_preset]

        if s.quick_preset == 'DESK_CINEMATIC':
            # low, close to the desk, wide open: the lamp, plant and books behind melt into bokeh
            s.cam_elev, s.cam_margin, s.cam_fstop = 10.0, 1.9, 2.8
        else:                           # the product shot the other scenes are made for
            s.cam_elev, s.cam_margin, s.cam_fstop = 20.0, 1.4, 4.0

        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        context.view_layer.update()
        render.setup(context, s)
        lighting.setup(context, s)
        camera.setup(context, s, obj)
        # look through the new camera so the user sees the shot, not the room from outside
        if context.area is not None and context.area.type == 'VIEW_3D':
            space = context.space_data
            space.region_3d.view_perspective = 'CAMERA'
            if space.shading.type in {'SOLID', 'WIREFRAME'}:
                space.shading.type = 'MATERIAL'
        return {'FINISHED'}


classes = (
    P3D_OT_apply_filament, P3D_OT_remove_filament, P3D_OT_scale_real, P3D_OT_drop,
    P3D_OT_apply_surface, P3D_OT_add_filament_color, P3D_OT_add_custom_material,
    P3D_OT_reload_palette, P3D_OT_open_user_dir,
    P3D_OT_build_room, P3D_OT_build_cove, P3D_OT_clear_room, P3D_OT_add_furniture,
    P3D_OT_asset_refresh, P3D_OT_asset_append, P3D_OT_asset_import, P3D_OT_asset_save,
    P3D_OT_lighting, P3D_OT_camera, P3D_OT_pick_focus, P3D_OT_clear_focus, P3D_OT_cam_nudge, P3D_OT_cam_drive, P3D_OT_render_setup, P3D_OT_render, P3D_OT_quick_scene,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
