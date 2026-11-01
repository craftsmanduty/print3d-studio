"""Real layer geometry: rebuilds a model as the stack of slices an FDM printer lays down.

Every layer is the cross-section of the model at mid-layer height, extruded straight up by one
layer height (the way slicers work). Sloped tops become real terraces and every silhouette
becomes a real staircase; the bead rounding is still done by the filament shader.
"""
import math

import numpy as np
from mathutils import Matrix, Vector, geometry


def _weld(co, tris, tol):
    keys = np.round(co / tol).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.reshape(-1)
    return co[first], inverse[tris]


def _contours(co, tris, z, gap, tz=None):
    """Closed contour loops (lists of xy) of a triangle mesh at height z. `tz` = optional
    precomputed (corner heights, min, max) of every triangle, so each layer only touches the
    triangles it actually cuts."""
    if tz is None:
        h = co[tris, 2]
        tz = (h, h.min(1), h.max(1))
    hit = (tz[1] < z) & (tz[2] > z)
    t, zt = tris[hit], tz[0][hit] - z
    if not len(t):
        return []
    p = co[t]                                              # (T, 3, 3)
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    pts, keys = [], []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        cross = (zt[:, a] * zt[:, b]) < 0
        f = np.where(cross, zt[:, a] / np.where(cross, zt[:, a] - zt[:, b], 1.0), 0.0)
        pts.append(p[:, a, :2] + (p[:, b, :2] - p[:, a, :2]) * f[:, None])
        va, vb = t[:, a], t[:, b]
        keys.append(np.where(cross, np.minimum(va, vb) * 4294967296 + np.maximum(va, vb), -1))
    pts, keys = np.stack(pts, 1), np.stack(keys, 1)        # (T, 3, 2), (T, 3)
    # the two crossed edges of every triangle form one segment
    order = np.argsort(keys < 0, axis=1, kind='stable')[:, :2]
    rows = np.arange(len(t))[:, None]
    sp, sk = pts[rows, order], keys[rows, order]
    # orient segments counter-clockwise around the solid: direction . (z x n) > 0
    side = np.stack([-n[:, 1], n[:, 0]], 1)
    flip = ((sp[:, 1] - sp[:, 0]) * side).sum(1) < 0
    sp[flip] = sp[flip][:, ::-1]
    sk[flip] = sk[flip][:, ::-1]

    nxt, where = {}, {}
    for (k0, k1), (p0, p1) in zip(sk.tolist(), sp.tolist()):
        nxt[k0] = k1
        where[k0] = p0
        where.setdefault(k1, p1)
    # open chains (holes in the mesh) start where nothing leads in
    targets = set(nxt.values())
    starts = [k for k in nxt if k not in targets] + list(nxt)
    loops, chains, seen = [], [], set()
    for start in starts:
        if start in seen:
            continue
        pts, k = [], start
        while k in nxt and k not in seen:
            seen.add(k)
            pts.append(where[k])
            k = nxt[k]
        if k == start:
            if len(pts) >= 3:
                loops.append(pts)
        else:
            pts.append(where[k])
            chains.append(pts)
    loops.extend(_stitch(chains, gap))
    return loops


def _stitch(chains, gap):
    """Closes open contour chains (non-manifold meshes) by joining each end to the nearest
    chain start, so a leaky STL still slices into closed layers."""
    loops = []
    chains = [c for c in chains if len(c) >= 2]
    while chains:
        cur = chains.pop()
        while True:
            ex, ey = cur[-1]
            own = math.hypot(cur[0][0] - ex, cur[0][1] - ey)
            best, dist = None, own
            for i, c in enumerate(chains):
                dd = math.hypot(c[0][0] - ex, c[0][1] - ey)
                if dd < dist and dd <= gap:
                    best, dist = i, dd
            if best is None:
                break
            cur = cur + chains.pop(best)
        if len(cur) >= 3:
            loops.append(cur)
    return loops


