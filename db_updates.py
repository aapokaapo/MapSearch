import codecs
import multiprocessing as mp
import os
import sys

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
# Topshot rendering — same BSP culling + UV logic as the 3D viewer (api.py)
# ---------------------------------------------------------------------------

# Surface flags (mirror of api.py constants)
_SURF_SKY = 0x0004
_SURF_TRANS33 = 0x0010
_SURF_TRANS66 = 0x0020
_SURF_NODRAW = 0x0080
_CULLED_TEXTURE_NAMES = {"sky", "hint", "clip", "skip"}
_BROWSER_TEXTURE_EXTS = ("png", "jpg", "jpeg", "webp")
# UV-scale overrides: multiplies BSP texel coords to get pixel coords in the
# chosen image (needed when the on-disk image differs in size from what the BSP
# UV values assume).  Mirror of api.py's _TEXTURE_UV_SCALE_OVERRIDES /
# _TEXTURE_HR4_UV_SCALE_OVERRIDES.
_TS_UV_SCALE_OVERRIDES: dict[str, float] = {
    "chainlink1": 8,
}
_TS_HR4_UV_SCALE_OVERRIDES: dict[str, float] = {
    "chainlink1": 16,
}


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


def _ts_resolve_texture_disk(texture_name: str, pball_root: str) -> tuple[str | None, float]:
    """
    Return (disk_path, uv_scale) for the best available texture image.

    uv_scale is the multiplier applied to BSP texel UV coordinates to convert
    them to pixel coordinates in the returned image (mirrors api.py logic).
    """
    tex_rel = texture_name.strip("/").replace("\\", "/")
    if not tex_rel:
        return None, 1.0
    tex_dir, tex_base = os.path.split(tex_rel)
    candidates = []
    for ext in _BROWSER_TEXTURE_EXTS:
        if tex_dir:
            hr4_scale = _TS_HR4_UV_SCALE_OVERRIDES.get(tex_base.lower(), 4)
            candidates.append((os.path.join("textures", tex_dir, "hr4", f"{tex_base}.{ext}"), hr4_scale))
        default_scale = _TS_UV_SCALE_OVERRIDES.get(tex_base.lower(), 1)
        candidates.append((os.path.join("textures", f"{tex_rel}.{ext}"), default_scale))
    for rel_disk, uv_scale in candidates:
        disk_path = os.path.realpath(os.path.join(pball_root, rel_disk))
        if disk_path.startswith(pball_root + os.sep) and os.path.isfile(disk_path):
            return disk_path, float(uv_scale)
    return None, 1.0


def _ts_tri_affine(
    src0: tuple, src1: tuple, src2: tuple,
    dst0: tuple, dst1: tuple, dst2: tuple,
) -> tuple | None:
    """
    Return PIL AFFINE coefficients (a,b,c,d,e,f) such that:
        src_x = a*dst_x + b*dst_y + c
        src_y = d*dst_x + e*dst_y + f
    Returns None if the destination triangle is degenerate.
    """
    dx0, dy0 = dst0; sx0, sy0 = src0
    dx1, dy1 = dst1; sx1, sy1 = src1
    dx2, dy2 = dst2; sx2, sy2 = src2
    det = dx0 * (dy1 - dy2) - dy0 * (dx1 - dx2) + (dx1 * dy2 - dx2 * dy1)
    if abs(det) < 1e-10:
        return None
    inv = 1.0 / det
    a00 = (dy1 - dy2) * inv;  a01 = (dy2 - dy0) * inv;  a02 = (dy0 - dy1) * inv
    a10 = (dx2 - dx1) * inv;  a11 = (dx0 - dx2) * inv;  a12 = (dx1 - dx0) * inv
    a20 = (dx1 * dy2 - dx2 * dy1) * inv
    a21 = (dx2 * dy0 - dx0 * dy2) * inv
    a22 = (dx0 * dy1 - dx1 * dy0) * inv
    a = sx0 * a00 + sx1 * a01 + sx2 * a02
    b = sx0 * a10 + sx1 * a11 + sx2 * a12
    c = sx0 * a20 + sx1 * a21 + sx2 * a22
    d = sy0 * a00 + sy1 * a01 + sy2 * a02
    e = sy0 * a10 + sy1 * a11 + sy2 * a12
    f = sy0 * a20 + sy1 * a21 + sy2 * a22
    return (a, b, c, d, e, f)


