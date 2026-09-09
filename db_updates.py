import codecs
import os
import sys
from functools import lru_cache

from sqlmodel import Session, select

from config import map_path, topshot_path, pball_path
from models import Map, Tag

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking"))


def _normalize_map_rel(map_rel: str) -> str:
    normalized = os.path.normpath((map_rel or "").replace("\\", "/")).replace("\\", "/")
    if normalized in {"", "."}:
        return ""
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def _safe_join_under_root(root: str, map_rel: str, suffix: str) -> str:
    root_real = os.path.realpath(root)
    candidate = os.path.normpath(os.path.join(root, map_rel + suffix))
    candidate_real = os.path.realpath(candidate)
    if candidate_real != root_real and not candidate_real.startswith(root_real + os.sep):
        raise ValueError(f"Invalid map path: {map_rel}")
    return candidate


def resolve_map_rel(map_ref: str, session: Session | None = None) -> str:
    """
    Resolve a map reference to the canonical path stored under maps/.
    Accepts either a full relative path (e.g. beta/mymap) or a bare map name.
    """
    normalized = _normalize_map_rel(map_ref)
    if not normalized:
        return normalized

    if session is not None:
        result = session.exec(
            select(Map).where((Map.map_path == normalized) | (Map.map_name == normalized))
        ).first()
        if result:
            return result.map_path

    return normalized


def iter_image_map_rels(map_rel: str) -> list[str]:
    """
    Return candidate relative paths for map images.
    Prefer the canonical map path, but also fall back to the bare filename to
    support older images that may have been written without their subfolder.
    """
    normalized = _normalize_map_rel(map_rel)
    if not normalized:
        return []

    candidates = [normalized]
    basename = normalized.rsplit("/", 1)[-1]
    if basename != normalized:
        candidates.append(basename)
    return candidates


