import os
import sys
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select

from database import get_session
from models import Map, Tag

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking"))

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