def _simplify(loop, min_len):
    out = [loop[0]]
    for x, y in loop[1:]:
        if math.hypot(x - out[-1][0], y - out[-1][1]) >= min_len:
            out.append((x, y))
    if len(out) > 3 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < min_len:
        out.pop()
    return out if len(out) >= 3 else None


def _area(loop):
    a = np.asarray(loop)
    return 0.5 * float(np.dot(a[:, 0], np.roll(a[:, 1], -1)) - np.dot(np.roll(a[:, 0], -1), a[:, 1]))


def _inside(pt, loop):
    a = np.asarray(loop)
    x0, y0 = a[:, 0], a[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    x, y = pt
    cross = (y0 > y) != (y1 > y)
    xs = x0 + (y - y0) * (x1 - x0) / np.where(y1 != y0, y1 - y0, 1.0)
    return bool(np.count_nonzero(cross & (xs > x)) % 2)


def _groups(cap):
    """Splits a layer's loops into outer boundaries (CCW) each with the holes (CW) inside it,
    so islands nested in holes are filled on their own."""
    outers, holes = [], []
    for item in cap:
        (outers if _area(item[2]) > 0 else holes).append(item)
    outers.sort(key=lambda it: _area(it[2]))                   # smallest first
    groups = {id(o): [o] for o in outers}
    for h in holes:
        for o in outers:
            if _inside(h[2][0], o[2]):
                groups[id(o)].append(h)
                break
    return list(groups.values())


class Flaws:
    """Printer imperfections in millimeters (scaled by `amount`; 0 = a perfect machine).

    Typical values for a well tuned hobby printer: the Z lead screw (8 mm pitch) wobbles the
    layers about 0.01 mm, extrusion width varies ~0.006 mm from layer to layer and along the
    path, and the squished first layer bulges outwards ("elephant foot") ~0.15 mm."""
    wobble = 0.010
    wobble_pitch = 8.0
    jitter = 0.005
    width = 0.006
    along = 0.004
    elephant = (0.15, 0.05)

    def __init__(self, amount=1.0, mm=1.0, seed=0):
        self.k, self.mm = amount, mm
        self.rng = np.random.default_rng(seed)
        self.ph = self.rng.uniform(0, 2 * math.pi, 6)

    def apply(self, loop, layer_index, z_mm):
        if self.k <= 0:
            return loop
        k, mm, r = self.k, self.mm, self.rng
        a = np.asarray(loop, dtype=np.float64)
        t = np.roll(a, -1, 0) - np.roll(a, 1, 0)
        t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
        nrm = np.stack([t[:, 1], -t[:, 0]], 1)               # outward for our loop winding
        x_mm, y_mm = a[:, 0] / mm, a[:, 1] / mm
        off = r.normal(0.0, self.width) + self.along * (
            np.sin(x_mm * 1.9 + self.ph[0] + z_mm * 0.7) * np.sin(y_mm * 1.6 + self.ph[1] - z_mm * 0.5))
        if layer_index < len(self.elephant):
            off = off + self.elephant[layer_index]
        w = 2 * math.pi * z_mm / self.wobble_pitch
        shift = np.array([self.wobble * math.sin(w + self.ph[2]), self.wobble * math.cos(w + self.ph[3])])
        shift = shift + r.normal(0.0, self.jitter, 2)
        a = a + nrm * (off[:, None] * k * mm) + shift * k * mm
        return a.tolist()


INNER = 99.0          # edge-distance value of the infill area (beyond the perimeter band)


def _smooth_tangents(a, h):
    """Unit tangents of a closed polyline measured over +-h of arc length. Neighbour-to-
    neighbour tangents of a dense, slightly jittery outline are noisy; offsetting along them
    folds the inset ring into tiny zigzags."""
    m = len(a)
    seg = np.hypot(*(np.roll(a, -1, 0) - a).T)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    h = min(h, total / 6.0) if total > 0 else 0.0

    def at(q):
        q = np.mod(q, total) if total > 0 else q
        j = np.clip(np.searchsorted(s, q, side='right') - 1, 0, m - 1)
        f = (q - s[j]) / np.maximum(seg[j], 1e-12)
        return a[j] + (a[(j + 1) % m] - a[j]) * f[:, None]

    t = at(s[:-1] + h) - at(s[:-1] - h)
    return t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)