def add_map_to_db(map_rel: str, session: Session) -> None:
    """
    Insert a map into the database if it is not already present.
    map_rel: path relative to maps/, without .bsp extension (e.g. 'beta/mymap' or 'mymap')
    """
    existing = session.exec(select(Map).where(Map.map_path == map_rel)).first()
    if existing:
        return

    message = "Message not found"
    bsp_path = map_path + map_rel + ".bsp"
    if os.path.isfile(bsp_path):
        with codecs.open(bsp_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "message" in line.lower():
                    tmp = line.split(" ", 1)[-1][1:-2]
                    message = tmp.replace("\\n", " ")
                    break

    map_entry = Map(
        map_name=map_rel.split("/")[-1],
        map_path=map_rel,
        message=message,
    )
    session.add(map_entry)
    session.commit()


def add_tag(map_name: str, tag: str, session: Session) -> str:
    """
    Add a tag to a map. Returns a status message.
    """
    map_entry = session.exec(select(Map).where(Map.map_name == map_name)).first()
    if not map_entry:
        return f"Map `{map_name}` not found in the database."

    existing = session.exec(
        select(Tag).where(Tag.map_id == map_entry.map_id, Tag.tag_name == tag)
    ).first()
    if existing:
        return f"Tag `{tag}` already exists on `{map_name}`."

    session.add(Tag(map_id=map_entry.map_id, tag_name=tag))
    session.commit()
    return f"✅ Tag `{tag}` added to `{map_name}`."


def remove_tag(map_name: str, tag: str, session: Session) -> str:
    """
    Remove a tag from a map. Returns a status message.
    """
    map_entry = session.exec(select(Map).where(Map.map_name == map_name)).first()
    if not map_entry:
        return f"Map `{map_name}` not found in the database."

    existing = session.exec(
        select(Tag).where(Tag.map_id == map_entry.map_id, Tag.tag_name == tag)
    ).first()
    if not existing:
        return f"Tag `{tag}` does not exist on `{map_name}`."

    session.delete(existing)
    session.commit()
    return f"✅ Tag `{tag}` removed from `{map_name}`."


# ---------------------------------------------------------------------------
# Topshot rendering — top-down overview with BSP culling
# ---------------------------------------------------------------------------

# Surface flags (mirror of api.py constants)
_SURF_SKY = 0x0004
_SURF_TRANS33 = 0x0010
_SURF_TRANS66 = 0x0020
_SURF_NODRAW = 0x0080
_CULLED_TEXTURE_NAMES = {"sky", "hint", "clip", "skip"}
_TS_TEXTURE_EXTS = ("png", "jpg", "jpeg", "webp", "tga", "pcx")
_TS_WAL_HEADER_SIZE = 100
_TS_WAL_MAX_DIMENSION = 4096


def _ts_bsp_lump(data: bytes, idx: int) -> tuple[int, int]:
    off = 8 + idx * 8
    if off + 8 > len(data):
        return (0, 0)
    lump_off = int.from_bytes(data[off:off + 4], "little", signed=False)
    lump_len = int.from_bytes(data[off + 4:off + 8], "little", signed=False)
    if lump_off + lump_len > len(data):
        return (0, 0)
    return (lump_off, lump_len)


def _ts_is_culled(texture_name: str, flags: int) -> bool:
    if flags & (_SURF_SKY | _SURF_NODRAW):
        return True
    lower = texture_name.lower().replace("\\", "/")
    if lower.startswith("sky") or "/sky" in lower:
        return True
    return any(p in _CULLED_TEXTURE_NAMES for p in lower.split("/") if p)


def _ts_opacity(flags: int) -> float:
    if flags & _SURF_TRANS33:
        return 0.33
    if flags & _SURF_TRANS66:
        return 0.66
    return 1.0


def _ts_resolve_face_indices(
    face_edges: list, edges: list, n_verts: int, first_edge: int, num_edges: int
) -> list | None:
    if first_edge < 0 or first_edge + num_edges > len(face_edges):
        return None
    idxs = []
    for fe in face_edges[first_edge:first_edge + num_edges]:
        ei = fe if fe >= 0 else -fe
        if ei < 0 or ei >= len(edges):
            return None
        vi = edges[ei][0] if fe >= 0 else edges[ei][1]
        if vi < 0 or vi >= n_verts:
            return None
        idxs.append(vi)
    return idxs if len(idxs) >= 3 else None


def _ts_parse_bsp(bsp_path: str) -> dict:
    import struct
    with open(bsp_path, "rb") as f:
        data = f.read()
    if data[:4] != b"IBSP":
        raise ValueError("Unsupported BSP format")
    vert_off, vert_len = _ts_bsp_lump(data, 2)
    edge_off, edge_len = _ts_bsp_lump(data, 11)
    face_edge_off, face_edge_len = _ts_bsp_lump(data, 12)
    face_off, face_len = _ts_bsp_lump(data, 6)
    tex_off, tex_len = _ts_bsp_lump(data, 5)
    if not all((vert_len, edge_len, face_edge_len, face_len, tex_len)):
        raise ValueError("Missing BSP geometry lumps")
    if vert_len % 12 or edge_len % 4 or face_edge_len % 4 or face_len % 20 or tex_len % 76:
        raise ValueError("Corrupt BSP lump sizes")
    vertices = [struct.unpack_from("<fff", data, vert_off + i * 12) for i in range(vert_len // 12)]
    edges = [struct.unpack_from("<HH", data, edge_off + i * 4) for i in range(edge_len // 4)]
    face_edges = [struct.unpack_from("<i", data, face_edge_off + i * 4)[0] for i in range(face_edge_len // 4)]
    tex_infos = []
    for i in range(tex_len // 76):
        base = tex_off + i * 76
        vals = struct.unpack_from("<8fii32si", data, base)
        tex_infos.append({
            "s": vals[0:4], "t": vals[4:8],
            "flags": vals[8],
            "name": vals[10].decode("ascii", "ignore").rstrip("\x00") or "__default__",
        })
    faces = []
    for i in range(face_len // 20):
        base = face_off + i * 20
        _, _, first_edge, num_edges, texinfo_idx, _, _ = struct.unpack_from("<HhiHh4si", data, base)
        faces.append((first_edge, num_edges, texinfo_idx))
    return {"vertices": vertices, "edges": edges, "face_edges": face_edges,
            "faces": faces, "tex_infos": tex_infos}


@lru_cache(maxsize=1)
def _ts_load_q2_palette() -> list[int]:
    from PIL import Image

    pball_root = os.path.realpath(pball_path.rstrip("/"))
    colormap_path = os.path.realpath(os.path.join(pball_root, "pics", "colormap.pcx"))
    if not colormap_path.startswith(pball_root + os.sep) or not os.path.isfile(colormap_path):
        raise FileNotFoundError("Missing Quake2 colormap.pcx palette file")

    with Image.open(colormap_path) as img:
        palette = img.getpalette()
    if not palette or len(palette) < 768:
        raise ValueError("Invalid Quake2 palette in colormap.pcx")
    return palette[:768]


def _ts_decode_wal_to_rgba(wal_path: str) -> "Image.Image":
    import struct
    from PIL import Image

    with open(wal_path, "rb") as f:
        wal_data = f.read()
    if len(wal_data) < _TS_WAL_HEADER_SIZE:
        raise ValueError("Invalid WAL texture header")

    _, width, height, off0, _, _, _, _, _, _, _ = struct.unpack_from("<32s6I32s3i", wal_data, 0)
    if width <= 0 or height <= 0 or width > _TS_WAL_MAX_DIMENSION or height > _TS_WAL_MAX_DIMENSION:
        raise ValueError("Invalid WAL texture dimensions")

    pixel_count = width * height
    if off0 <= 0 or off0 + pixel_count > len(wal_data):
        raise ValueError("Invalid WAL texture pixel data")

    indices = wal_data[off0:off0 + pixel_count]
    indexed = Image.frombytes("P", (width, height), indices)
    indexed.putpalette(_ts_load_q2_palette())

    rgba = indexed.convert("RGBA")
    if b"\xff" in indices:
        alpha = indexed.point(lambda p: 0 if p == 255 else 255, mode="L")
        rgba.putalpha(alpha)
    return rgba


def _ts_average_rgba_color(img: "Image.Image") -> tuple[int, int, int] | None:
    from PIL import ImageStat

    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getbbox() is None:
        return None
    mask = alpha.point(lambda a: 255 if a else 0, mode="L")
    stats = ImageStat.Stat(rgba, mask=mask)
    count = stats.count[0] if stats.count else 0
    if not count:
        return None
    return tuple(int(round(channel)) for channel in stats.mean[:3])


@lru_cache(maxsize=1024)
def _ts_average_texture_color(texture_name: str) -> tuple[int, int, int] | None:
    from PIL import Image

    texture_rel = texture_name.strip("/").replace("\\", "/")
    if not texture_rel:
        return None

    pball_root = os.path.realpath(pball_path.rstrip("/"))
    textures_root = os.path.realpath(os.path.join(pball_root, "textures"))
    tex_dir, tex_base = os.path.split(texture_rel)
    candidates = []
    if tex_dir:
        for ext in _TS_TEXTURE_EXTS:
            candidates.append(os.path.join(textures_root, tex_dir, "hr4", f"{tex_base}.{ext}"))
        candidates.append(os.path.join(textures_root, tex_dir, "hr4", f"{tex_base}.wal"))
    for ext in _TS_TEXTURE_EXTS:
        candidates.append(os.path.join(textures_root, f"{texture_rel}.{ext}"))
    candidates.append(os.path.join(textures_root, f"{texture_rel}.wal"))

    for candidate in candidates:
        texture_path = os.path.realpath(candidate)
        if not texture_path.startswith(textures_root + os.sep) or not os.path.isfile(texture_path):
            continue
        if texture_path.lower().endswith(".wal"):
            return _ts_average_rgba_color(_ts_decode_wal_to_rgba(texture_path))
        with Image.open(texture_path) as img:
            return _ts_average_rgba_color(img)
    return None


def _ts_apply_shading(
    texture_color: tuple[int, int, int] | None,
    z: float,
    min_z: float,
    z_range: float,
) -> tuple[int, int, int]:
    t = (z - min_z) / z_range
    t = max(0.0, min(1.0, t))
    shade = int(60 + 170 * t)
    if texture_color is None:
        return (shade, shade, shade)

    shade_offset = shade - 145
    return tuple(max(0, min(255, channel + shade_offset)) for channel in texture_color)



def _render_topshot_topdown(bsp_path: str, max_resolution: int = 1024) -> "Image.Image":
    """
    Render a top-down orthographic overview of the BSP map.

    The camera looks straight down the BSP Z axis so the XY plane of the map
    is projected onto the image.  Surfaces are culled using the same rules as
    the 3D viewer (sky, nodraw, hint, clip, skip).  Back-facing opaque surfaces
    are culled via the 2-D signed area of their projection (FrontSide); transparent
    surfaces are rendered from both sides (DoubleSide).  Painter's algorithm
    (back-to-front by Z elevation) handles depth ordering.  Polygon color is
    tinted with the average resolved texture color and remains slope-aware: for
    non-degenerate XY projections, height is evaluated per pixel from the polygon
    plane to brighten or darken the texture tint.  Degenerate projections fall
    back to average-Z shading.  Returns a PIL RGBA image.
    """
    import math
    from PIL import Image, ImageDraw

    parsed = _ts_parse_bsp(bsp_path)
    vertices = parsed["vertices"]
    edges = parsed["edges"]
    face_edges = parsed["face_edges"]
    tex_infos = parsed["tex_infos"]
    faces = parsed["faces"]

    # Collect all visible polygons with their screen-space data.
    # Top-down projection: screen_x = BSP_x, screen_y = -BSP_y, depth = BSP_z
    # (negating Y so the image Y axis increases downward as in screen space).
    polys: list[tuple] = []  # (avg_z, screen_pts, screen_pts_z, opacity, texture_color)

    for first_edge, num_edges, texinfo_idx in faces:
        if num_edges < 3 or texinfo_idx < 0 or texinfo_idx >= len(tex_infos):
            continue
        tex_info = tex_infos[texinfo_idx]
        texture_name = tex_info["name"] or "__default__"
        if _ts_is_culled(texture_name, tex_info["flags"]):
            continue
        face_indices = _ts_resolve_face_indices(face_edges, edges, len(vertices), first_edge, num_edges)
        if face_indices is None:
            continue

        opacity = _ts_opacity(tex_info["flags"])

        # Project vertices to screen space and record depth.
        sx_list = []
        sy_list = []
        z_list = []
        for vi in face_indices:
            bx, by, bz = vertices[vi]
            sx_list.append(bx)
            sy_list.append(-by)
            z_list.append(bz)

        # Back-face culling via 2-D signed area (Shoelace formula).
        # The projection is (BSP_x, -BSP_y), so a positive signed area means
        # the polygon winds CCW in screen space, i.e. it faces the camera
        # looking straight down.  A negative (or zero) area means back-facing.
        # Opaque surfaces: cull back-faces (FrontSide), matching the 3D viewer.
        # Transparent surfaces: render from both sides (DoubleSide).
        n = len(sx_list)
        signed_area = 0.0
        for i in range(n):
            j = (i + 1) % n
            signed_area += sx_list[i] * sy_list[j] - sx_list[j] * sy_list[i]

        if signed_area <= 0:
            if opacity >= 1.0:
                continue  # back-facing opaque surface — cull it

        avg_z = sum(z_list) / len(z_list)
        screen_pts = list(zip(sx_list, sy_list))
        screen_pts_z = list(zip(sx_list, sy_list, z_list))
        texture_color = _ts_average_texture_color(texture_name)
        polys.append((avg_z, screen_pts, screen_pts_z, opacity, texture_color))
    if not polys:
        return Image.new("RGBA", (max_resolution, max_resolution), (255, 255, 255, 255))

    # Compute world bounding box.
    all_sx = [pt[0] for _, pts, _, _, _ in polys for pt in pts]
    all_sy = [pt[1] for _, pts, _, _, _ in polys for pt in pts]
    all_z = [z for _, _, pts_z, _, _ in polys for _, _, z in pts_z]

    min_x, max_x = min(all_sx), max(all_sx)
    min_y, max_y = min(all_sy), max(all_sy)
    min_z, max_z = min(all_z),  max(all_z)

    span = max(max_x - min_x, max_y - min_y)
    if span == 0:
        span = 1.0
    scale = max_resolution / span
    z_range = max_z - min_z if max_z != min_z else 1.0

    img_w = max(1, int((max_x - min_x) * scale + 0.5))
    img_h = max(1, int((max_y - min_y) * scale + 0.5))

    def to_px(sx: float, sy: float) -> tuple[float, float]:
        return (sx - min_x) * scale, (sy - min_y) * scale

    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))
    img_px = img.load()
    z_buffer = [float("-inf")] * (img_w * img_h)

    def _fit_plane_z(points: list[tuple[float, float, float]]) -> tuple[float, float, float] | None:
        # Solve z = a*x + b*y + c from the most numerically stable non-collinear triplet in projected XY.
        n = len(points)
        best: tuple[float, float, float] | None = None
        best_det_abs = 0.0
        for i in range(n - 2):
            x1, y1, z1 = points[i]
            for j in range(i + 1, n - 1):
                x2, y2, z2 = points[j]
                for k in range(j + 1, n):
                    x3, y3, z3 = points[k]
                    det = x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)
                    if abs(det) < 1e-9:
                        continue
                    a = (z1 * (y2 - y3) + z2 * (y3 - y1) + z3 * (y1 - y2)) / det
                    b = (z1 * (x3 - x2) + z2 * (x1 - x3) + z3 * (x2 - x1)) / det
                    c = (
                        z1 * (x2 * y3 - x3 * y2)
                        + z2 * (x3 * y1 - x1 * y3)
                        + z3 * (x1 * y2 - x2 * y1)
                    ) / det
                    det_abs = abs(det)
                    if det_abs > best_det_abs:
                        best_det_abs = det_abs
                        best = (a, b, c)
        if best is None:
            return None

        # Guard against noisy/non-planar inputs that can create extreme artifacts.
        a, b, c = best
        zs = [z for _, _, z in points]
        z_span = max(zs) - min(zs) if zs else 0.0
        max_residual = max(abs((a * x + b * y + c) - z) for x, y, z in points)
        if max_residual > max(0.1, z_span * 1e-3):
            return None
        return best

    opaque_polys = [p for p in polys if p[3] >= 1.0]
    transparent_polys = [p for p in polys if p[3] < 1.0]

    # Opaque pass: per-pixel depth test to avoid painter-order artifacts on overlaps.
    for avg_z, screen_pts, screen_pts_z, _opacity, texture_color in opaque_polys:
        poly_px = [to_px(sx, sy) for sx, sy in screen_pts]
        if len(poly_px) < 3:
            continue

        plane = _fit_plane_z(screen_pts_z)
        min_px = max(0, math.floor(min(x for x, _ in poly_px)))
        max_px = min(img_w - 1, math.ceil(max(x for x, _ in poly_px)))
        min_py = max(0, math.floor(min(y for _, y in poly_px)))
        max_py = min(img_h - 1, math.ceil(max(y for _, y in poly_px)))
        if min_px > max_px or min_py > max_py:
            continue

        local_w = max_px - min_px + 1
        local_h = max_py - min_py + 1
        local_poly = [(x - min_px, y - min_py) for x, y in poly_px]

        mask = Image.new("L", (local_w, local_h), 0)
        ImageDraw.Draw(mask).polygon(local_poly, fill=255)
        mask_px = mask.load()

        a = b = c = 0.0
        if plane is not None:
            a, b, c = plane
        for py in range(local_h):
            sy = (min_py + py + 0.5) / scale + min_y
            for px in range(local_w):
                if mask_px[px, py] == 0:
                    continue
                sx = (min_px + px + 0.5) / scale + min_x
                z = (a * sx + b * sy + c) if plane is not None else avg_z
                gx = min_px + px
                gy = min_py + py
                idx = gy * img_w + gx
                if z >= z_buffer[idx]:
                    z_buffer[idx] = z
                    img_px[gx, gy] = (*_ts_apply_shading(texture_color, z, min_z, z_range), 255)

    # Transparent pass: keep painter ordering, but skip fragments behind opaque depth.
    transparent_polys.sort(key=lambda p: p[0])
    for avg_z, screen_pts, screen_pts_z, opacity, texture_color in transparent_polys:
        alpha = int(255 * opacity)
        poly_px = [to_px(sx, sy) for sx, sy in screen_pts]
        if len(poly_px) < 3:
            continue

        plane = _fit_plane_z(screen_pts_z)
        min_px = max(0, math.floor(min(x for x, _ in poly_px)))
        max_px = min(img_w - 1, math.ceil(max(x for x, _ in poly_px)))
        min_py = max(0, math.floor(min(y for _, y in poly_px)))
        max_py = min(img_h - 1, math.ceil(max(y for _, y in poly_px)))
        if min_px > max_px or min_py > max_py:
            continue

        local_w = max_px - min_px + 1
        local_h = max_py - min_py + 1
        local_poly = [(x - min_px, y - min_py) for x, y in poly_px]

        mask = Image.new("L", (local_w, local_h), 0)
        ImageDraw.Draw(mask).polygon(local_poly, fill=255)
        mask_px = mask.load()

        tile = Image.new("RGBA", (local_w, local_h), (0, 0, 0, 0))
        tile_px = tile.load()
        a = b = c = 0.0
        if plane is not None:
            a, b, c = plane
        for py in range(local_h):
            sy = (min_py + py + 0.5) / scale + min_y
            for px in range(local_w):
                if mask_px[px, py] == 0:
                    continue
                sx = (min_px + px + 0.5) / scale + min_x
                z = (a * sx + b * sy + c) if plane is not None else avg_z
                gx = min_px + px
                gy = min_py + py
                if z < z_buffer[gy * img_w + gx]:
                    continue
                tile_px[px, py] = (*_ts_apply_shading(texture_color, z, min_z, z_range), alpha)
        img.alpha_composite(tile, dest=(min_px, min_py))

    return img


def generate_topshot(map_rel: str) -> None:
    """
    Generate a top-down overview image for the given map and save it to
    topshot_path. Uses BSP culling (sky, nodraw, hint, clip, skip), texture-aware
    height shading, and per-pixel depth testing for opaque surfaces.
    """
    normalized_map_rel = _normalize_map_rel(map_rel)
    bsp_path = _safe_join_under_root(map_path, normalized_map_rel, ".bsp")
    if not os.path.isfile(bsp_path):
        raise FileNotFoundError(f"BSP file not found: {normalized_map_rel}")

    out_path = _safe_join_under_root(topshot_path, normalized_map_rel, ".jpg")
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    img = _render_topshot_topdown(bsp_path, max_resolution=1024)
    img.convert("RGB").save(out_path, "JPEG", quality=75, optimize=True)


def request_topshot_via_api(map_rel: str) -> None:
    """
    Ask the API to generate a topshot for the given map by calling the
    /api/export-bsp endpoint.  This delegates image generation to the API
    process, which has the required dependencies available.
    """
    import urllib.request
    import urllib.parse
    from config import base_url

    url = base_url + "/api/export-bsp?" + urllib.parse.urlencode({"map_name": map_rel})
    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=30):
            pass
    except Exception as e:
        print(f"request_topshot_via_api: failed for {map_rel}: {e}")
        raise