def _render_topshot_textured(bsp_path: str, pball_root: str, max_resolution: int = 2048) -> "Image.Image":
    """
    Render a 45° yaw + 45° pitch isometric view of the BSP with textures.

    Uses the same surface culling, UV computation, and coordinate mapping as the
    3D viewer (api.py).  Textures are loaded from disk, tiled as needed, and
    painted back-to-front using a painter's algorithm with affine texture mapping
    and diffuse lighting.  Returns a PIL RGBA image with a white background.
    """
    import math
    from PIL import Image, ImageDraw, ImageEnhance

    AMBIENT = 0.35
    DIFFUSE = 0.65
    _inv_sqrt3 = 1.0 / math.sqrt(3.0)
    LIGHT_DIR = (-_inv_sqrt3, -_inv_sqrt3, _inv_sqrt3)

    parsed = _ts_parse_bsp(bsp_path)
    vertices = parsed["vertices"]
    edges = parsed["edges"]
    face_edges = parsed["face_edges"]
    tex_infos = parsed["tex_infos"]
    faces = parsed["faces"]

    pball_root = os.path.realpath(pball_root.rstrip("/"))

    # Texture cache: name → (PIL Image | None, uv_scale)
    tex_cache: dict[str, tuple] = {}

    def _get_texture(name: str) -> tuple:
        if name in tex_cache:
            return tex_cache[name]
        disk_path, uv_scale = _ts_resolve_texture_disk(name, pball_root)
        result: tuple
        if disk_path:
            try:
                result = (Image.open(disk_path).convert("RGBA"), uv_scale)
            except Exception:
                result = (None, 1.0)
        else:
            result = (None, 1.0)
        tex_cache[name] = result
        return result

    cos45 = math.cos(math.radians(45))
    sin45 = math.sin(math.radians(45))

    def _project(bx: float, by: float, bz: float) -> tuple[float, float, float]:
        # Coordinate swap identical to api.py viewer: (BSP_x, BSP_z, -BSP_y)
        vx, vy, vz = bx, bz, -by
        # Yaw 45° around viewer-Y axis (rotate in X-Z plane)
        vx, vz = cos45 * vx + sin45 * vz, -sin45 * vx + cos45 * vz
        # Pitch 45° around viewer-X axis (rotate in Y-Z plane)
        vy, vz = cos45 * vy - sin45 * vz, sin45 * vy + cos45 * vz
        return vx, vy, vz  # screen_x, screen_y, depth

    # Collect all visible triangles
    triangles: list[tuple] = []

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
        s = tex_info["s"]
        tv = tex_info["t"]

        screen_verts = []
        uv_verts = []
        for vi in face_indices:
            bx, by, bz = vertices[vi]
            sx, sy, depth = _project(bx, by, bz)
            screen_verts.append((sx, sy, depth))
            # BSP texel-space UVs (same formula as api.py; v not negated here
            # because PIL pixel space and BSP V axis both increase downward)
            u = bx * s[0] + by * s[1] + bz * s[2] + s[3]
            v = bx * tv[0] + by * tv[1] + bz * tv[2] + tv[3]
            uv_verts.append((u, v))

        # Compute projected face normal via cross product for back-face culling
        # and diffuse lighting.
        p0 = screen_verts[0]; p1 = screen_verts[1]; p2 = screen_verts[2]
        ax = p1[0] - p0[0]; ay = p1[1] - p0[1]; az = p1[2] - p0[2]
        bx2 = p2[0] - p0[0]; by2 = p2[1] - p0[1]; bz2 = p2[2] - p0[2]
        nx = ay * bz2 - az * by2
        ny = az * bx2 - ax * bz2
        nz = ax * by2 - ay * bx2
        # Camera faces +Z after the isometric rotation; cull back-facing polygons.
        if nz < 0:
            continue
        mag = math.sqrt(nx * nx + ny * ny + nz * nz)
        if mag > 0:
            nx /= mag; ny /= mag; nz /= mag

        # Fan-triangulate the face
        v0_s = screen_verts[0]; u0 = uv_verts[0]
        for t in range(1, len(face_indices) - 1):
            v1_s = screen_verts[t]; v2_s = screen_verts[t + 1]
            u1 = uv_verts[t]; u2 = uv_verts[t + 1]
            depth_avg = (v0_s[2] + v1_s[2] + v2_s[2]) / 3.0
            triangles.append((
                depth_avg,
                ((v0_s[0], v0_s[1]), (v1_s[0], v1_s[1]), (v2_s[0], v2_s[1])),
                texture_name,
                (u0, u1, u2),
                opacity,
                (nx, ny, nz),
            ))

    if not triangles:
        return Image.new("RGBA", (max_resolution, max_resolution), (255, 255, 255, 255))

    all_pts = [(p[0], p[1]) for _, pts, *_ in triangles for p in pts]
    min_x = min(p[0] for p in all_pts)
    min_y = min(p[1] for p in all_pts)
    max_x = max(p[0] for p in all_pts)
    max_y = max(p[1] for p in all_pts)

    span = max(max_x - min_x, max_y - min_y)
    if span == 0:
        span = 1.0
    scale = max_resolution / span

    img_w = max(1, int((max_x - min_x) * scale + 0.5))
    img_h = max(1, int((max_y - min_y) * scale + 0.5))

    def to_px(sx: float, sy: float) -> tuple[float, float]:
        # Flip Y so world-up maps to image-up.
        return (sx - min_x) * scale, (max_y - sy) * scale

    # Painter's algorithm: ascending depth = back-to-front
    # (larger depth = closer to camera after isometric rotation).
    triangles.sort(key=lambda t: t[0])

    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))

    for depth, screen_pts, tex_name, uv_pts, opacity, normal in triangles:
        dot_light = max(0.0, sum(normal[i] * LIGHT_DIR[i] for i in range(3)))
        brightness = AMBIENT + DIFFUSE * dot_light

        px0, py0 = to_px(*screen_pts[0])
        px1, py1 = to_px(*screen_pts[1])
        px2, py2 = to_px(*screen_pts[2])
        poly_px = [(px0, py0), (px1, py1), (px2, py2)]

        tex_img, uv_scale = _get_texture(tex_name)
        if tex_img is not None:
            tw, th = tex_img.size

            # Scale BSP texel UVs to pixel coords in the chosen image.
            u0_px, v0_px = uv_pts[0][0] * uv_scale, uv_pts[0][1] * uv_scale
            u1_px, v1_px = uv_pts[1][0] * uv_scale, uv_pts[1][1] * uv_scale
            u2_px, v2_px = uv_pts[2][0] * uv_scale, uv_pts[2][1] * uv_scale

            # Shift UVs so the minimum falls within [0, tile_size).
            off_u = math.floor(min(u0_px, u1_px, u2_px) / tw) * tw
            off_v = math.floor(min(v0_px, v1_px, v2_px) / th) * th
            su0, sv0 = u0_px - off_u, v0_px - off_v
            su1, sv1 = u1_px - off_u, v1_px - off_v
            su2, sv2 = u2_px - off_u, v2_px - off_v

            # Tile the texture enough to cover the full UV range of this triangle.
            tiles_u = min(8, int(math.ceil(max(su0, su1, su2) / tw)) + 1)
            tiles_v = min(8, int(math.ceil(max(sv0, sv1, sv2) / th)) + 1)
            src_w, src_h = tiles_u * tw, tiles_v * th
            src_img = Image.new("RGBA", (src_w, src_h))
            for tu in range(tiles_u):
                for tv2 in range(tiles_v):
                    src_img.paste(tex_img, (tu * tw, tv2 * th))

            src_img = ImageEnhance.Brightness(src_img).enhance(brightness)
            if opacity < 1.0:
                r, g, b, a = src_img.split()
                src_img = Image.merge("RGBA", (r, g, b, a.point(lambda x: int(x * opacity))))

            coeffs = _ts_tri_affine(
                (su0, sv0), (su1, sv1), (su2, sv2),
                (px0, py0), (px1, py1), (px2, py2),
            )
            if coeffs is not None:
                tri_mask = Image.new("L", (img_w, img_h), 0)
                ImageDraw.Draw(tri_mask).polygon(poly_px, fill=255)
                tex_canvas = src_img.transform(
                    (img_w, img_h), Image.AFFINE, coeffs, resample=Image.BILINEAR,
                )
                img.paste(tex_canvas, (0, 0), tri_mask)
                continue

        # Fallback: flat grey lit by diffuse lighting.
        fb = min(255, int(180 * brightness))
        fallback_color = (fb, fb, fb, int(255 * opacity))
        tri_mask = Image.new("L", (img_w, img_h), 0)
        ImageDraw.Draw(tri_mask).polygon(poly_px, fill=255)
        img.paste(Image.new("RGBA", (img_w, img_h), fallback_color), (0, 0), tri_mask)

    return img