def _unfold(ring, t):
    """Collapses inset points that would step backwards along the outline (local fold-overs
    at concave spots) onto the previous point, so the ring never crosses itself."""
    r = ring.tolist()
    tl = t.tolist()
    lx, ly = r[0]
    for i in range(1, len(r)):
        x, y = r[i]
        if (x - lx) * tl[i][0] + (y - ly) * tl[i][1] <= 0.0:
            r[i] = [lx, ly]
        else:
            lx, ly = x, y
    return np.asarray(r)


def _rings(loops, band):
    """Inset every loop by up to `band` towards the solid (the top perimeter loops), but never
    past half the local wall thickness. Returns [(ring_points, inset_distances)].

    The inset b at a point is valid when the moved point keeps at least b clearance from every
    outline (that is the offset curve); the largest valid b <= band is found by bisection."""
    from mathutils.kdtree import KDTree
    # densify long straight edges so the clearance test sees the whole outline, not only corners
    step = band / 3.0
    pts = []
    for l in loops:
        a = np.asarray(l, dtype=np.float64)
        nxt = np.roll(a, -1, 0)
        k = np.maximum(1, (np.hypot(*(nxt - a).T) / step).astype(np.int64))
        e = np.repeat(np.arange(len(a)), k)
        f = (np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)) / np.repeat(k, k)
        pts.extend((a[e] + (nxt[e] - a[e]) * f[:, None]).tolist())
    kd = KDTree(len(pts))
    for i, (x, y) in enumerate(pts):
        kd.insert((x, y, 0.0), i)
    kd.balance()

    def clear(p):
        return np.array([kd.find((x, y, 0.0))[2] for x, y in p.tolist()])

    out = []
    for loop in loops:
        a = np.asarray(loop, dtype=np.float64)
        t = _smooth_tangents(a, band * 0.5)
        inward = np.stack([-t[:, 1], t[:, 0]], 1)              # the solid is on the left
        b = np.full(len(a), band)
        bad = clear(a + inward * band) < band * 0.97
        if bad.any():
            lo, hi = np.zeros(bad.sum()), np.full(bad.sum(), band)
            ab, ib = a[bad], inward[bad]
            for _ in range(6):
                mid = 0.5 * (lo + hi)
                ok = clear(ab + ib * mid[:, None]) >= mid * 0.97
                lo, hi = np.where(ok, mid, lo), np.where(ok, hi, mid)
            # stay short of the wall's midline: on a wall about two bands thick the rings of
            # both sides would otherwise touch or cross, the infill between them turns inside
            # out and the cap gets filled over the hole instead of the wall (tube chimney top)
            b[bad] = lo * 0.92
        ring = _unfold(a + inward * b[:, None], t)
        A, Ar = _area(a), _area(ring)
        if not ((0 < Ar < A) or (Ar < A < 0)):                   # inverted: no band here
            ring, b = a.copy(), np.zeros(len(a))
        out.append((ring.tolist(), b))
    return out


def _restore_dropped(tri, sizes):
    """The scanline filler silently skips outline points that are (nearly) collinear or very
    close. Those points still exist in the perimeter band next to the cap, so skipping them
    leaves hairline cracks. Fan every skipped run back into the triangle that bridges it."""
    used = {i for t in tri for i in t}
    runs, off = {}, 0
    for m in sizes:
        loop = range(off, off + m)
        keep = [i for i in loop if i in used]
        if len(keep) < m and keep:
            for a, b in zip(keep, keep[1:] + keep[:1]):
                gap = (b - a) % m - 1 if m else 0
                if gap > 0:
                    runs[(a, b)] = [off + (a - off + s) % m for s in range(1, gap + 1)]
        off += m
    if not runs:
        return tri
    out = []
    for t in tri:
        t = list(t)
        for e in range(3):
            a, b, c = t[e], t[(e + 1) % 3], t[(e + 2) % 3]
            run = runs.get((a, b)) or (runs.get((b, a)) or [])[::-1]
            if run:
                chain = [a] + run + [b]
                out.extend((chain[s], chain[s + 1], c) for s in range(len(chain) - 1))
                break
        else:
            out.append(tuple(t))
    return out


