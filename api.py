import io
import os
import struct
import sys
import zipfile
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import case
from sqlmodel import Session, select

from database import get_session
from models import Map, Tag

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(_BASE_DIR, "bsp_hacking"))

app = FastAPI(title="MapSearch API")
_TOPSHOT_GENERATION_TIMEOUT_SECONDS = 45


# ---------------------------------------------------------------------------
# Map endpoints
# ---------------------------------------------------------------------------

@app.get("/api/maps", response_model=List[Map])
def list_maps(session: Session = Depends(get_session)):
    """Return all maps in the database."""
    return session.exec(select(Map)).all()


@app.get("/api/maps/search", response_model=List[Map])
def search_maps(keyword: str, session: Session = Depends(get_session)):
    """Search maps by keyword matching name, path, message, or tag."""
    kw = f"%{keyword}%"
    tag_map_ids = session.exec(
        select(Tag.map_id).where(Tag.tag_name.like(kw))
    ).all()
    _is_beta = Map.map_path.like("%beta%") | Map.map_path.op("GLOB")("*_b[0-9]*")
    results = session.exec(
        select(Map).where(
            Map.map_path.like(kw)
            | Map.map_name.like(kw)
            | Map.message.like(kw)
            | Map.map_id.in_(tag_map_ids)
        ).order_by(case((_is_beta, 1), else_=0))
    ).all()
    return results


@app.get("/api/maps/{map_path:path}/files")
def get_map_files(map_path: str, session: Session = Depends(get_session)):
    """Return the list of required files for a map."""
    db_map = session.exec(select(Map).where(Map.map_path == map_path)).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")
    from config import map_path as maps_dir, pball_path
    trusted_path = db_map.map_path
    bsp_file = os.path.join(maps_dir, trusted_path + ".bsp")
    if os.path.isfile(bsp_file):
        collected = _collect_map_files(bsp_file, trusted_path, pball_path)
        files = [{"path": arcname, "available": True} for _, arcname in collected]
    else:
        # BSP not on disk – report it as missing
        bsp_rel = f"pball/maps/{trusted_path}.bsp"
        files = [{"path": bsp_rel, "available": False}]
    return {"map_path": trusted_path, "files": files}


