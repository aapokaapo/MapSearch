import codecs
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
# Topshot rendering — top-down overview with BSP culling
# ---------------------------------------------------------------------------

# Surface flags (mirror of api.py constants)
_SURF_SKY = 0x0004
_SURF_TRANS33 = 0x0010
_SURF_TRANS66 = 0x0020
_SURF_NODRAW = 0x0080
_CULLED_TEXTURE_NAMES = {"sky", "hint", "clip", "skip"}


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


def _ts_projected_plane_coeffs(
    projected_vertices: list[tuple[float, float, float]]
) -> tuple[float, float, float] | None:
    """
    Return coefficients for z = ax + by + c in projected top-down space.

    Faces that are vertical (or otherwise degenerate in top-down projection)
    cannot be expressed this way and return None.
    """
    if len(projected_vertices) < 3:
        return None

    p0 = projected_vertices[0]
    for i in range(1, len(projected_vertices) - 1):
        p1 = projected_vertices[i]
        p2 = projected_vertices[i + 1]

        ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
        vx, vy, vz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
        nx = uy * vz - uz * vy
        ny = uz * vx - ux * vz
        nz = ux * vy - uy * vx
        if abs(nz) > 1e-6:
            a = -nx / nz
            b = -ny / nz
            c = p0[2] - a * p0[0] - b * p0[1]
            return (a, b, c)

    return None


def _ts_draw_height_shaded_polygon(
    img,
    poly_px: list[tuple[float, float]],
    avg_z: float,
    opacity: float,
    min_z: float,
    z_range: float,
    plane_coeffs: tuple[float, float, float] | None,
    min_x: float,
    min_y: float,
    scale: float,
) -> None:
    from PIL import Image, ImageDraw

    if len(poly_px) < 3:
        return

    x_coords = [pt[0] for pt in poly_px]
    y_coords = [pt[1] for pt in poly_px]
    x0 = max(0, int(min(x_coords)))
    y0 = max(0, int(min(y_coords)))
    x1 = min(img.width, int(max(x_coords) + 1.0))
    y1 = min(img.height, int(max(y_coords) + 1.0))
    if x1 <= x0 or y1 <= y0:
        return

    local_poly = [(px - x0, py - y0) for px, py in poly_px]
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).polygon(local_poly, fill=255)
    mask_data = list(mask.getdata())
    if not any(mask_data):
        return

    shade_values: list[int] = []
    if plane_coeffs is None:
        t = max(0.0, min(1.0, (avg_z - min_z) / z_range))
        shade = int(60 + 170 * t)
        shade_values = [shade] * (mask.width * mask.height)
    else:
        a, b, c = plane_coeffs
        for py in range(mask.height):
            sy = min_y + (y0 + py + 0.5) / scale
            for px in range(mask.width):
                sx = min_x + (x0 + px + 0.5) / scale
                z = a * sx + b * sy + c
                t = max(0.0, min(1.0, (z - min_z) / z_range))
                shade_values.append(int(60 + 170 * t))

    alpha = int(255 * opacity)
    tile_data = [
        (shade, shade, shade, alpha if mask_alpha else 0)
        for shade, mask_alpha in zip(shade_values, mask_data)
    ]
    tile = Image.new("RGBA", (mask.width, mask.height))
    tile.putdata(tile_data)
    img.alpha_composite(tile, dest=(x0, y0))


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