def _fill(group_items):
    """Triangulates loops (outer + holes); items are (bottom_indices, top_indices, points).
    Returns [(top_tri, bottom_tri, points)], all counter-clockwise seen from above (flip the
    bottom one for a downward cap)."""
    polys = [[Vector((x, y, 0.0)) for x, y in loop] for _, _, loop in group_items]
    try:
        tri = geometry.tessellate_polygon(polys)
    except Exception:
        return []
    pts = [p for _, _, loop in group_items for p in loop]
    lower = [i for lo, _, _ in group_items for i in lo]
    upper = [i for _, up, _ in group_items for i in up]
    tri = _restore_dropped(tri, [len(loop) for _, _, loop in group_items])
    out = []
    for i0, i1, i2 in tri:
        pa, pb, pc = pts[i0], pts[i1], pts[i2]
        if (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pb[1] - pa[1]) * (pc[0] - pa[0]) < 0:
            i1, i2 = i2, i1
        out.append(((upper[i0], upper[i1], upper[i2]), (lower[i0], lower[i1], lower[i2]),
                    (pts[i0], pts[i1], pts[i2])))
    return out


def _nothing(q):
    return np.zeros(len(q), dtype=bool)


class _Raster:
    """Grid covering all layers; turns layer outlines into a coverage bitmap."""

    def __init__(self, layers, cell, tol):
        pts = [p for loops in layers for l in loops for p in l]
        a = np.asarray(pts, dtype=np.float64) if pts else np.zeros((1, 2))
        pad = tol + 2 * cell
        self.x0, self.y0 = a[:, 0].min() - pad, a[:, 1].min() - pad
        self.cell = cell
        self.w = int(math.ceil((a[:, 0].max() + pad - self.x0) / cell)) + 1
        self.h = int(math.ceil((a[:, 1].max() + pad - self.y0) / cell)) + 1
        self.r = max(0, int(round(tol / cell)))

    def cover(self, loops):
        """covered(points) for one layer: inside its outlines, or less than `tol` outside them
        (a ledge narrower than about one extrusion line cannot carry a skin line, it is just
        the side of a slightly shifted wall). Scanline fill + square dilation, all numpy."""
        if not loops:
            return _nothing
        x0, y0, c, w, h = self.x0, self.y0, self.cell, self.w, self.h
        rows, cols = [], []
        for l in loops:
            a = np.asarray(l, dtype=np.float64)
            b = np.roll(a, -1, 0)
            ya, yb = a[:, 1], b[:, 1]
            lo, hi = np.minimum(ya, yb), np.maximum(ya, yb)
            # pixel rows whose centre y lies in [lo, hi)
            r0 = np.ceil((lo - y0) / c - 0.5).astype(np.int64)
            r1 = np.ceil((hi - y0) / c - 0.5).astype(np.int64)
            cnt = np.maximum(r1 - r0, 0)
            if not cnt.sum():
                continue
            e = np.repeat(np.arange(len(a)), cnt)
            r = np.repeat(r0, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
            yc = y0 + (r + 0.5) * c
            xa, xb, yya, yyb = a[e, 0], b[e, 0], ya[e], yb[e]
            xc = xa + (yc - yya) * (xb - xa) / (yyb - yya)
            rows.append(r)
            cols.append(np.clip(np.ceil((xc - x0) / c - 0.5).astype(np.int64), 0, w))
        if not rows:
            return _nothing
        tog = np.zeros((h, w + 1), dtype=np.int32)
        np.add.at(tog, (np.concatenate(rows), np.concatenate(cols)), 1)
        m = (np.cumsum(tog, axis=1)[:, :w] & 1).astype(bool)
        for axis in (0, 1):                                       # dilate by the tolerance
            d = m.copy()
            for s in range(1, self.r + 1):
                if axis == 0:
                    d[s:] |= m[:-s]
                    d[:-s] |= m[s:]
                else:
                    d[:, s:] |= m[:, :-s]
                    d[:, :-s] |= m[:, s:]
            m = d

        def covered(q):
            q = np.asarray(q, dtype=np.float64).reshape(-1, 2)
            ix = np.floor((q[:, 0] - x0) / c).astype(np.int64)
            iy = np.floor((q[:, 1] - y0) / c).astype(np.int64)
            ok = (ix >= 0) & (ix < w) & (iy >= 0) & (iy < h)
            res = np.zeros(len(q), dtype=bool)
            res[ok] = m[iy[ok], ix[ok]]
            return res
        return covered


# face classes written to SKIN_ATTR: what the printer lays down on that exposed surface
SKIN_WALL, SKIN_TOP, SKIN_HIDDEN, SKIN_BOTTOM, SKIN_BED = 0.0, 1.0, 0.0, -1.0, -2.0


def slice_arrays(co, tris, d, layer, flaws=None, line=None, mm=1.0):
    """co: (V,3) local coordinates, tris: (T,3), d: print direction, layer: layer height and
    line: extrusion width (same units as co), flaws: optional Flaws, mm: units per millimeter.
    Returns (verts, faces, edge, skin, n_layers) in the same local space. `edge` is the
    per-vertex distance (mm) from the layer outline across the perimeter band (INNER inside);
    `skin` classifies every face like a slicer does: top skin only where nothing is printed
    above it, bottom skin only where nothing is below, the first layer lies on the bed."""
    rot = Vector(d).normalized().rotation_difference(Vector((0, 0, 1))).to_matrix()
    R = np.array(rot)
    co = co @ R.T
    co, tris = _weld(co, tris, layer * 1e-4)
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])]
    zmin, zmax = co[:, 2].min(), co[:, 2].max()
    n_layers = max(1, int(math.ceil((zmax - zmin) / layer - 1e-6)))
    min_len = layer * 0.05
    band = 2.0 * (line if line else layer * 2.1)                # two perimeter loops

    # pass 1: every layer outline (with printer flaws)
    hz = co[tris, 2]
    tz = (hz, hz.min(1), hz.max(1))
    layers = []
    for k in range(n_layers):
        z0 = zmin + k * layer
        zc = min(z0 + layer * 0.5, (z0 + zmax) * 0.5) + layer * 1.37e-5
        loops = [l for l in (_simplify(l, min_len) for l in _contours(co, tris, zc, layer * 5.0, tz)) if l]
        if flaws is not None:
            loops = [flaws.apply(l, k, (zc - zmin) / flaws.mm) for l in loops]
        layers.append(loops)
    # coverage bitmaps at ~0.05 mm (coarser for very large parts), built lazily: only layers
    # k-1, k and k+1 are ever needed at the same time
    span = max((max(p[i] for l in ls for p in l) - min(p[i] for l in ls for p in l))
               for ls in layers if ls for i in (0, 1)) if any(layers) else 1.0
    raster = _Raster(layers, max(0.05 * mm, span / 3000.0), band * 0.3)
    cache = {}

    def cover_of(i):
        if i not in cache:
            for old in [j for j in cache if j < i - 1]:
                del cache[old]
            cache[i] = raster.cover(layers[i])
        return cache[i]

    # pass 2: geometry, with every cap face classified by what lies above / below it.
    # Caps must be watertight: the perimeter band and the infill share their ring vertices
    # (the edge distance is stored per face corner), and every point added while splitting
    # infill triangles is also inserted into the neighbouring faces (no hanging vertices).
    verts, faces, fedge, skin = [], [], [], []
    for k, loops in enumerate(layers):
        if not loops:
            continue
        z0 = zmin + k * layer
        z1 = min(z0 + layer, zmax)
        above = cover_of(k + 1) if k + 1 < n_layers else _nothing
        below = cover_of(k - 1) if k > 0 else None
        top_f, bot_f, cen = [], [], []                # cap faces as [indices, corner values]
        inner = []
        for loop, (ring, b_in) in zip(loops, _rings(loops, band)):
            m = len(loop)
            # ring points collapsed onto each other (folds, thin walls) share one vertex
            uniq, rep = [], []
            for p in ring:
                if not uniq or p[0] != uniq[-1][0] or p[1] != uniq[-1][1]:
                    uniq.append(p)
                rep.append(len(uniq) - 1)
            while len(uniq) > 1 and uniq[-1][0] == uniq[0][0] and uniq[-1][1] == uniq[0][1]:
                uniq.pop()
                rep = [0 if r == len(uniq) else r for r in rep]
            n_u = len(uniq)
            b = len(verts)
            for pts, z in ((loop, z0), (loop, z1), (uniq, z0), (uniq, z1)):
                verts.extend((x, y, z) for x, y in pts)
            ob, ot, rb, rt = b, b + m, b + 2 * m, b + 2 * m + n_u
            bmm = (b_in / mm).tolist()
            for i in range(m):
                j = (i + 1) % m
                ri, rj = rep[i], rep[j]
                faces.append((ob + i, ob + j, ot + j, ot + i))                 # wall
                fedge.append((0.0, 0.0, 0.0, 0.0))
                skin.append(SKIN_WALL)
                if ri == rj:                                               # band narrows to a point
                    top_f.append([[ot + i, ot + j, rt + ri], [0.0, 0.0, bmm[i]]])
                    bot_f.append([[rb + ri, ob + j, ob + i], [bmm[i], 0.0, 0.0]])
                else:
                    top_f.append([[ot + i, ot + j, rt + rj, rt + ri], [0.0, 0.0, bmm[j], bmm[i]]])
                    bot_f.append([[rb + ri, rb + rj, ob + j, ob + i], [bmm[i], bmm[j], 0.0, 0.0]])
                cen.append(((loop[i][0] + loop[j][0] + ring[i][0] + ring[j][0]) * 0.25,
                            (loop[i][1] + loop[j][1] + ring[i][1] + ring[j][1]) * 0.25))
            if n_u >= 3:
                inner.append(([rb + q for q in range(n_u)], [rt + q for q in range(n_u)], uniq))
        # infill caps: split triangles that straddle the next layer's outline until each piece
        # is clearly exposed or clearly covered (no triangle-shaped skin patches)
        mid_t, mid_b = {}, {}

        def mid(u0, u1, l0, l1, p0, p1):
            key = (min(u0, u1), max(u0, u1))
            if key not in mid_t:
                p = ((p0[0] + p1[0]) * 0.5, (p0[1] + p1[1]) * 0.5)
                iu = len(verts)
                verts.extend(((p[0], p[1], z1), (p[0], p[1], z0)))
                mid_t[key] = (iu, p)
                mid_b[(min(l0, l1), max(l0, l1))] = (iu + 1, p)
            iu, p = mid_t[key]
            return iu, iu + 1, p

        cur = [(u, lo, P) for g in _groups(inner) for u, lo, P in _fill(g)]
        depth = 0
        while cur:
            P = np.asarray([t[2] for t in cur], dtype=np.float64)          # (n, 3, 2)
            cen_n = P.mean(1)
            lens = np.hypot(*(np.roll(P, -1, 1) - P).transpose(2, 0, 1))  # edge i: corner i -> i+1
            longest = lens.argmax(1)
            samples = np.concatenate([P, cen_n[:, None]], 1).reshape(-1, 2)
            A = above(samples).reshape(-1, 4)
            B = below(samples).reshape(-1, 4) if below is not None else A
            mixed = (A.any(1) != A.all(1)) | (B.any(1) != B.all(1))
            split = mixed & (lens.max(1) > band * 0.5) & (depth < 24)
            nxt = []
            for idx, (u, lo, Pt) in enumerate(cur):
                if not split[idx]:
                    top_f.append([list(u), [INNER] * 3])
                    bot_f.append([[lo[2], lo[1], lo[0]], [INNER] * 3])
                    cen.append(cen_n[idx])
                    continue
                # bisect the longest edge (keeps slivers from multiplying)
                i0 = int(longest[idx])
                i1, i2 = (i0 + 1) % 3, (i0 + 2) % 3
                mu, ml, mp = mid(u[i0], u[i1], lo[i0], lo[i1], Pt[i0], Pt[i1])
                nxt.append(((u[i0], mu, u[i2]), (lo[i0], ml, lo[i2]), (Pt[i0], mp, Pt[i2])))
                nxt.append(((mu, u[i1], u[i2]), (ml, lo[i1], lo[i2]), (mp, Pt[i1], Pt[i2])))
            cur = nxt
            depth += 1
        if mid_t:
            top_f = [_weld_hanging(f, mid_t) for f in top_f]
            bot_f = [_weld_hanging(f, mid_b) for f in bot_f]
        faces.extend(f[0] for f in top_f)
        fedge.extend(f[1] for f in top_f)
        skin.extend(np.where(above(cen), SKIN_HIDDEN, SKIN_TOP).tolist())
        faces.extend(f[0] for f in bot_f)
        fedge.extend(f[1] for f in bot_f)
        if below is None:
            skin.extend([SKIN_BED] * len(bot_f))
        else:
            skin.extend(np.where(below(cen), SKIN_HIDDEN, SKIN_BOTTOM).tolist())

    v = np.array(verts, dtype=np.float64).reshape(-1, 3) @ R      # back to the model frame
    corner = np.fromiter((x for vals in fedge for x in vals), dtype=np.float32)
    return v, faces, corner, np.array(skin, dtype=np.float32), n_layers