def _collect_map_files(bsp_file: str, map_rel: str, pball: str):
    """
    Return a list of (disk_path, zip_arcname) pairs for the BSP and all
    map-related loose files (textures, sounds, scripts) found under *pball*.
    Base-game files packed inside .pak archives are not on disk as loose files
    and are therefore naturally excluded.  Topshots are never included.
    """
    import re as _re

    pball = os.path.realpath(pball.rstrip("/"))
    result = []
    seen_arcnames: set = set()

    def _add(disk_path: str, arcname: str) -> None:
        # Resolve the path and ensure it stays within the pball tree to
        # prevent path traversal via maliciously crafted BSP content.
        real = os.path.realpath(disk_path)
        if not real.startswith(pball + os.sep) and real != pball:
            return
        if arcname not in seen_arcnames and os.path.isfile(real):
            seen_arcnames.add(arcname)
            result.append((real, arcname))

    # Always include the BSP itself.
    _add(bsp_file, f"pball/maps/{map_rel}.bsp")

    # Read the whole BSP once.
    real_bsp = os.path.realpath(bsp_file)
    if not real_bsp.startswith(pball + os.sep) and real_bsp != pball:
        return result
    try:
        with open(real_bsp, "rb") as _f:
            data = _f.read()
    except OSError:
        return result

    if data[:4] != b"IBSP":
        return result

    def _lump(idx: int):
        off = 8 + idx * 8
        return (
            int.from_bytes(data[off : off + 4], "little"),
            int.from_bytes(data[off + 4 : off + 8], "little"),
        )

    # ── Textures (lump 5 – tex_info, 76 bytes each, name at +40, 32 bytes) ──
    tex_off, tex_len = _lump(5)
    if tex_off + tex_len > len(data):
        return result
    textures: set = set()
    for i in range(tex_len // 76):
        base = tex_off + i * 76
        raw = data[base + 40 : base + 72]
        name = raw.decode("ascii", "ignore").rstrip("\x00")
        if name:
            textures.add(name)

    for tex in textures:
        for ext in ("wal", "png", "jpg", "tga", "pcx"):
            _add(
                os.path.join(pball, "textures", tex + "." + ext),
                f"pball/textures/{tex}.{ext}",
            )
            # Higher-resolution versions live under textures/{dir}/hr4/
            tex_dir, tex_base = os.path.split(tex)
            _add(
                os.path.join(pball, "textures", tex_dir, "hr4", tex_base + "." + ext),
                f"pball/textures/{tex_dir}/hr4/{tex_base}.{ext}",
            )

    # ── Entity lump (lump 0) – extract sound / sky references ───────────────
    ent_off, ent_len = _lump(0)
    if ent_off + ent_len > len(data):
        return result
    entity_text = data[ent_off : ent_off + ent_len].decode("cp1252", "ignore").rstrip("\x00")

    sounds: set = set()
    sky: str | None = None
    for line in entity_text.split("\n"):
        kv = _re.findall(r'"([^"]*)"', line.strip())
        if len(kv) == 2:
            key, value = kv
            if key in ("noise", "noise1", "noise2", "noise3", "noise4", "sound") and value:
                sounds.add(value)
            elif key == "sky" and value and sky is None:
                sky = value

    # Sounds – value may already include extension.
    for snd in sounds:
        if "." in snd:
            _add(os.path.join(pball, "sound", snd), f"pball/sound/{snd}")
        else:
            for ext in ("wav", "ogg", "mp3"):
                _add(
                    os.path.join(pball, "sound", snd + "." + ext),
                    f"pball/sound/{snd}.{ext}",
                )

    # Sky box faces.
    if sky:
        for suffix in ("bk", "dn", "ft", "lf", "rt", "up"):
            for ext in ("pcx", "tga", "png", "jpg"):
                _add(
                    os.path.join(pball, "env", sky + suffix + "." + ext),
                    f"pball/env/{sky}{suffix}.{ext}",
                )

    # ── Scripts associated with this map name ────────────────────────────────
    map_name = map_rel.split("/")[-1]
    scripts_dir = os.path.join(pball, "scripts")
    if os.path.isdir(scripts_dir):
        for fname in sorted(os.listdir(scripts_dir)):
            if fname.startswith(map_name + ".") or fname.startswith(map_name + "_"):
                _add(os.path.join(scripts_dir, fname), f"pball/scripts/{fname}")

    return result


@app.get("/api/maps/{map_path:path}/download")
def download_map_zip(map_path: str, session: Session = Depends(get_session)):
    """Stream a ZIP archive rooted at pball/ with the BSP and all associated files."""
    from config import map_path as maps_dir, pball_path

    bsp_file = os.path.join(maps_dir, map_path + ".bsp")
    if not os.path.isfile(bsp_file):
        raise HTTPException(status_code=404, detail="BSP file not found")

    map_files = _collect_map_files(bsp_file, map_path, pball_path)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for disk_path, arcname in map_files:
            zf.write(disk_path, arcname=arcname)

    buf.seek(0)
    map_name = map_path.split("/")[-1]
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{map_name}.zip"'},
    )


