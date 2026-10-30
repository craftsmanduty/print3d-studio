import math

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       PointerProperty, StringProperty)

from . import palette
from .scene import furniture


def _apply(self, context):
    obj = self.id_data
    if obj is not None and obj.type == 'MESH' and self.is_print:
        from .materials import filament
        filament.apply(obj, context.scene)


def _type_changed(self, context):
    self["filament_color"] = 0
    _apply(self, context)


class P3D_ObjectProps(bpy.types.PropertyGroup):
    is_print: BoolProperty(default=False)
    material: PointerProperty(type=bpy.types.Material)

    filament_type: EnumProperty(name="Filament Type", items=palette.enum_types, update=_type_changed)
    filament_color: EnumProperty(name="Color", items=palette.enum_colors, update=_apply)
    use_custom_color: BoolProperty(name="Custom Color", default=False, update=_apply)
    custom_color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0, max=1,
                                      default=(0.8, 0.1, 0.1), update=_apply)

    layer_height: FloatProperty(name="Layer Height (mm)", default=0.2, min=0.02, max=1.0,
                                step=1, precision=2, update=_apply)
    line_width: FloatProperty(name="Line Width (mm)", default=0.42, min=0.1, max=1.5,
                              step=1, precision=2, update=_apply)
    print_dir: EnumProperty(name="Print Direction", default='Z+', update=_apply, items=[
        ('Z+', "Z+ (As modeled)", "Printed as modeled, building upwards"),
        ('Z-', "Z- (Upside down)", "Printed flipped upside down"),
        ('Y+', "Y+ (Back face on bed)", ""),
        ('Y-', "Y- (Front face on bed)", ""),
        ('X+', "X+ (Left side on bed)", ""),
        ('X-', "X- (Right side on bed)", ""),
        ('CUSTOM', "Custom Angle", "Set the print direction with an X/Y tilt"),
    ])
    tilt_x: FloatProperty(name="Tilt X", subtype='ANGLE', default=0.0, update=_apply)
    tilt_y: FloatProperty(name="Tilt Y", subtype='ANGLE', default=0.0, update=_apply)
    layer_strength: FloatProperty(name="Layer Visibility", default=1.0, min=0.0, max=3.0, update=_apply)
    variation: FloatProperty(name="Layer Irregularity", default=0.35, min=0.0, max=1.0, update=_apply)
    seam: EnumProperty(name="Seam", default='ALIGNED', update=_apply, items=[
        ('ALIGNED', "Aligned", "Seam on a single line"),
        ('RANDOM', "Random", "Seam at a different spot on every layer"),
        ('NONE', "None", ""),
    ])
    seam_angle: FloatProperty(name="Seam Angle", subtype='ANGLE', default=math.radians(90), update=_apply)
    top_lines: BoolProperty(name="Top Surface Lines", default=True, update=_apply)
    real_layers: BoolProperty(
        name="Real Layer Geometry", default=True, update=_apply,
        description="Rebuild the model as real stacked layers (sliced at mid-layer like a slicer) so "
                    "sloped tops and silhouettes show true stair steps. Turn off to edit the model")
    flaws: FloatProperty(
        name="Print Imperfections", default=1.0, min=0.0, max=3.0, update=_apply,
        description="Real printer flaws in the layer geometry: Z wobble, extrusion width "
                    "variation and elephant foot (1 = a typical well tuned printer, 0 = perfect)")
    wear: FloatProperty(
        name="Dust & Handling", default=1.0, min=0.0, max=3.0, update=_apply,
        description="Fine dust specks on upward faces and faint matte smudges from handling")
    rainbow_period: FloatProperty(name="Color Cycle Height (mm)", default=25.0, min=1.0, max=500.0, update=_apply)


def _mat_default(mid):
    return palette.mat_number(mid)


