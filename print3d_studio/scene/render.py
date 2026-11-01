import bpy

QUALITY = {  # samples, adaptive threshold, resolution percentage
    'PREVIEW': (96, 0.05, 50),
    'FINAL': (512, 0.01, 100),
    'ULTRA': (2048, 0.004, 100),
}

RESOLUTION = {
    'LAND_HD': (1920, 1080),
    'LAND_4K': (3840, 2160),
    'SQUARE': (2048, 2048),
    'PORTRAIT': (1080, 1350),
    'STORY': (1080, 1920),
}


def setup_units(scene):
    us = scene.unit_settings
    us.system = 'METRIC'
    us.length_unit = 'MILLIMETERS'


def enable_gpu(scene):
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
    except KeyError:
        return False
    for kind in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        devs = [d for d in prefs.devices if d.type == kind]
        if devs:
            for d in prefs.devices:
                d.use = d.type == kind
            scene.cycles.device = 'GPU'
            return True
    scene.cycles.device = 'CPU'
    return False


def setup(context, s):
    scene = context.scene
    scene.render.engine = 'CYCLES'
    cy = scene.cycles
    samples, thr, pct = QUALITY[s.render_quality]
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = thr
    cy.use_denoising = True
    try:
        cy.denoiser = 'OPENIMAGEDENOISE'
        # albedo + normal guiding keeps layer lines and fine relief that a plain denoise smears
        cy.denoising_input_passes = 'RGB_ALBEDO_NORMAL'
        cy.denoising_prefilter = 'ACCURATE'
        cy.denoising_quality = 'HIGH'
        cy.denoising_use_gpu = s.use_gpu
    except (TypeError, AttributeError):
        pass
    # 8K maps (photo woods) only cost VRAM at product-shot distances
    try:
        cy.texture_limit_render = 'OFF' if s.render_quality == 'ULTRA' else '4096'
    except (TypeError, AttributeError):
        pass
    cy.max_bounces = 12
    cy.diffuse_bounces = 4
    cy.glossy_bounces = 6
    cy.transmission_bounces = 12
    cy.transparent_max_bounces = 16
    cy.caustics_reflective = False
    cy.caustics_refractive = False
    cy.blur_glossy = 0.5
    cy.sample_clamp_indirect = 10.0
    if s.use_gpu:
        enable_gpu(scene)
    else:
        cy.device = 'CPU'

    rx, ry = RESOLUTION[s.res_preset]
    scene.render.resolution_x, scene.render.resolution_y = rx, ry
    scene.render.resolution_percentage = pct
    scene.render.film_transparent = False
    scene.render.use_persistent_data = True
    scene.render.image_settings.file_format = 'PNG'
    try:
        scene.render.image_settings.color_depth = '8'
    except TypeError:
        pass

    vs = scene.view_settings
    try:
        vs.view_transform = 'AgX'
    except TypeError:
        pass
    looks = ('AgX - Medium High Contrast', 'Medium High Contrast', 'AgX - Base Contrast')
    if getattr(s, "light_preset", "") == 'CINEMATIC':
        looks = ('AgX - High Contrast', 'High Contrast') + looks
    for look in looks:
        try:
            vs.look = look
            break
        except TypeError:
            continue
    # the cinematic sun is strong: exposing for it lets the shadowed room fall off into darkness
    vs.exposure = -0.4 if getattr(s, "light_preset", "") == 'CINEMATIC' else 0.0
    vs.gamma = 1.0
    setup_units(scene)
    lens_effects(scene, getattr(s, "photo_fx", True))


LENS_GROUP = "P3D_Lens"


def lens_effects(scene, enable=True):
    """What a real camera adds on top of the light: slight barrel distortion and lateral
    chromatic aberration, bloom around bright highlights, lens vignetting and sensor grain."""
    import bpy
    ng = bpy.data.node_groups.get(LENS_GROUP)
    if not enable:
        if scene.compositing_node_group == ng:
            scene.compositing_node_group = None
        scene.render.use_compositing = False
        return
    if ng is not None:
        bpy.data.node_groups.remove(ng)
    ng = bpy.data.node_groups.new(LENS_GROUP, 'CompositorNodeTree')
    ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    N, L = ng.nodes, ng.links

    def val(node, name, v):
        try:
            node.inputs[name].default_value = v
        except Exception:
            pass

    rl = N.new('CompositorNodeRLayers')
    rl.scene = scene
    lens = N.new('CompositorNodeLensdist')
    val(lens, "Distortion", 0.006)
    val(lens, "Dispersion", 0.012)
    val(lens, "Fit", True)                  # scale up slightly so no edge is left unsampled
    L.new(rl.outputs['Image'], lens.inputs['Image'])

    glare = N.new('CompositorNodeGlare')
    for t in ("Bloom", "BLOOM", "Fog Glow", "FOG_GLOW"):
        try:
            glare.inputs['Type'].default_value = t
            break
        except Exception:
            continue
    val(glare, "Threshold", 0.9)
    val(glare, "Strength", 0.12)
    val(glare, "Size", 0.5)
    L.new(lens.outputs['Image'], glare.inputs['Image'])

    # vignette: 1 - k r^2 (r = distance from the image center, aspect corrected)
    coords = N.new('CompositorNodeImageCoordinates')
    L.new(rl.outputs['Image'], coords.inputs['Image'])
    r2 = N.new('ShaderNodeVectorMath')
    r2.operation = 'DOT_PRODUCT'
    L.new(coords.outputs['Uniform'], r2.inputs[0])
    L.new(coords.outputs['Uniform'], r2.inputs[1])
    vig = N.new('ShaderNodeMath')
    vig.operation = 'MULTIPLY_ADD'
    L.new(r2.outputs['Value'], vig.inputs[0])
    vig.inputs[1].default_value = -0.12
    vig.inputs[2].default_value = 1.0

    # luminance grain, proportional to the signal like photon noise at base ISO
    noise = N.new('ShaderNodeTexWhiteNoise')
    noise.noise_dimensions = '3D'
    L.new(coords.outputs['Pixel'], noise.inputs['Vector'])
    grain = N.new('ShaderNodeMath')
    grain.operation = 'MULTIPLY_ADD'
    L.new(noise.outputs['Value'], grain.inputs[0])
    grain.inputs[1].default_value = 0.035
    grain.inputs[2].default_value = 1.0 - 0.0175
    gain = N.new('ShaderNodeMath')
    gain.operation = 'MULTIPLY'
    L.new(vig.outputs[0], gain.inputs[0])
    L.new(grain.outputs[0], gain.inputs[1])

    mix = N.new('ShaderNodeMix')
    mix.data_type, mix.blend_type = 'RGBA', 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    L.new(glare.outputs['Image'], mix.inputs[6])
    L.new(gain.outputs[0], mix.inputs[7])
    out = N.new('NodeGroupOutput')
    L.new(mix.outputs[2], out.inputs[0])
    scene.compositing_node_group = ng
    scene.render.use_compositing = True
