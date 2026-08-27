import codecs
import os
import sys

from sqlmodel import Session, select

from config import map_path, topshot_path, pball_path
from models import Map

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking"))


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


def generate_topshot(map_rel: str) -> None:
    """
    Generate a top-down radar image for the given map and save it to topshot_path.
    """
    bsp_path = map_path + map_rel + ".bsp"
    if not os.path.isfile(bsp_path):
        return

    out_path = topshot_path + map_rel + ".jpg"
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    try:
        import radar_image
        radar_image.create_image(
            path_to_pball=pball_path,
            map_path=bsp_path,
            image_type="top",
            mode=0,
            image_path=out_path,
        )
    except Exception as e:
        print(f"generate_topshot: failed for {map_rel}: {e}")