class P3D_SceneProps(bpy.types.PropertyGroup):
    # one-click scene
    quick_preset: EnumProperty(name="Scene", items=[
        ('DESK_DAY', "Room + Desk (Daylight)", ""),
        ('DESK_GOLDEN', "Room + Desk (Golden Hour)", ""),
        ('DESK_EVENING', "Room + Desk (Evening)", ""),
        ('STUDIO', "Studio Backdrop", ""),
    ])
    quick_decor: BoolProperty(name="Add Desk Decor", default=True)
    scale_unit: EnumProperty(name="Model Units", items=[
        ('MM', "Millimeters (STL default)", ""), ('CM', "Centimeters", ""), ('IN', "Inches", ""),
        ('M', "Meters", "")])

    # material library
    mat_category: EnumProperty(name="Category", items=palette.enum_categories)
    mat_item: EnumProperty(name="Material", items=palette.enum_mats_in_cat)

    # room
    room_w: FloatProperty(name="Width", default=4.0, min=1.0, max=30.0, unit='LENGTH')
    room_d: FloatProperty(name="Depth", default=3.5, min=1.0, max=30.0, unit='LENGTH')
    room_h: FloatProperty(name="Height", default=2.7, min=2.0, max=8.0, unit='LENGTH')
    room_wall_mat: EnumProperty(name="Walls", items=palette.enum_all_mats, default=_mat_default('paint_warm'))
    room_floor_mat: EnumProperty(name="Floor", items=palette.enum_all_mats, default=_mat_default('parquet_oak'))
    room_window: EnumProperty(name="Window", default='LEFT', items=[
        ('NONE', "None", ""), ('LEFT', "Left Wall", ""), ('RIGHT', "Right Wall", ""), ('BACK', "Back Wall", "")])
    window_w: FloatProperty(name="Window Width", default=1.4, min=0.3, max=6.0, unit='LENGTH')
    window_h: FloatProperty(name="Window Height", default=1.4, min=0.3, max=4.0, unit='LENGTH')
    window_sill: FloatProperty(name="Sill Height", default=0.9, min=0.0, max=3.0, unit='LENGTH')
    room_ceiling: BoolProperty(name="Ceiling", default=True)
    room_front: BoolProperty(name="Front Wall", default=False)
    room_baseboard: BoolProperty(name="Baseboard", default=True)

    cove_w: FloatProperty(name="Width", default=1.6, min=0.2, unit='LENGTH')
    cove_d: FloatProperty(name="Depth", default=1.4, min=0.2, unit='LENGTH')
    cove_h: FloatProperty(name="Height", default=1.0, min=0.2, unit='LENGTH')
    cove_r: FloatProperty(name="Curve Radius", default=0.35, min=0.01, unit='LENGTH')
    cove_color: FloatVectorProperty(name="Backdrop Color", subtype='COLOR', size=3, min=0, max=1,
                                    default=(0.72, 0.72, 0.72))

    # props
    furniture_item: EnumProperty(name="Prop", items=[(i[0], i[1], "", i[2], n) for n, i in enumerate(furniture.ITEMS)])
    asset_item: EnumProperty(name="Library", items=lambda self, ctx: _asset_items())
    asset_name: StringProperty(name="Name", default="My_Asset")

    # extending the palette
    nf_type: EnumProperty(name="Type", items=palette.enum_types)
    nf_name: StringProperty(name="Color Name", default="New Color")
    nf_color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0, max=1, default=(0.5, 0.2, 0.6))
    nm_name: StringProperty(name="Material Name", default="New Material")
    nm_category: StringProperty(name="Category", default="My Materials")
    nm_builder: EnumProperty(name="Material Type", items=[
        ('plastic', "Plastic / Paint", ""), ('paint', "Wall Paint", ""), ('wood', "Wood", ""),
        ('metal', "Metal", ""), ('ceramic', "Ceramic", ""), ('fabric', "Fabric", ""), ('leather', "Leather", ""),
        ('concrete', "Concrete / Stone", ""), ('marble', "Marble", ""), ('glass', "Glass", ""),
        ('carpet', "Carpet", ""), ('paper', "Paper", "")])
    nm_color: FloatVectorProperty(name="Color", subtype='COLOR', size=3, min=0, max=1, default=(0.6, 0.45, 0.3))
    nm_rough: FloatProperty(name="Roughness", default=0.5, min=0, max=1)

    # lighting & camera
    light_preset: EnumProperty(name="Lighting", default='WINDOW_DAY', items=[
        ('WINDOW_DAY', "Daylight (Window)", ""), ('GOLDEN', "Golden Hour", ""),
        ('STUDIO', "Studio (3 Softboxes)", ""), ('EVENING', "Evening / Lamp", ""), ('HDRI', "HDRI File", "")])
    light_strength: FloatProperty(name="Light Strength", default=1.0, min=0.0, max=10.0)
    sun_elev: FloatProperty(name="Sun Elevation", default=32.0, min=-5, max=90)
    sun_azim: FloatProperty(name="Sun Side Angle", default=25.0, min=-90, max=90)
    hdri_path: StringProperty(name="HDRI", subtype='FILE_PATH')
    hdri_strength: FloatProperty(name="HDRI Strength", default=1.0, min=0.0)
    hdri_rot: FloatProperty(name="HDRI Rotation", default=0.0, min=-180, max=180)

    cam_lens: FloatProperty(name="Focal Length (mm)", default=85.0, min=10, max=300)
    cam_fstop: FloatProperty(name="Aperture (f/)", default=4.0, min=0.7, max=32)
    cam_elev: FloatProperty(name="Camera Elevation", default=20.0, min=-30, max=89)
    cam_azim: FloatProperty(name="Camera Orbit Angle", default=-30.0, min=-180, max=180)
    cam_margin: FloatProperty(name="Framing Margin", default=1.4, min=0.8, max=5.0)
    cam_roll: FloatProperty(name="Camera Roll", default=0.6, min=-15, max=15,
                            description="Slight tilt of the horizon in degrees, like a hand-set tripod")
    use_dof: BoolProperty(name="Depth of Field (Bokeh)", default=True)

    # render
    render_quality: EnumProperty(name="Quality", default='FINAL', items=[
        ('PREVIEW', "Preview (fast)", ""), ('FINAL', "Final", ""), ('ULTRA', "Ultra", "")])
    res_preset: EnumProperty(name="Resolution", default='SQUARE', items=[
        ('SQUARE', "Square 2048x2048", ""), ('LAND_HD', "Landscape 1920x1080", ""), ('LAND_4K', "Landscape 4K", ""),
        ('PORTRAIT', "Portrait 4:5 (1080x1350)", ""), ('STORY', "Portrait 9:16 (1080x1920)", "")])
    use_gpu: BoolProperty(name="Use GPU", default=True)
    photo_fx: BoolProperty(name="Lens Effects", default=True,
                           description="Chromatic aberration, slight distortion, bloom, vignetting and "
                                       "sensor grain like a real camera photo")


_ASSETS = [("NONE", "(Library empty - Refresh)", "", 0)]


def _asset_items():
    return _ASSETS


def set_assets(entries):
    global _ASSETS
    _ASSETS = [(e, e.replace("::", " > "), "", i) for i, e in enumerate(entries)] or \
        [("NONE", "(Library empty)", "", 0)]


class P3D_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    asset_dir: StringProperty(name="Extra Asset Folder", subtype='DIR_PATH',
                              description="Folder containing your .blend asset files")
    texture_res: EnumProperty(name="Photo Texture Resolution", default="4k", items=[
        ("2k", "2K (fast)", ""), ("4k", "4K (recommended)", ""),
        ("8k", "8K (extreme close-ups, ~150 MB per wood)", "")])

    def draw(self, context):
        self.layout.prop(self, "asset_dir")
        self.layout.prop(self, "texture_res")
        self.layout.label(text="User palette folder: " + palette.user_dir())


classes = (P3D_ObjectProps, P3D_SceneProps, P3D_Preferences)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.p3d = PointerProperty(type=P3D_ObjectProps)
    bpy.types.Scene.p3d = PointerProperty(type=P3D_SceneProps)


def unregister():
    del bpy.types.Scene.p3d
    del bpy.types.Object.p3d
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
