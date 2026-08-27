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


def _bsp_to_obj(bsp_path: str) -> str:
    """Convert a Quake 2 BSP file to an OBJ-format string.

    Reads the vertex, edge, surfedge and face lumps from the BSP and emits
    a minimal OBJ that Three.js (or any other OBJ consumer) can load.
    Returns an empty string if the file cannot be parsed.
    """
    try:
        with open(bsp_path, "rb") as f:
            data = f.read()
    except OSError:
        return ""

    if data[:4] != b"IBSP":
        return ""

    def lump_info(idx: int):
        off = 8 + idx * 8
        return (
            int.from_bytes(data[off : off + 4], "little"),
            int.from_bytes(data[off + 4 : off + 8], "little"),
        )

    # Lump indices
    LUMP_VERTICES  = 2
    LUMP_EDGES     = 11
    LUMP_SURFEDGES = 12
    LUMP_FACES     = 6

    v_off, v_len = lump_info(LUMP_VERTICES)
    e_off, e_len = lump_info(LUMP_EDGES)
    s_off, s_len = lump_info(LUMP_SURFEDGES)
    f_off, f_len = lump_info(LUMP_FACES)


    # Vertices: 3 × float32 (12 bytes each)
    num_verts = v_len // 12
    verts = []
    for i in range(num_verts):
        base = v_off + i * 12
        x, y, z = struct.unpack_from("<fff", data, base)
        # Q2 coords → standard (swap Y/Z, negate old Y)
        verts.append((x, z, -y))

    # Edges: 2 × uint16 (4 bytes each)
    num_edges = e_len // 4
    edges = []
    for i in range(num_edges):
        a, b = struct.unpack_from("<HH", data, e_off + i * 4)
        edges.append((a, b))

    # Surfedges: 1 × int32 (4 bytes each)
    num_surfedges = s_len // 4
    surfedges = struct.unpack_from(f"<{num_surfedges}i", data, s_off)

    # Faces: 20 bytes each; first_edge @ +0 (uint32), num_edges @ +4 (uint16)
    FACE_SIZE = 20
    num_faces = f_len // FACE_SIZE

    lines = ["# Quake 2 BSP → OBJ", "o map"]
    for x, y, z in verts:
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")

    for fi in range(num_faces):
        fbase = f_off + fi * FACE_SIZE
        first_edge, num_e = struct.unpack_from("<IH", data, fbase)
        if num_e < 3:
            continue
        face_verts = []
        for e in range(num_e):
            se_idx = first_edge + e
            if se_idx >= num_surfedges:
                continue
            se = surfedges[se_idx]
            if se >= 0:
                vi = edges[se][0] if se < num_edges else None
            else:
                vi = edges[-se][1] if -se < num_edges else None
            if vi is None or vi >= num_verts:
                continue
            face_verts.append(vi + 1)  # OBJ uses 1-based indices
        if len(face_verts) < 3:
            continue
        # Fan-triangulate
        v0 = face_verts[0]
        for t in range(1, len(face_verts) - 1):
            lines.append(f"f {v0} {face_verts[t]} {face_verts[t + 1]}")

    return "\n".join(lines) + "\n"


@app.get("/api/maps/{map_path:path}/obj")
def get_map_obj(map_path: str, session: Session = Depends(get_session)):
    """Return BSP geometry as a temporary OBJ file for 3D viewer use."""
    db_map = session.exec(select(Map).where(Map.map_path == map_path)).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")

    from config import map_path as maps_dir
    trusted_path = db_map.map_path
    bsp_file = os.path.join(maps_dir, trusted_path + ".bsp")
    if not os.path.isfile(bsp_file):
        raise HTTPException(status_code=404, detail="BSP file not found")

    obj_text = _bsp_to_obj(bsp_file)
    if not obj_text:
        raise HTTPException(status_code=422, detail="Could not convert BSP to OBJ")

    map_name = trusted_path.split("/")[-1]
    return Response(
        content=obj_text,
        media_type="model/obj",
        headers={"Content-Disposition": f'inline; filename="{map_name}.obj"'},
    )


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

    # Resolve to a trusted DB record so that path used for file I/O and
    # redirects comes from our database, not directly from user input.
    db_map = session.exec(
        select(Map).where((Map.map_path == map_path) | (Map.map_name == map_path))
    ).first()
    if not db_map:
        raise HTTPException(status_code=404, detail="Map not found")

    trusted_path = db_map.map_path
    safe_url_path = urllib.parse.quote(trusted_path, safe="/")

    mapshot = os.path.join(mapshot_path, trusted_path + ".jpg")
    if os.path.isfile(mapshot):
        return RedirectResponse(url=f"/mapshots/{safe_url_path}.jpg", status_code=302)

    topshot = os.path.join(topshot_path, trusted_path + ".jpg")
    if not os.path.isfile(topshot):
        # Try to generate the topshot on-demand from the BSP.
        bsp = os.path.join(maps_dir, trusted_path + ".bsp")
        if os.path.isfile(bsp):
            from db_updates import generate_topshot
            generate_topshot(trusted_path)

    if os.path.isfile(topshot):
        return RedirectResponse(url=f"/topshots/{safe_url_path}.jpg", status_code=302)

    raise HTTPException(status_code=404, detail="No image available for this map")


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
    from db_updates import generate_topshot
    from config import map_path

    bsp_path = os.path.join(map_path, map_name + ".bsp")
    if not os.path.isfile(bsp_path):
        raise HTTPException(status_code=404, detail=f"BSP file not found: {map_name}")

    try:
        generate_topshot(map_name)
        return {"success": True, "message": f"Topshot generated for {map_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BSP processing failed: {str(e)}")


# Serve mapshots and topshots before the frontend catch-all.
from config import mapshot_path as _MAPSHOTS_DIR, topshot_path as _TOPSHOTS_DIR
# Strip trailing slash so StaticFiles receives a plain directory path.
_MAPSHOTS_DIR = _MAPSHOTS_DIR.rstrip("/")
_TOPSHOTS_DIR = _TOPSHOTS_DIR.rstrip("/")
if os.path.isdir(_MAPSHOTS_DIR):
    app.mount("/mapshots", StaticFiles(directory=_MAPSHOTS_DIR), name="mapshots")
if os.path.isdir(_TOPSHOTS_DIR):
    app.mount("/topshots", StaticFiles(directory=_TOPSHOTS_DIR), name="topshots")

# Serve the frontend after API routes so it does not shadow `/api/*`.
_FRONTEND_DIR = os.path.join(_BASE_DIR, "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")