def _weld_hanging(face, mids):
    """Inserts split points that lie on this face's edges (recursively), so neighbouring faces
    share every vertex and the cap has no hairline cracks. Corner values are interpolated."""
    idx, val = face
    n = len(idx)
    if not any((min(idx[t], idx[(t + 1) % n]), max(idx[t], idx[(t + 1) % n])) in mids for t in range(n)):
        return face

    def between(a, b, va, vb):
        hit = mids.get((min(a, b), max(a, b)))
        if hit is None:
            return []
        m = hit[0]
        vm = INNER if (va >= INNER or vb >= INNER) else 0.5 * (va + vb)
        return between(a, m, va, vm) + [(m, vm)] + between(m, b, vm, vb)

    oi, ov = [], []
    for t in range(n):
        a, b, va, vb = idx[t], idx[(t + 1) % n], val[t], val[(t + 1) % n]
        oi.append(a)
        ov.append(va)
        for m, vm in between(a, b, va, vb):
            oi.append(m)
            ov.append(vm)
    return [oi, ov]


def slice_mesh(me, d, layer, layer_mm=0.2, flaws=1.0, seed=0, line_mm=0.42):
    """Builds a new bpy mesh with the sliced geometry of mesh `me` (`layer` in mesh units,
    `layer_mm` the same height in millimeters, `flaws` the imperfection amount)."""
    import bpy
    mm = layer / layer_mm
    me.calc_loop_triangles()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    v, faces, corner, skin, n = slice_arrays(co.reshape(-1, 3), tris.reshape(-1, 3), d, layer,
                                             Flaws(flaws, mm, seed), line_mm * mm, mm)
    out = bpy.data.meshes.new(me.name + "_layers")
    out.from_pydata(v.tolist(), [], faces)
    out.attributes.new(EDGE_ATTR, 'FLOAT', 'CORNER').data.foreach_set("value", corner)
    out.attributes.new(SKIN_ATTR, 'FLOAT', 'FACE').data.foreach_set("value", skin)
    out.validate(clean_customdata=False)
    out.shade_smooth()
    out.set_sharp_from_angle(angle=math.radians(35))
    for m in me.materials:
        out.materials.append(m)
    return out, n


EDGE_ATTR = "p3d_edge"
SKIN_ATTR = "p3d_skin"
