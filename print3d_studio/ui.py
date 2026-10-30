import bpy

from .scene import furniture


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "3D Print"


class P3D_PT_main(_Base, bpy.types.Panel):
    bl_label = "3D Print Studio"

    def draw(self, context):
        s = context.scene.p3d
        col = self.layout.column(align=True)
        col.prop(s, "quick_preset", text="")
        col.prop(s, "quick_decor")
        row = self.layout.row()
        row.scale_y = 1.6
        row.operator("p3d.quick_scene", icon='SCENE')
        box = self.layout.box()
        box.label(text="Scale", icon='FIXED_SIZE')
        ob = context.active_object
        if ob is not None and ob.type == 'MESH':
            d = ob.dimensions * 1000.0 * (context.scene.unit_settings.scale_length or 1.0)
            box.label(text="Size: %.1f x %.1f x %.1f mm" % tuple(d))
        r = box.row(align=True)
        r.prop(s, "scale_unit", text="")
        r.operator("p3d.scale_real", text="Scale")
        box.operator("p3d.drop", icon='TRIA_DOWN_BAR')


class P3D_PT_print(_Base, bpy.types.Panel):
    bl_label = "Print & Filament"
    bl_parent_id = "P3D_PT_main"

    def draw(self, context):
        lay = self.layout
        ob = context.active_object
        if ob is None or ob.type != 'MESH':
            lay.label(text="Select a mesh object", icon='INFO')
            return
        p = ob.p3d
        col = lay.column(align=True)
        col.prop(p, "filament_type", text="Type")
        row = col.row(align=True)
        row.enabled = not p.use_custom_color
        row.prop(p, "filament_color", text="Color")
        row = col.row(align=True)
        row.prop(p, "use_custom_color")
        if p.use_custom_color:
            row.prop(p, "custom_color", text="")

        col = lay.column(align=True)
        col.label(text="Print Settings", icon='MOD_ARRAY')
        col.prop(p, "layer_height")
        col.prop(p, "line_width")
        col.prop(p, "print_dir", text="Direction")
        if p.print_dir == 'CUSTOM':
            col.prop(p, "tilt_x")
            col.prop(p, "tilt_y")
        col.prop(p, "layer_strength")
        col.prop(p, "variation")
        col.prop(p, "seam")
        if p.seam == 'ALIGNED':
            col.prop(p, "seam_angle")
        col.prop(p, "top_lines")
        col.prop(p, "real_layers")
        sub = col.column(align=True)
        sub.active = p.real_layers
        sub.prop(p, "flaws")
        col.prop(p, "wear")
        col.prop(p, "rainbow_period")

        row = lay.row(align=True)
        row.scale_y = 1.3
        row.operator("p3d.apply_filament", icon='CHECKMARK',
                     text="Apply" if not p.is_print else "Copy to Selected / Refresh")
        row.operator("p3d.remove_filament", icon='X', text="")
        if p.is_print:
            lay.label(text="Changes are applied live", icon='INFO')


class P3D_PT_materials(_Base, bpy.types.Panel):
    bl_label = "Material Library"
    bl_parent_id = "P3D_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.p3d
        col = self.layout.column(align=True)
        col.prop(s, "mat_category", text="")
        col.prop(s, "mat_item", text="")
        col.operator("p3d.apply_surface", icon='MATERIAL')


class P3D_PT_room(_Base, bpy.types.Panel):
    bl_label = "Room & Environment"
    bl_parent_id = "P3D_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.p3d
        lay = self.layout
        col = lay.column(align=True)
        col.label(text="Room", icon='HOME')
        col.prop(s, "room_w")
        col.prop(s, "room_d")
        col.prop(s, "room_h")
        col.prop(s, "room_wall_mat")
        col.prop(s, "room_floor_mat")
        col.prop(s, "room_window")
        if s.room_window != 'NONE':
            col.prop(s, "window_w")
            col.prop(s, "window_h")
            col.prop(s, "window_sill")
        row = col.row(align=True)
        row.prop(s, "room_ceiling", toggle=True)
        row.prop(s, "room_front", toggle=True)
        row.prop(s, "room_baseboard", toggle=True)
        lay.operator("p3d.build_room", icon='MOD_BUILD')

        col = lay.column(align=True)
        col.label(text="Studio Backdrop", icon='IMAGE_BACKGROUND')
        col.prop(s, "cove_color")
        row = col.row(align=True)
        row.prop(s, "cove_w")
        row.prop(s, "cove_d")
        row = col.row(align=True)
        row.prop(s, "cove_h")
        row.prop(s, "cove_r")
        lay.operator("p3d.build_cove", icon='MESH_PLANE')
        lay.operator("p3d.clear_room", icon='TRASH')


