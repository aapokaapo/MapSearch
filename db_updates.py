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


def _get_topshot_polygons(bsp_path: str, pball_path: str):
    """
    Parse a Q2BSP file and return (polygons, average_colors) for top-shot rendering.

    Each polygon is a dict with keys 'vertices' (list of [x,y,z] floats),
    'tex_id' (index into average_colors), and 'normal' ([nx,ny,nz] floats).
    average_colors is a list of (R,G,B) or (R,G,B,A) tuples; (0,0,0,0) means
    the face should be skipped (clip/skip/hint/trigger/origin surfaces).
    """
    import math
    from PIL import Image, WalImageFile
    from Q2BSP import Q2BSP

    bsp = Q2BSP(bsp_path)

    # Build deduplicated texture list (preserving first-seen order).
    texture_list = [ti.get_texture_name() for ti in bsp.tex_infos]
    unique_textures = list(dict.fromkeys(texture_list))

    _SKIP_KEYWORDS = ("origin", "clip", "skip", "hint", "trigger")
    _SUPPORTED_EXTS = {".png", ".jpg", ".tga", ".wal"}

    _pal_cache: list[list] = []  # lazy-loaded WAL palette (stored as single-element list)

    def _get_wal_palette() -> list:
        if not _pal_cache:
            pal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking", "pb2e.pal")
            with open(pal_path) as fh:
                lines = fh.read().split("\n")[3:]
            entries = [c for line in lines for c in line.split() if c]
            _pal_cache.append(list(map(int, entries)))
        return _pal_cache[0]

    average_colors: list = []
    for texture in unique_textures:
        # Surfaces whose names contain control keywords are always transparent.
        if any(kw in texture.lower() for kw in _SKIP_KEYWORDS):
            average_colors.append((0, 0, 0, 0))
            continue

        tex_dir = "/".join(texture.lower().split("/")[:-1])
        tex_name = texture.split("/")[-1].lower()
        abs_tex_dir = os.path.join(pball_path, "textures", tex_dir)

        if not os.path.isdir(abs_tex_dir):
            average_colors.append((0, 0, 0))
            continue

        # Find the texture file (any supported extension).
        matched_path = ""
        for entry in os.listdir(abs_tex_dir):
            stem, ext = os.path.splitext(entry)
            if stem.lower() == tex_name and ext.lower() in _SUPPORTED_EXTS:
                matched_path = os.path.join(tex_dir, entry)
                break

        if not matched_path:
            average_colors.append((0, 0, 0))
            continue

        abs_path = os.path.join(pball_path, "textures", matched_path)
        ext = os.path.splitext(matched_path)[1].lower()
        try:
            if ext == ".wal":
                img = WalImageFile.open(abs_path)
                img.putpalette(_get_wal_palette())
                img = img.convert("RGBA")
            else:
                img = Image.open(abs_path).convert("RGBA")
            color = img.resize((1, 1)).getpixel((0, 0))[:3]
        except Exception:
            color = (0, 0, 0)
        average_colors.append(color)

    # Map each face's tex_info index to its index in unique_textures.
    tex_id_for_face = [
        unique_textures.index(texture_list[face.texture_info])
        for face in bsp.faces
    ]

    _SKIP_FLAGS = ("hint", "nodraw", "sky", "skip")

    # Collect vertices for every face via the edge list.
    raw_faces: list[list] = []
    skip_face_indices: list[int] = []
    for fidx, face in enumerate(bsp.faces):
        flags = bsp.tex_infos[face.texture_info].flags
        if any(getattr(flags, f, False) for f in _SKIP_FLAGS):
            skip_face_indices.append(fidx)
        verts: list = []
        for i in range(face.num_edges):
            fe = bsp.face_edges[face.first_edge + i]
            edge_idx = fe if fe >= 0 else -fe
            if edge_idx < 0 or edge_idx >= len(bsp.edge_list):
                continue
            edge = bsp.edge_list[edge_idx]
            vi = edge[0] if fe >= 0 else edge[1]
            verts.append(bsp.vertices[vi])

        # Drop duplicate closing vertex and consecutive duplicates.
        while len(verts) > 1 and verts[-1] == verts[0]:
            verts.pop()
        deduped: list = []
        for v in verts:
            if not deduped or deduped[-1] != v:
                deduped.append(v)
        if len(deduped) < 3:
            skip_face_indices.append(fidx)
        raw_faces.append(deduped)

    # Shift all vertices so minimum x, y, z == 0.
    all_verts = [v for face in raw_faces for v in face]
    min_x = min(v[0] for v in all_verts)
    min_y = min(v[1] for v in all_verts)
    min_z = min(v[2] for v in all_verts)
    norm_faces = [
        [[v[0] - min_x, v[1] - min_y, v[2] - min_z] for v in face]
        for face in raw_faces
    ]

    # Build normals; flip if plane_side != 0.
    plane_normals = [list(p.normal) for p in bsp.planes]
    normals: list[list[float]] = []
    for face in bsp.faces:
        n = plane_normals[face.plane]
        if face.plane_side != 0:
            n = [-x if x != 0.0 else x for x in n]
        normals.append(n)

    # Assemble polygon list, dropping skip surfaces (in reverse order).
    polygons = [
        {"vertices": norm_faces[i], "tex_id": tex_id_for_face[i], "normal": normals[i]}
        for i in range(len(bsp.faces))
    ]
    for i in sorted(skip_face_indices, reverse=True):
        polygons.pop(i)

    return polygons, average_colors