@app.get("/api/maps/{map_path:path}/bsp")
def get_bsp_file(map_path: str):
    """Stream the raw BSP file for use in the 3D viewer."""
    from config import map_path as maps_dir

    bsp_file = os.path.join(maps_dir, map_path + ".bsp")
    if not os.path.isfile(bsp_file):
        raise HTTPException(status_code=404, detail="BSP file not found")

    def iterfile():
        with open(bsp_file, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    map_name = map_path.split("/")[-1]
    return StreamingResponse(
        iterfile(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{map_name}.bsp"'},
    )


def _bsp_to_obj_stream(parsed: dict):
    """Generate streamed OBJ text from parsed BSP geometry."""
    vertices = parsed["vertices"]
    edges = parsed["edges"]
    face_edges = parsed["face_edges"]
    faces = parsed["faces"]
    tex_infos = parsed["tex_infos"]

    yield "# Quake 2 BSP -> OBJ\no map\n"
    for x, y, z in vertices:
        yield f"v {x:.6f} {z:.6f} {-y:.6f}\n"

    vt_idx = 1
    last_material = None
    for first_edge, num_edges, texinfo_idx in faces:
        if num_edges < 3 or texinfo_idx < 0 or texinfo_idx >= len(tex_infos):
            continue
        tex_info = tex_infos[texinfo_idx]
        texture_name = tex_info["name"]
        if _is_culled_surface(texture_name, tex_info["flags"]):
            continue
        face_indices = _resolve_face_indices(face_edges, edges, len(vertices), first_edge, num_edges)
        if face_indices is None:
            continue

        if texture_name != last_material:
            yield f"usemtl {texture_name}\n"
            last_material = texture_name

        s = tex_info["s"]
        tv = tex_info["t"]
        v0 = face_indices[0]
        for t in range(1, len(face_indices) - 1):
            tri = (v0, face_indices[t], face_indices[t + 1])
            tri_vt = []
            for vi in tri:
                x, y, z = vertices[vi]
                u = (x * s[0] + y * s[1] + z * s[2] + s[3]) / _OBJ_UV_SCALE
                uv_v = -((x * tv[0] + y * tv[1] + z * tv[2] + tv[3]) / _OBJ_UV_SCALE)
                yield f"vt {u:.6f} {uv_v:.6f}\n"
                tri_vt.append(vt_idx)
                vt_idx += 1
            yield (
                f"f {tri[0] + 1}/{tri_vt[0]} {tri[1] + 1}/{tri_vt[1]} {tri[2] + 1}/{tri_vt[2]}\n"
            )


_SURF_SKY = 0x0004
_SURF_TRANS33 = 0x0010
_SURF_TRANS66 = 0x0020
_SURF_NODRAW = 0x0080
_CULLED_TEXTURE_NAMES = {"sky", "hint", "clip", "skip"}
_BROWSER_TEXTURE_EXTS = ("png", "jpg", "jpeg", "webp")
_OBJ_UV_SCALE = 256.0  # default texel-to-UV divisor for OBJ export (no image size available)
# Per-texture UV scale overrides for non-hr4 textures whose on-disk image is a different
# size than the BSP UV coordinates assume.  Key is the base texture name (no path, no ext),
# value is the float multiplier applied to map.repeat in the viewer (< 1 → texture tiles
# less, compensating for an image that is smaller than expected).
_TEXTURE_UV_SCALE_OVERRIDES: dict[str, float] = {
    "chainlink1": 8,  # default image is 8× smaller than the BSP UV scale assumes
}
# Per-texture hr4 UV scale overrides.  Used instead of the default hr4 scale of 4 when the
# hr4 image is already at the canonical BSP UV size (i.e. not a 4× upscale of the original).
_TEXTURE_HR4_UV_SCALE_OVERRIDES: dict[str, float] = {
    "chainlink1": 16,  # hr4 image (128×128) is the canonical size; no extra scaling needed
}


def _bsp_lump(data: bytes, idx: int) -> tuple[int, int]:
    off = 8 + idx * 8
    if off + 8 > len(data):
        return (0, 0)
    lump_off = int.from_bytes(data[off:off + 4], "little", signed=False)
    lump_len = int.from_bytes(data[off + 4:off + 8], "little", signed=False)
    if lump_off + lump_len > len(data):
        return (0, 0)
    return (lump_off, lump_len)


def _is_culled_surface(texture_name: str, flags: int) -> bool:
    if flags & (_SURF_SKY | _SURF_NODRAW):
        return True
    lower = texture_name.lower().replace("\\", "/")
    if lower.startswith("sky") or "/sky" in lower:
        return True
    components = [part for part in lower.split("/") if part]
    return any(part in _CULLED_TEXTURE_NAMES for part in components)


def _surface_opacity(flags: int) -> float:
    if flags & _SURF_TRANS33:
        return 0.33
    if flags & _SURF_TRANS66:
        return 0.66
    return 1.0


def _resolve_face_indices(
    face_edges: list[int],
    edges: list[tuple[int, int]],
    n_vertices: int,
    first_edge: int,
    num_edges: int,
) -> list[int] | None:
    if first_edge < 0 or first_edge + num_edges > len(face_edges):
        return None
    face_indices: list[int] = []
    for fe in face_edges[first_edge:first_edge + num_edges]:
        edge_idx = fe if fe >= 0 else -fe
        if edge_idx < 0 or edge_idx >= len(edges):
            return None
        vi = edges[edge_idx][0] if fe >= 0 else edges[edge_idx][1]
        if vi < 0 or vi >= n_vertices:
            return None
        face_indices.append(vi)
    if len(face_indices) < 3:
        return None
    return face_indices


def _resolve_texture_url(texture_name: str) -> tuple[str | None, int]:
    from config import pball_path
    pball_root = os.path.realpath(pball_path.rstrip("/"))
    tex_rel = texture_name.strip("/").replace("\\", "/")
    if not tex_rel:
        return None, 1
    tex_dir, tex_base = os.path.split(tex_rel)
    candidates = []
    for ext in _BROWSER_TEXTURE_EXTS:
        if tex_dir:
            hr4_scale = _TEXTURE_HR4_UV_SCALE_OVERRIDES.get(tex_base.lower(), 4)
            candidates.append((os.path.join("textures", tex_dir, "hr4", f"{tex_base}.{ext}"), f"/pball/textures/{tex_dir}/hr4/{tex_base}.{ext}", hr4_scale))
        default_scale = _TEXTURE_UV_SCALE_OVERRIDES.get(tex_base.lower(), 1)
        candidates.append((os.path.join("textures", f"{tex_rel}.{ext}"), f"/pball/textures/{tex_rel}.{ext}", default_scale))

    for rel_disk, rel_url, uv_scale in candidates:
        disk_path = os.path.realpath(os.path.join(pball_root, rel_disk))
        if not disk_path.startswith(pball_root + os.sep):
            continue
        if os.path.isfile(disk_path):
            return rel_url, uv_scale
    return None, 1


def _parse_bsp_geometry(bsp_path: str):
    with open(bsp_path, "rb") as f:
        data = f.read()
    if data[:4] != b"IBSP":
        raise HTTPException(status_code=422, detail="Unsupported BSP format")

    vert_off, vert_len = _bsp_lump(data, 2)
    edge_off, edge_len = _bsp_lump(data, 11)
    face_edge_off, face_edge_len = _bsp_lump(data, 12)
    face_off, face_len = _bsp_lump(data, 6)
    tex_off, tex_len = _bsp_lump(data, 5)

    if not all((vert_len, edge_len, face_edge_len, face_len, tex_len)):
        raise HTTPException(status_code=422, detail="Missing BSP geometry lumps")
    if vert_len % 12 or edge_len % 4 or face_edge_len % 4 or face_len % 20 or tex_len % 76:
        raise HTTPException(status_code=422, detail="Corrupt BSP lump sizes")

    vertices = [struct.unpack_from("<fff", data, vert_off + i * 12) for i in range(vert_len // 12)]
    edges = [struct.unpack_from("<HH", data, edge_off + i * 4) for i in range(edge_len // 4)]
    face_edges = [struct.unpack_from("<i", data, face_edge_off + i * 4)[0] for i in range(face_edge_len // 4)]

    tex_infos = []
    for i in range(tex_len // 76):
        base = tex_off + i * 76
        vals = struct.unpack_from("<8fii32si", data, base)
        tex_infos.append(
            {
                "s": vals[0:4],
                "t": vals[4:8],
                "flags": vals[8],
                "name": vals[10].decode("ascii", "ignore").rstrip("\x00") or "__default__",
            }
        )

    faces = []
    for i in range(face_len // 20):
        base = face_off + i * 20
        _, _, first_edge, num_edges, texinfo_idx, _, _ = struct.unpack_from("<HhiHh4si", data, base)
        faces.append((first_edge, num_edges, texinfo_idx))

    return {
        "vertices": vertices,
        "edges": edges,
        "face_edges": face_edges,
        "faces": faces,
        "tex_infos": tex_infos,
    }


def _build_viewer_mesh_data(bsp_path: str):
    parsed = _parse_bsp_geometry(bsp_path)
    vertices = parsed["vertices"]
    edges = parsed["edges"]
    face_edges = parsed["face_edges"]
    tex_infos = parsed["tex_infos"]
    faces = parsed["faces"]

    positions: list[float] = []
    uvs: list[float] = []
    groups = []
    materials = []
    material_key_to_index: dict[tuple[str, float], int] = {}
    current_group = None
    vertex_cursor = 0

    def _material_index(texture_name: str, opacity: float) -> int:
        key = (texture_name, opacity)
        idx = material_key_to_index.get(key)
        if idx is not None:
            return idx
        idx = len(materials)
        material_key_to_index[key] = idx
        texture_url, uv_scale = _resolve_texture_url(texture_name)
        materials.append({"name": texture_name, "texture_url": texture_url, "uv_scale": uv_scale, "opacity": opacity})
        return idx

    for first_edge, num_edges, texinfo_idx in faces:
        if num_edges < 3 or texinfo_idx < 0 or texinfo_idx >= len(tex_infos):
            continue
        tex_info = tex_infos[texinfo_idx]
        texture_name = tex_info["name"] or "__default__"
        if _is_culled_surface(texture_name, tex_info["flags"]):
            continue
        face_indices = _resolve_face_indices(face_edges, edges, len(vertices), first_edge, num_edges)
        if face_indices is None:
            continue

        opacity = _surface_opacity(tex_info["flags"])
        material_index = _material_index(texture_name, opacity)
        if current_group is None or current_group["material_index"] != material_index:
            current_group = {"start": vertex_cursor, "count": 0, "material_index": material_index}
            groups.append(current_group)

        v0 = face_indices[0]
        s = tex_info["s"]
        tv = tex_info["t"]
        for t in range(1, len(face_indices) - 1):
            for vi in (v0, face_indices[t + 1], face_indices[t]):
                x, y, z = vertices[vi]
                positions.extend((x, z, -y))
                u = x * s[0] + y * s[1] + z * s[2] + s[3]
                v = -(x * tv[0] + y * tv[1] + z * tv[2] + tv[3])
                uvs.extend((u, v))
            current_group["count"] += 3
            vertex_cursor += 3

    if not positions:
        raise HTTPException(status_code=422, detail="No drawable faces found in BSP")

    return {
        "positions": positions,
        "uvs": uvs,
        "groups": groups,
        "materials": materials,
    }


@app.get("/api/maps/{map_path:path}/obj")
def get_map_obj(map_path: str, session: Session = Depends(get_session)):
    """Return BSP geometry as a streamed OBJ file for 3D viewer use."""
    db_map = session.exec(select(Map).where(Map.map_path == map_path)).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")

    from config import map_path as maps_dir
    trusted_path = db_map.map_path
    bsp_file = os.path.join(maps_dir, trusted_path + ".bsp")
    if not os.path.isfile(bsp_file):
        raise HTTPException(status_code=404, detail="BSP file not found")

    parsed = _parse_bsp_geometry(bsp_file)
    map_name = trusted_path.split("/")[-1]
    return StreamingResponse(
        _bsp_to_obj_stream(parsed),
        media_type="model/obj",
        headers={"Content-Disposition": f'inline; filename="{map_name}.obj"'},
    )


@app.get("/api/maps/{map_path:path}/viewer-mesh")
def get_map_viewer_mesh(map_path: str, session: Session = Depends(get_session)):
    db_map = session.exec(select(Map).where(Map.map_path == map_path)).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")

    from config import map_path as maps_dir
    trusted_path = db_map.map_path
    bsp_file = os.path.join(maps_dir, trusted_path + ".bsp")
    if not os.path.isfile(bsp_file):
        raise HTTPException(status_code=404, detail="BSP file not found")

    return _build_viewer_mesh_data(bsp_file)


@app.get("/api/maps/{map_path:path}/image")
def get_map_image(map_path: str, session: Session = Depends(get_session)):
    """Return the best available image for a map.

    Prefers a mapshot; falls back to a topshot, generating one on-demand from
    the BSP file if it does not exist yet.  Returns 404 if no image can be
    produced.
    """
    import urllib.parse
    from fastapi.responses import RedirectResponse
    from config import mapshot_path, topshot_path, map_path as maps_dir
    from db_updates import generate_topshot_with_timeout, iter_image_map_rels

    # Resolve to a trusted DB record so that path used for file I/O and
    # redirects comes from our database, not directly from user input.
    requested_map_ref = urllib.parse.unquote(map_path)
    db_map = session.exec(
        select(Map).where((Map.map_path == requested_map_ref) | (Map.map_name == requested_map_ref))
    ).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")

    trusted_path = db_map.map_path

    def _first_existing_image(directory: str) -> str | None:
        for image_map_rel in iter_image_map_rels(trusted_path):
            image_path = os.path.join(directory, image_map_rel + ".jpg")
            if os.path.isfile(image_path):
                return image_map_rel
        return None

    mapshot_rel = _first_existing_image(mapshot_path)
    if mapshot_rel:
        safe_url_path = urllib.parse.quote(mapshot_rel, safe="/")
        return RedirectResponse(url=f"/mapshots/{safe_url_path}.jpg", status_code=302)

    topshot_rel = _first_existing_image(topshot_path)
    generation_errors: list[str] = []
    if not topshot_rel:
        # Try to generate the topshot on-demand from the BSP.
        for candidate_map_rel in iter_image_map_rels(trusted_path):
            bsp = os.path.join(maps_dir, candidate_map_rel + ".bsp")
            if not os.path.isfile(bsp):
                continue
            try:
                generate_topshot_with_timeout(candidate_map_rel, _TOPSHOT_GENERATION_TIMEOUT_SECONDS)
            except Exception as e:
                generation_errors.append(f"{candidate_map_rel}: {e}")
                continue

            topshot_rel = _first_existing_image(topshot_path)
            if topshot_rel:
                break

    if topshot_rel:
        safe_url_path = urllib.parse.quote(topshot_rel, safe="/")
        return RedirectResponse(url=f"/topshots/{safe_url_path}.jpg", status_code=302)

    if generation_errors:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate image: " + " | ".join(generation_errors),
        )

    raise HTTPException(status_code=404, detail="No image available for this map")


@app.get("/api/maps/{map_path:path}/topshot")
def get_or_create_map_topshot(map_path: str, session: Session = Depends(get_session)):
    import urllib.parse
    from fastapi.responses import RedirectResponse
    from config import topshot_path, map_path as maps_dir
    from db_updates import generate_topshot_with_timeout, iter_image_map_rels

    requested_map_ref = urllib.parse.unquote(map_path)
    db_map = session.exec(
        select(Map).where((Map.map_path == requested_map_ref) | (Map.map_name == requested_map_ref))
    ).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")

    trusted_path = db_map.map_path
    topshot_rel = None
    for candidate_map_rel in iter_image_map_rels(trusted_path):
        candidate_topshot = os.path.join(topshot_path, candidate_map_rel + ".jpg")
        if os.path.isfile(candidate_topshot):
            topshot_rel = candidate_map_rel
            break

    generation_errors: list[str] = []
    if not topshot_rel:
        for candidate_map_rel in iter_image_map_rels(trusted_path):
            bsp = os.path.join(maps_dir, candidate_map_rel + ".bsp")
            if not os.path.isfile(bsp):
                continue
            try:
                generate_topshot_with_timeout(candidate_map_rel, _TOPSHOT_GENERATION_TIMEOUT_SECONDS)
                candidate_topshot = os.path.join(topshot_path, candidate_map_rel + ".jpg")
                if os.path.isfile(candidate_topshot):
                    topshot_rel = candidate_map_rel
                    break
            except Exception as e:
                generation_errors.append(f"{candidate_map_rel}: {e}")

    if topshot_rel:
        safe_url_path = urllib.parse.quote(topshot_rel, safe="/")
        return RedirectResponse(url=f"/topshots/{safe_url_path}.jpg", status_code=302)

    if generation_errors:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate topshot: " + " | ".join(generation_errors),
        )

    raise HTTPException(status_code=404, detail="No topshot available for this map")


@app.get("/api/maps/{map_path:path}", response_model=Map)
def get_map(map_path: str, session: Session = Depends(get_session)):
    """Return info for a specific map by its path or name."""
    result = session.exec(
        select(Map).where((Map.map_path == map_path) | (Map.map_name == map_path))
    ).first()
    if not result:
        raise HTTPException(status_code=404, detail="Map not found")
    return result


# ---------------------------------------------------------------------------
# BSP export endpoint
# ---------------------------------------------------------------------------

@app.post("/api/export-bsp")
def export_bsp(map_name: str, session: Session = Depends(get_session)):
    """Generate a topshot radar image for the given map."""
    from db_updates import generate_topshot_with_timeout, resolve_map_rel
    from config import map_path

    resolved_map_name = resolve_map_rel(map_name, session)
    bsp_path = os.path.join(map_path, resolved_map_name + ".bsp")
    if not os.path.isfile(bsp_path):
        raise HTTPException(status_code=404, detail=f"BSP file not found: {resolved_map_name}")

    try:
        generate_topshot_with_timeout(resolved_map_name, _TOPSHOT_GENERATION_TIMEOUT_SECONDS)
        return {"success": True, "message": f"Topshot generated for {resolved_map_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BSP processing failed: {str(e)}")


# Serve mapshots and topshots before the frontend catch-all.
from config import mapshot_path as _MAPSHOTS_DIR, topshot_path as _TOPSHOTS_DIR, pball_path as _PBALL_DIR
# Strip trailing slash so StaticFiles receives a plain directory path.
_MAPSHOTS_DIR = _MAPSHOTS_DIR.rstrip("/")
_TOPSHOTS_DIR = _TOPSHOTS_DIR.rstrip("/")
_PBALL_DIR = _PBALL_DIR.rstrip("/")
_PBALL_TEXTURES_DIR = os.path.join(_PBALL_DIR, "textures")
if os.path.isdir(_MAPSHOTS_DIR):
    app.mount("/mapshots", StaticFiles(directory=_MAPSHOTS_DIR), name="mapshots")
if os.path.isdir(_TOPSHOTS_DIR):
    app.mount("/topshots", StaticFiles(directory=_TOPSHOTS_DIR), name="topshots")
if os.path.isdir(_PBALL_TEXTURES_DIR):
    app.mount("/pball/textures", StaticFiles(directory=_PBALL_TEXTURES_DIR), name="pball_textures")

# Serve the frontend after API routes so it does not shadow `/api/*`.
_FRONTEND_DIR = os.path.join(_BASE_DIR, "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