class P3D_PT_furniture(_Base, bpy.types.Panel):
    bl_label = "Props"
    bl_parent_id = "P3D_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.p3d
        lay = self.layout
        lay.label(text="Added at the 3D cursor", icon='PIVOT_CURSOR')
        grid = lay.grid_flow(row_major=True, columns=2, even_columns=True, align=True)
        for iid, label, icon, _ in furniture.ITEMS:
            grid.operator("p3d.add_furniture", text=label, icon=icon).item = iid

        box = lay.box()
        box.label(text="My Asset Library", icon='ASSET_MANAGER')
        row = box.row(align=True)
        row.prop(s, "asset_item", text="")
        row.operator("p3d.asset_refresh", text="", icon='FILE_REFRESH')
        box.operator("p3d.asset_append", icon='IMPORT')
        row = box.row(align=True)
        row.prop(s, "asset_name", text="")
        row.operator("p3d.asset_save", text="Save", icon='EXPORT')


class P3D_PT_light(_Base, bpy.types.Panel):
    bl_label = "Lighting & Camera"
    bl_parent_id = "P3D_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.p3d
        lay = self.layout
        col = lay.column(align=True)
        col.prop(s, "light_preset", text="")
        col.prop(s, "light_strength")
        if s.light_preset in ('WINDOW_DAY', 'GOLDEN'):
            col.prop(s, "sun_elev")
            col.prop(s, "sun_azim")
        if s.light_preset == 'HDRI':
            col.prop(s, "hdri_path", text="")
            col.prop(s, "hdri_strength")
            col.prop(s, "hdri_rot")
        lay.operator("p3d.lighting", icon='LIGHT_SUN')

        col = lay.column(align=True)
        col.label(text="Camera", icon='CAMERA_DATA')
        col.prop(s, "cam_lens")
        col.prop(s, "cam_elev")
        col.prop(s, "cam_azim")
        col.prop(s, "cam_margin")
        col.prop(s, "cam_roll")
        col.prop(s, "use_dof")
        if s.use_dof:
            col.prop(s, "cam_fstop")
        lay.operator("p3d.camera", icon='OUTLINER_OB_CAMERA')


class P3D_PT_render(_Base, bpy.types.Panel):
    bl_label = "Render"
    bl_parent_id = "P3D_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.p3d
        lay = self.layout
        col = lay.column(align=True)
        col.prop(s, "render_quality")
        col.prop(s, "res_preset", text="Size")
        col.prop(s, "use_gpu")
        col.prop(s, "photo_fx")
        lay.operator("p3d.render_setup", icon='SETTINGS')
        row = lay.row()
        row.scale_y = 1.5
        row.operator("p3d.render", icon='RENDER_STILL')


class P3D_PT_palette(_Base, bpy.types.Panel):
    bl_label = "Extend Palette"
    bl_parent_id = "P3D_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.p3d
        lay = self.layout
        col = lay.column(align=True)
        col.label(text="New Filament Color", icon='COLOR')
        col.prop(s, "nf_type", text="")
        col.prop(s, "nf_name", text="")
        col.prop(s, "nf_color", text="")
        col.operator("p3d.add_filament_color", icon='ADD')

        col = lay.column(align=True)
        col.label(text="New Library Material", icon='MATERIAL')
        col.prop(s, "nm_name", text="")
        col.prop(s, "nm_category", text="")
        col.prop(s, "nm_builder", text="")
        col.prop(s, "nm_color", text="")
        col.prop(s, "nm_rough")
        col.operator("p3d.add_custom_material", icon='ADD')

        row = lay.row(align=True)
        row.operator("p3d.reload_palette", icon='FILE_REFRESH')
        row.operator("p3d.open_user_dir", icon='FILE_FOLDER', text="Folder")


classes = (P3D_PT_main, P3D_PT_print, P3D_PT_materials, P3D_PT_room, P3D_PT_furniture,
           P3D_PT_light, P3D_PT_render, P3D_PT_palette)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