def _rotate_topshot_polygons(polygons: list, x_deg: float, y_deg: float, z_deg: float) -> list:
    """
    Apply Z → Y → X rotation matrices to polygon vertices and normals,
    then re-normalise so all coordinates remain ≥ 0.
    """
    import copy
    import math

    polys = copy.deepcopy(polygons)

    def _rot_z(vx, vy, angle):
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        return c * vx - s * vy, s * vx + c * vy

    def _rot_y(vx, vz, angle):
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        return c * vx + s * vz, -s * vx + c * vz

    def _rot_x(vy, vz, angle):
        c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        return c * vy - s * vz, s * vy + c * vz

    if z_deg != 0:
        for p in polys:
            for v in p["vertices"]:
                v[0], v[1] = _rot_z(v[0], v[1], z_deg)
            n = p["normal"]
            n[0], n[1] = _rot_z(n[0], n[1], z_deg)

    if y_deg != 0:
        for p in polys:
            for v in p["vertices"]:
                v[0], v[2] = _rot_y(v[0], v[2], y_deg)
            n = p["normal"]
            n[0], n[2] = _rot_y(n[0], n[2], y_deg)

    if x_deg != 0:
        for p in polys:
            for v in p["vertices"]:
                v[1], v[2] = _rot_x(v[1], v[2], x_deg)
            n = p["normal"]
            n[1], n[2] = _rot_x(n[1], n[2], x_deg)

    # Re-normalise so all coords ≥ 0.
    all_verts = [v for p in polys for v in p["vertices"]]
    min_x = min(v[0] for v in all_verts)
    min_y = min(v[1] for v in all_verts)
    min_z = min(v[2] for v in all_verts)
    for p in polys:
        for v in p["vertices"]:
            v[0] -= min_x
            v[1] -= min_y
            v[2] -= min_z

    return polys


