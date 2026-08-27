from typing import Optional, Tuple

from sqlmodel import Session, select

from models import Map


def find_map_name(keyword: str, session: Session) -> Tuple[bool, Optional[str]]:
    """
    Return the first map_path that exactly matches the given keyword
    against map_path or map_name.
    """
    result = session.exec(
        select(Map).where((Map.map_path == keyword) | (Map.map_name == keyword))
    ).first()
    if result:
        return True, result.map_path
    return False, None
