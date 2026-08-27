from typing import Optional, Tuple

from sqlalchemy import case
from sqlmodel import Session, select

from models import Map


def _beta_sort_key():
    """Return a SQLAlchemy sort expression that puts beta/bN maps last."""
    _is_beta = Map.map_path.like("%beta%") | Map.map_path.op("GLOB")("*_b[0-9]*")
    return case((_is_beta, 1), else_=0)


def find_map_name(keyword: str, session: Session) -> Tuple[bool, Optional[str]]:
    """
    Return the first map_path that exactly matches the given keyword
    against map_path or map_name, preferring non-beta maps.
    """
    result = session.exec(
        select(Map)
        .where((Map.map_path == keyword) | (Map.map_name == keyword))
        .order_by(_beta_sort_key())
    ).first()
    if result:
        return True, result.map_path
    return False, None
