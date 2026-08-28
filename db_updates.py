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

    import radar_image

    radar_image.create_image(
        path_to_pball=pball_path,
        map_path=bsp_path,
        image_type="top",
        mode=0,
        image_path=out_path,
    )


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
