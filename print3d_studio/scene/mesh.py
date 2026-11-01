"""Builds prop and room geometry in a single bmesh, with material indices."""
import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector


def mat4(loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
    return Matrix.LocRotScale(Vector(loc), Euler(rot), Vector(scale))


class MB:
    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def _tag(self, verts=None, faces=None, mat=None, smooth=False):
        if mat not in self.mats:
            self.mats.append(mat)
        mi = self.mats.index(mat)
        if faces is None:
            faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            f.material_index = mi
            f.smooth = smooth

    def box(self, size, loc, mat, rot=(0, 0, 0), pre=None):
        m = mat4(loc, rot, size)
        if pre is not None:
            m = pre @ m
        ret = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        self._tag(ret['verts'], mat=mat)

    def slab(self, along, fixed, us, zs, T, mat, empty=()):
        """A wall of thickness T as one connected mesh: a grid of cells between the lines
        `us` (along the wall) and `zs` (height), skipping the (i, j) cells in `empty`
        (openings). Shared vertices keep displaced surfaces from cracking at the cell joins."""
        bm = self.bm

        def pt(u, z, side):
            off = fixed + side * T / 2
            return Vector((u, off, z)) if along == 'X' else Vector((off, u, z))

        vs = {(i, j, s): bm.verts.new(pt(u, z, s)) for i, u in enumerate(us) for j, z in enumerate(zs)
              for s in (-1, 1)}
        full = {(i, j) for i in range(len(us) - 1) for j in range(len(zs) - 1)} - set(empty)
        faces = []
        for i, j in full:
            for s in (-1, 1):
                faces.append(bm.faces.new([vs[i, j, s], vs[i + 1, j, s], vs[i + 1, j + 1, s], vs[i, j + 1, s]]))
            # side faces on the outline and around the openings
            for (ni, nj), a, b in (((i - 1, j), (i, j), (i, j + 1)), ((i + 1, j), (i + 1, j), (i + 1, j + 1)),
                                   ((i, j - 1), (i, j), (i + 1, j)), ((i, j + 1), (i, j + 1), (i + 1, j + 1))):
                if (ni, nj) not in full:
                    faces.append(bm.faces.new([vs[a + (-1,)], vs[b + (-1,)], vs[b + (1,)], vs[a + (1,)]]))
        self._tag(faces=faces, mat=mat)

    def cyl(self, r, depth, loc, mat, r2=None, rot=(0, 0, 0), segs=48, caps=True, pre=None):
        m = mat4(loc, rot)
        if pre is not None:
            m = pre @ m
        ret = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=segs,
                                    radius1=r, radius2=r if r2 is None else r2, depth=depth, matrix=m)
        verts = ret['verts']
        side = {f for v in verts for f in v.link_faces if len(f.verts) == 4}
        caps_f = {f for v in verts for f in v.link_faces} - side
        self._tag(faces=side, mat=mat, smooth=True)
        self._tag(faces=caps_f, mat=mat, smooth=False)

    def sphere(self, r, loc, mat, scale=(1, 1, 1), rot=(0, 0, 0), segs=24, rings=12):
        ret = bmesh.ops.create_uvsphere(self.bm, u_segments=segs, v_segments=rings, radius=r,
                                        matrix=mat4(loc, rot, scale))
        self._tag(ret['verts'], mat=mat, smooth=True)

    def lathe(self, prof, loc, mat, segs=64, closed=False, rot=(0, 0, 0)):
        """Creates a surface by revolving an (r, z) profile around the Z axis."""
        bm = self.bm
        m = mat4(loc, rot)
        rings = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ca, sa = math.cos(a), math.sin(a)
            rings.append([bm.verts.new(m @ Vector((r * ca, r * sa, z))) for r, z in prof])
        n = len(prof)
        faces = []
        for i in range(segs):
            A, B = rings[i], rings[(i + 1) % segs]
            for j in range(n if closed else n - 1):
                k = (j + 1) % n
                faces.append(bm.faces.new((A[j], B[j], B[k], A[k])))
        self._tag(faces=faces, mat=mat, smooth=True)
        bmesh.ops.remove_doubles(bm, verts=[v for ring in rings for v in ring], dist=1e-7)

    def torus(self, R, r, loc, mat, rot=(0, 0, 0), segs=48, rsegs=16, arc=2 * math.pi, arc_start=0.0):
        bm = self.bm
        m = mat4(loc, rot)
        full = abs(arc - 2 * math.pi) < 1e-6
        count = segs if full else segs + 1
        rings = []
        for i in range(count):
            a = arc_start + arc * i / segs
            ring = []
            for j in range(rsegs):
                b = 2 * math.pi * j / rsegs
                rr = R + r * math.cos(b)
                ring.append(bm.verts.new(m @ Vector((rr * math.cos(a), rr * math.sin(a), r * math.sin(b)))))
            rings.append(ring)
        faces = []
        for i in range(segs):
            A, B = rings[i], rings[(i + 1) % count]
            for j in range(rsegs):
                k = (j + 1) % rsegs
                faces.append(bm.faces.new((A[j], B[j], B[k], A[k])))
        self._tag(faces=faces, mat=mat, smooth=True)

    def to_object(self, name, coll, parent=None, bevel=0.0015):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces[:])
        # real-size box-projected UVs (1 UV unit = 1 m) so photo textures keep their scale
        uv = self.bm.loops.layers.uv.verify()
        for f in self.bm.faces:
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for lp in f.loops:
                c = lp.vert.co
                lp[uv].uv = (c.x, c.y) if ax == 2 else ((c.y, c.z) if ax == 0 else (c.x, c.z))
        me = bpy.data.meshes.new(name)
        self.bm.to_mesh(me)
        self.bm.free()
        for mt in self.mats:
            me.materials.append(mt)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        if bevel > 0:
            mod = ob.modifiers.new("Pah", 'BEVEL')
            mod.width = bevel
            mod.segments = 3
            mod.limit_method = 'ANGLE'
            mod.angle_limit = math.radians(35)
            try:
                mod.harden_normals = True
            except Exception:
                pass
        return ob
