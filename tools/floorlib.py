"""Image helpers shared by the floor photo tools (run inside Blender: bpy + numpy)."""
import json
import os

import bpy
import numpy as np

LUMW = np.array([0.2126, 0.7152, 0.0722], np.float32)


def load(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1, :, :3].copy()          # rows top to bottom, sRGB values


def save(arr, path, fmt, quality=92):
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        arr = np.repeat(arr[:, :, None], 3, 2)
    rgba = np.ones((h, w, 4), np.float32)
    rgba[:, :, :3] = np.clip(arr, 0, 1)
    img = bpy.data.images.new(os.path.basename(path), w, h)
    img.colorspace_settings.name = 'Non-Color'                # write the values as they are
    img.pixels.foreach_set(rgba[::-1].ravel())
    img.filepath_raw = path
    img.file_format = fmt
    sc = bpy.context.scene
    sc.render.image_settings.quality = quality
    img.save(filepath=path, quality=quality)
    bpy.data.images.remove(img)


def box1(a, r, axis, wrap=False):
    pad = [(r + 1, r) if i == axis else (0, 0) for i in range(a.ndim)]
    c = np.cumsum(np.pad(a, pad, mode='wrap' if wrap else 'edge'), axis=axis)
    n = a.shape[axis]
    return (np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
            - np.take(c, np.arange(0, n), axis=axis)) / (2 * r + 1)


def blur(a, r, wrap=False):
    return box1(box1(a, r, 0, wrap), r, 1, wrap)


def sample(im, xs, ys):
    """Bilinear lookup of im at float pixel positions."""
    h, w = im.shape[:2]
    xs, ys = np.clip(xs, 0, w - 1.001), np.clip(ys, 0, h - 1.001)
    x0, y0 = xs.astype(np.int64), ys.astype(np.int64)
    fx, fy = (xs - x0)[..., None], (ys - y0)[..., None]
    a, b = im[y0, x0], im[y0, x0 + 1]
    c, d = im[y0 + 1, x0], im[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def flatten(rect):
    """Removes light falloff and color cast: every channel divided by a smooth quadratic fit
    of itself (in place)."""
    H, W = rect.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    xn, yn = xx / W - 0.5, yy / H - 0.5
    A = np.stack([np.ones_like(xn), xn, yn, xn * yn, xn ** 2, yn ** 2], -1).reshape(-1, 6)
    for c in range(3):
        ch = rect[:, :, c]
        coef, *_ = np.linalg.lstsq(A[::37], ch.ravel()[::37], rcond=None)
        rect[:, :, c] = ch * (ch.mean() / (A @ coef).reshape(H, W))
    return rect


def write_maps(atlas, out, name, info):
    """Color, normal (OpenGL) and roughness maps of a board atlas, plus <name>.json. The
    shader draws the joints itself, so the maps only carry the wood: embossed grain + cracks."""
    os.makedirs(out, exist_ok=True)
    col = np.clip(atlas, 0, 1)
    L = col @ LUMW
    detail = L - blur(L, 3)
    crack = np.clip((blur(L, 25) - L - 0.04) * 6, 0, 1)
    height = np.clip(0.6 + np.clip(detail * 2.5, -0.25, 0.25) - crack * 0.3, 0, 1)
    gy, gx = np.gradient(height)
    k = 6.0
    nx, ny, nz = -gx * k, gy * k, np.ones_like(gx)           # green = up (rows go down)
    ln = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
    nrm = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
    rough = np.clip(0.42 + np.clip(-detail * 1.5, -0.08, 0.12) + crack * 0.25, 0, 1)
    save(col, os.path.join(out, name + "_COL.jpg"), 'JPEG', 93)
    save(nrm, os.path.join(out, name + "_NRM.jpg"), 'JPEG', 95)
    save(rough, os.path.join(out, name + "_ROUGHNESS.jpg"), 'JPEG', 90)
    json.dump(info, open(os.path.join(out, name + ".json"), "w"), indent=2)
    print("ATLAS", info)
