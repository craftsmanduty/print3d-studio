"""Helper class for building shader node trees with short code."""
import bpy

PRINCIPLED = {
    'base': "Base Color", 'metal': "Metallic", 'rough': "Roughness", 'ior': "IOR",
    'alpha': "Alpha", 'normal': "Normal", 'sss': "Subsurface Weight",
    'sss_radius': "Subsurface Radius", 'sss_scale': "Subsurface Scale",
    'spec': "Specular IOR Level", 'spec_tint': "Specular Tint", 'aniso': "Anisotropic",
    'aniso_rot': "Anisotropic Rotation", 'tangent': "Tangent", 'trans': "Transmission Weight",
    'coat': "Coat Weight", 'coat_rough': "Coat Roughness", 'coat_normal': "Coat Normal",
    'sheen': "Sheen Weight", 'sheen_rough': "Sheen Roughness", 'sheen_tint': "Sheen Tint",
    'emit': "Emission Color", 'emit_str': "Emission Strength",
}


def _is_socket(v):
    return isinstance(v, bpy.types.NodeSocket)


class NB:
    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links
        self._i = 0
        self._tc = None

    # --- basics --------------------------------------------------------
    def new(self, typ, **props):
        n = self.nodes.new(typ)
        n.location = ((self._i % 12) * 220.0, -(self._i // 12) * 320.0)
        self._i += 1
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def set(self, sock, v):
        if v is None:
            return
        if _is_socket(v):
            self.links.new(v, sock)
            return
        try:
            sock.default_value = v
        except (TypeError, ValueError):
            if isinstance(v, (tuple, list)) and len(v) == 3:
                sock.default_value = (*v, 1.0)
            elif isinstance(v, (int, float)):
                sock.default_value = (v, v, v, 1.0)[:len(sock.default_value)]
            else:
                raise

    def inp(self, node, name, v):
        s = node.inputs.get(name)
        if s is not None:
            self.set(s, v)

    @property
    def tc(self):
        if self._tc is None:
            self._tc = self.new('ShaderNodeTexCoord')
        return self._tc

    @property
    def obj(self):
        return self.tc.outputs['Object']

    # --- math ----------------------------------------------------------
    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        n = self.new('ShaderNodeMath', operation=op, use_clamp=clamp)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        self.set(n.inputs[2], c)
        return n.outputs[0]

    def add(self, a, b):
        return self.math('ADD', a, b)

    def mul(self, a, b):
        return self.math('MULTIPLY', a, b)

    def sub(self, a, b):
        return self.math('SUBTRACT', a, b)

    def _vm(self, op, a, b=None, scale=None):
        n = self.new('ShaderNodeVectorMath', operation=op)
        self.set(n.inputs[0], a)
        if b is not None:
            self.set(n.inputs[1], b)
        if scale is not None:
            sock = n.inputs.get("Scale") or n.inputs[3]
            self.set(sock, scale)
        return n

    def dot(self, a, b):
        return self._vm('DOT_PRODUCT', a, b).outputs['Value']

    def vadd(self, a, b):
        return self._vm('ADD', a, b).outputs[0]

    def vsub(self, a, b):
        return self._vm('SUBTRACT', a, b).outputs[0]

    def vmul(self, a, b):
        return self._vm('MULTIPLY', a, b).outputs[0]

    def vscale(self, a, s):
        return self._vm('SCALE', a, scale=s).outputs[0]

    def length(self, a):
        return self._vm('LENGTH', a).outputs['Value']

    def vec(self, x, y, z):
        n = self.new('ShaderNodeCombineXYZ')
        for i, v in enumerate((x, y, z)):
            self.set(n.inputs[i], v)
        return n.outputs[0]

    def separate(self, v):
        n = self.new('ShaderNodeSeparateXYZ')
        self.set(n.inputs[0], v)
        return n.outputs[0], n.outputs[1], n.outputs[2]

    def maprange(self, v, fmin, fmax, tmin, tmax, smooth=False, clamp=True):
        n = self.new('ShaderNodeMapRange', clamp=clamp)
        if smooth:
            n.interpolation_type = 'SMOOTHSTEP'
        for i, val in enumerate((v, fmin, fmax, tmin, tmax)):
            self.set(n.inputs[i], val)
        return n.outputs[0]

    def mix_float(self, fac, a, b):
        n = self.new('ShaderNodeMix', data_type='FLOAT')
        self.set(n.inputs[0], fac)
        self.set(n.inputs[2], a)
        self.set(n.inputs[3], b)
        return n.outputs[0]

    def mix_col(self, fac, a, b, blend='MIX'):
        n = self.new('ShaderNodeMix', data_type='RGBA', blend_type=blend)
        fs = next(s for s in n.inputs if s.name == "Factor" and s.type == 'VALUE')
        sa = next(s for s in n.inputs if s.name == "A" and s.type == 'RGBA')
        sb = next(s for s in n.inputs if s.name == "B" and s.type == 'RGBA')
        self.set(fs, fac)
        self.set(sa, a)
        self.set(sb, b)
        return next(s for s in n.outputs if s.type == 'RGBA')

    def ramp(self, fac, stops, interp='LINEAR'):
        n = self.new('ShaderNodeValToRGB')
        cr = n.color_ramp
        cr.interpolation = interp
        stops = sorted(stops, key=lambda s: s[0])
        els = cr.elements
        els[0].position, els[0].color = stops[0][0], (*stops[0][1][:3], 1.0)
        els[1].position, els[1].color = stops[-1][0], (*stops[-1][1][:3], 1.0)
        for p, c in stops[1:-1]:
            e = els.new(p)
            e.color = (*c[:3], 1.0)
        self.set(n.inputs[0], fac)
        return n.outputs['Color']

    # --- textures ------------------------------------------------------
    def noise(self, vec, scale, detail=2.0, rough=0.5, distortion=0.0):
        n = self.new('ShaderNodeTexNoise')
        self.inp(n, "Vector", vec)
        self.inp(n, "Scale", scale)
        self.inp(n, "Detail", detail)
        self.inp(n, "Roughness", rough)
        self.inp(n, "Distortion", distortion)
        return n

    def voronoi(self, vec, scale, feature='F1', randomness=1.0):
        n = self.new('ShaderNodeTexVoronoi', feature=feature)
        self.inp(n, "Vector", vec)
        self.inp(n, "Scale", scale)
        self.inp(n, "Randomness", randomness)
        return n

    def wave(self, vec, typ, direction, scale, distortion=0.0, detail=2.0, detail_scale=1.0, detail_rough=0.5):
        n = self.new('ShaderNodeTexWave', wave_type=typ)
        if typ == 'RINGS':
            n.rings_direction = direction
        else:
            n.bands_direction = direction
        self.inp(n, "Vector", vec)
        self.inp(n, "Scale", scale)
        self.inp(n, "Distortion", distortion)
        self.inp(n, "Detail", detail)
        self.inp(n, "Detail Scale", detail_scale)
        self.inp(n, "Detail Roughness", detail_rough)
        return n

    def white1d(self, w):
        n = self.new('ShaderNodeTexWhiteNoise', noise_dimensions='1D')
        self.inp(n, "W", w)
        return n.outputs['Value']

    def bump(self, height, distance, strength=1.0, normal=None):
        n = self.new('ShaderNodeBump')
        self.inp(n, "Strength", strength)
        self.inp(n, "Distance", distance)
        self.inp(n, "Height", height)
        if normal is not None:
            self.inp(n, "Normal", normal)
        return n.outputs['Normal']

    # --- output --------------------------------------------------------
    def principled(self, **kw):
        n = self.new('ShaderNodeBsdfPrincipled')
        for k, v in kw.items():
            self.inp(n, PRINCIPLED[k], v)
        return n

    def output(self, shader_socket):
        out = self.new('ShaderNodeOutputMaterial')
        self.links.new(shader_socket, out.inputs['Surface'])
        return out