def _render_topshot_topdown(bsp_path: str, max_resolution: int = 1024) -> "Image.Image":
    """
    Render a top-down orthographic overview of the BSP map.

    The camera looks straight down the BSP Z axis so the XY plane of the map
    is projected onto the image.  Surfaces are culled using the same rules as
    the 3D viewer (sky, nodraw, hint, clip, skip).  Back-facing opaque surfaces
    are culled via the 2-D signed area of their projection (FrontSide); transparent
    surfaces are rendered from both sides (DoubleSide).  Painter's algorithm
    (back-to-front by Z elevation) handles depth ordering.  Each polygon is
    filled with grey height shading derived from its elevation (dark = low,
    light = high), using a smooth per-pixel gradient on sloped faces when
    possible.  Returns a PIL RGBA image.
    """
    from PIL import Image

    parsed = _ts_parse_bsp(bsp_path)
    vertices = parsed["vertices"]
    edges = parsed["edges"]
    face_edges = parsed["face_edges"]
    tex_infos = parsed["tex_infos"]
    faces = parsed["faces"]

    # Collect all visible polygons with their screen-space data.
    # Top-down projection: screen_x = BSP_x, screen_y = -BSP_y, depth = BSP_z
    # (negating Y so the image Y axis increases downward as in screen space).
    polys: list[tuple] = []  # (avg_z, screen_pts, opacity, plane_coeffs)
    fallback_polys: list[tuple] = []
    polys_z_values: list[float] = []
    fallback_z_values: list[float] = []

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
        projected_vertices = []
        for vi in face_indices:
            bx, by, bz = vertices[vi]
            sx_list.append(bx)
            sy_list.append(-by)
            z_list.append(bz)
            projected_vertices.append((bx, -by, bz))

        # Back-face culling via 2-D signed area (Shoelace formula).
        # The projection is (BSP_x, -BSP_y), so the Y negation flips winding:
        # front-facing polygons wind clockwise in screen space and therefore
        # produce a negative signed area here. Positive area means the face is
        # back-facing in the top-down view; zero-area projections are kept so
        # nearly-vertical slopes do not disappear.
        # Opaque surfaces: cull back-faces (FrontSide), matching the 3D viewer.
        # Transparent surfaces: render from both sides (DoubleSide).
        n = len(sx_list)
        signed_area = 0.0
        for i in range(n):
            j = (i + 1) % n
            signed_area += sx_list[i] * sy_list[j] - sx_list[j] * sy_list[i]

        avg_z = sum(z_list) / len(z_list)
        screen_pts = list(zip(sx_list, sy_list))
        plane_coeffs = _ts_projected_plane_coeffs(projected_vertices)
        fallback_polys.append((avg_z, screen_pts, opacity, plane_coeffs))
        fallback_z_values.extend(z_list)

        if signed_area > 0:
            if opacity >= 1.0:
                continue  # back-facing opaque surface — cull it

        polys.append((avg_z, screen_pts, opacity, plane_coeffs))
        polys_z_values.extend(z_list)

    if not polys:
        # Some maps (for example pyramid interiors) can end up entirely
        # back-facing from a strict top-down test. Fall back to drawing all
        # non-culled surfaces instead of returning a blank image.
        polys = fallback_polys
        polys_z_values = fallback_z_values
    if not polys:
        return Image.new("RGBA", (max_resolution, max_resolution), (255, 255, 255, 255))

    # Compute world bounding box.
    all_sx = [pt[0] for _, pts, _, _ in polys for pt in pts]
    all_sy = [pt[1] for _, pts, _, _ in polys for pt in pts]
    all_z = polys_z_values

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

    # Painter's algorithm: draw back-to-front (lowest Z first).
    polys.sort(key=lambda p: p[0])

    img = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 255))

    for avg_z, screen_pts, opacity, plane_coeffs in polys:
        poly_px = [to_px(sx, sy) for sx, sy in screen_pts]
        _ts_draw_height_shaded_polygon(
            img=img,
            poly_px=poly_px,
            avg_z=avg_z,
            opacity=opacity,
            min_z=min_z,
            z_range=z_range,
            plane_coeffs=plane_coeffs,
            min_x=min_x,
            min_y=min_y,
            scale=scale,
        )

    return img


def generate_topshot(map_rel: str) -> None:
    """
    Generate a top-down overview image for the given map and save it to
    topshot_path.  Uses BSP culling (sky, nodraw, hint, clip, skip) and a
    height-based grey shading with painter's algorithm for depth ordering.
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