def _render_topshot_image(
    polygons: list,
    average_colors: list,
    max_resolution: int = 2048,
) -> "Image.Image":
    """
    Render an isometric radar image from rotated polygons using a painter's algorithm.

    Orthographic projection is used so the image shows the map without perspective
    distortion.  Diffuse lighting is applied based on each face's normal relative to
    a fixed directional light to give a 3D appearance.
    Returns a PIL RGBA Image with a black background.
    """
    import copy
    import math
    from PIL import Image, ImageDraw

    # After the isometric rotation the view direction is along the Z axis (index 2).
    # Image x = vertex[0], image y = vertex[1], depth = vertex[2].
    IX, IY, DEPTH = 0, 1, 2

    # View direction (unit vector pointing from scene toward camera).
    VIEW_DIR = (0.0, 0.0, 1.0)

    # Directional light direction (unit vector pointing *toward* the light source),
    # chosen to match the upper-left lighting visible in the target image.
    _inv_sqrt3 = 1.0 / math.sqrt(3.0)
    LIGHT_DIR = (-_inv_sqrt3, -_inv_sqrt3, _inv_sqrt3)

    # Ambient and diffuse light intensities.
    AMBIENT = 0.35
    DIFFUSE = 0.65

    # Sort back-to-front (painter's algorithm): use each polygon's centroid
    # depth so faces farther from the camera are drawn first.
    def _centroid_depth(p):
        verts = p["vertices"]
        return sum(v[DEPTH] for v in verts) / len(verts)

    polys = sorted(copy.deepcopy(polygons), key=_centroid_depth)

    # Orthographic projection: use IX and IY directly (no depth division).
    all_verts = [v for p in polys for v in p["vertices"]]
    if not all_verts:
        return Image.new("RGBA", (max_resolution, max_resolution), (0, 0, 0, 255))

    pmin_x = min(v[IX] for v in all_verts)
    pmin_y = min(v[IY] for v in all_verts)
    pmax_x = max(v[IX] for v in all_verts)
    pmax_y = max(v[IY] for v in all_verts)

    span_x = max(pmax_x - pmin_x, pmax_y - pmin_y)
    if span_x == 0:
        span_x = 1.0

    w = int((pmax_x - pmin_x) / span_x * max_resolution)
    h = int((pmax_y - pmin_y) / span_x * max_resolution)
    img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    for p in polys:
        color = average_colors[p["tex_id"]]
        if len(color) == 4 and color[3] == 0:
            continue  # transparent / skip surface

        # Back-face culling: skip faces whose normal points away from the camera.
        normal = p["normal"]
        dot_view = sum(normal[i] * VIEW_DIR[i] for i in range(3))
        if dot_view < 0:
            continue

        # Diffuse lighting: dot product of face normal with light direction.
        dot_light = max(0.0, sum(normal[i] * LIGHT_DIR[i] for i in range(3)))
        brightness = AMBIENT + DIFFUSE * dot_light

        base = color[:3]
        lit_color = tuple(min(255, int(c * brightness)) for c in base)

        # Map projected coords to pixel space.
        pixel_poly = [
            (
                (v[IX] - pmin_x) / span_x * max_resolution,
                (pmax_y - v[IY]) / span_x * max_resolution,
            )
            for v in p["vertices"]
        ]
        draw.polygon(pixel_poly, fill=lit_color)

    return img


def _compute_map_yaw_angle(polygons: list) -> float:
    """
    Find the two face centroids that are furthest apart in the horizontal (X-Y)
    plane and return the yaw angle (in degrees) of the vector between them.

    This is used to auto-orient the map so its longest horizontal axis runs
    diagonally from bottom-left to top-right before the isometric pitch is
    applied, matching the appearance in the reference image.
    """
    import math

    # Compute each face's horizontal centroid (X and Y only).
    centroids = []
    for p in polygons:
        verts = p["vertices"]
        if not verts:
            continue
        cx = sum(v[0] for v in verts) / len(verts)
        cy = sum(v[1] for v in verts) / len(verts)
        centroids.append((cx, cy))

    if len(centroids) < 2:
        return 45.0

    # Find the pair of centroids with the greatest horizontal distance.
    max_dist_sq = -1.0
    far_a = centroids[0]
    far_b = centroids[-1]
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            dx = centroids[j][0] - centroids[i][0]
            dy = centroids[j][1] - centroids[i][1]
            d2 = dx * dx + dy * dy
            if d2 > max_dist_sq:
                max_dist_sq = d2
                far_a = centroids[i]
                far_b = centroids[j]

    dx = far_b[0] - far_a[0]
    dy = far_b[1] - far_a[1]
    # Angle of the longest axis, then subtract 45° so it aligns with the
    # isometric diagonal (bottom-left to top-right).
    angle_deg = math.degrees(math.atan2(dy, dx)) - 45.0
    return angle_deg


def generate_topshot(map_rel: str) -> None:
    """
    Generate a top-down radar image for the given map and save it to topshot_path.
    """
    normalized_map_rel = _normalize_map_rel(map_rel)
    bsp_path = _safe_join_under_root(map_path, normalized_map_rel, ".bsp")
    if not os.path.isfile(bsp_path):
        raise FileNotFoundError(f"BSP file not found: {normalized_map_rel}")

    out_path = _safe_join_under_root(topshot_path, normalized_map_rel, ".jpg")
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    polygons, average_colors = _get_topshot_polygons(bsp_path, pball_path)
    # Auto-orient: rotate the map in Z so its longest horizontal axis aligns
    # with the isometric diagonal, then apply 45° pitch.
    yaw_deg = _compute_map_yaw_angle(polygons)
    rotated = _rotate_topshot_polygons(polygons, x_deg=45, y_deg=0, z_deg=yaw_deg)
    img = _render_topshot_image(rotated, average_colors)
    img.convert("RGB").save(out_path, "JPEG")


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
