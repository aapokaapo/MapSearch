import io
import os
import sys
import zipfile
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
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
    results = session.exec(
        select(Map).where(
            Map.map_path.like(kw)
            | Map.map_name.like(kw)
            | Map.message.like(kw)
            | Map.map_id.in_(tag_map_ids)
        )
    ).all()
    return results


@app.get("/api/maps/{map_path:path}/files")
def get_map_files(map_path: str, session: Session = Depends(get_session)):
    """Return the list of required files for a map."""
    from config import map_path as maps_dir, pball_path
    bsp = os.path.join(maps_dir, map_path + ".bsp")
    if not os.path.isfile(bsp):
        raise HTTPException(status_code=404, detail="BSP file not found")
    # Collect all game files referenced by the map that exist on disk
    files = []
    bsp_rel = f"maps/{map_path}.bsp"
    if os.path.isfile(os.path.join(pball_path, bsp_rel)):
        files.append({"path": bsp_rel, "available": True})
    else:
        files.append({"path": bsp_rel, "available": os.path.isfile(bsp)})
    return {"map_path": map_path, "files": files}


@app.get("/api/maps/{map_path:path}/download")
def download_map_zip(map_path: str, session: Session = Depends(get_session)):
    """Stream a ZIP archive containing the BSP and any associated files."""
    from config import map_path as maps_dir, pball_path

    bsp_file = os.path.join(maps_dir, map_path + ".bsp")
    if not os.path.isfile(bsp_file):
        raise HTTPException(status_code=404, detail="BSP file not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(bsp_file, arcname=f"maps/{map_path}.bsp")
        # Include topshot if available
        from config import topshot_path
        topshot = os.path.join(topshot_path, map_path + ".jpg")
        if os.path.isfile(topshot):
            zf.write(topshot, arcname=f"topshots/{map_path}.jpg")

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


@app.get("/api/maps/{map_path:path}/image")
def get_map_image(map_path: str):
    """Return the best available image for a map.

    Prefers a mapshot; falls back to a topshot, generating one on-demand from
    the BSP file if it does not exist yet.  Returns 404 if no image can be
    produced.
    """
    import urllib.parse
    from fastapi.responses import RedirectResponse
    from config import mapshot_path, topshot_path, map_path as maps_dir

    # Reject paths that could escape the image directories.
    if ".." in map_path.split("/") or "\\" in map_path:
        raise HTTPException(status_code=400, detail="Invalid map path")
    safe_url_path = urllib.parse.quote(map_path, safe="/")

    mapshot = os.path.join(mapshot_path, map_path + ".jpg")
    if os.path.isfile(mapshot):
        return RedirectResponse(url=f"/mapshots/{safe_url_path}.jpg", status_code=302)

    topshot = os.path.join(topshot_path, map_path + ".jpg")
    if not os.path.isfile(topshot):
        # Try to generate the topshot on-demand from the BSP.
        bsp = os.path.join(maps_dir, map_path + ".bsp")
        if os.path.isfile(bsp):
            from db_updates import generate_topshot
            generate_topshot(map_path)

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
_PBALL_DIR = os.path.join(_BASE_DIR, "pball")
_MAPSHOTS_DIR = os.path.join(_PBALL_DIR, "mapshots")
_TOPSHOTS_DIR = os.path.join(_PBALL_DIR, "topshots")
if os.path.isdir(_MAPSHOTS_DIR):
    app.mount("/mapshots", StaticFiles(directory=_MAPSHOTS_DIR), name="mapshots")
if os.path.isdir(_TOPSHOTS_DIR):
    app.mount("/topshots", StaticFiles(directory=_TOPSHOTS_DIR), name="topshots")

# Serve the frontend after API routes so it does not shadow `/api/*`.
_FRONTEND_DIR = os.path.join(_BASE_DIR, "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")