def generate_topshot(map_rel: str) -> None:
    """
    Generate a 45° yaw + 45° pitch isometric image for the given map and save
    it to topshot_path.  Uses the same BSP culling and UV logic as the 3D viewer.
    """
    normalized_map_rel = _normalize_map_rel(map_rel)
    bsp_path = _safe_join_under_root(map_path, normalized_map_rel, ".bsp")
    if not os.path.isfile(bsp_path):
        raise FileNotFoundError(f"BSP file not found: {normalized_map_rel}")

    out_path = _safe_join_under_root(topshot_path, normalized_map_rel, ".jpg")
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    img = _render_topshot_textured(bsp_path, pball_path)
    img.convert("RGB").save(out_path, "JPEG")


def _generate_topshot_worker(map_rel: str, result_conn: "mp.connection.Connection") -> None:
    try:
        generate_topshot(map_rel)
        result_conn.send((True, None))
    except Exception as e:
        result_conn.send((False, str(e)))
    finally:
        result_conn.close()


def generate_topshot_with_timeout(map_rel: str, timeout_seconds: float = 45) -> None:
    if timeout_seconds <= 0:
        generate_topshot(map_rel)
        return

    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    worker = ctx.Process(target=_generate_topshot_worker, args=(map_rel, child_conn))
    worker.start()
    child_conn.close()
    worker.join(timeout_seconds)

    if worker.is_alive():
        worker.terminate()
        worker.join(5)
        parent_conn.close()
        raise TimeoutError(f"Topshot generation timed out after {timeout_seconds} seconds for {map_rel}")

    if parent_conn.poll():
        ok, message = parent_conn.recv()
        parent_conn.close()
        if not ok:
            raise RuntimeError(message or f"Topshot generation failed for {map_rel}")
        return

    parent_conn.close()
    if worker.exitcode not in (0, None):
        raise RuntimeError(f"Topshot generation process failed with exit code {worker.exitcode} for {map_rel}")

    raise RuntimeError(f"Topshot generation process completed without a result for {map_rel}")


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
