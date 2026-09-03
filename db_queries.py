import asyncio
import random
from collections import deque

import embedmaker
import searcher
from database import engine
from db_io import find_map_name
from models import Map, Tag
from sqlalchemy import case
from sqlmodel import Session, select
from utils import send


def _beta_sort_key():
    """Return a SQLAlchemy sort expression that puts beta/bN maps last."""
    _is_beta = Map.map_path.like("%beta%") | Map.map_path.op("GLOB")("*_b[0-9]*")
    return case((_is_beta, 1), else_=0)


def _search_map_paths(keyword: str) -> list[str]:
    """Return matching map paths for a keyword search."""
    kw = f"%{keyword}%"
    with Session(engine) as session:
        tag_map_ids = session.exec(
            select(Tag.map_id).where(Tag.tag_name.like(kw))
        ).all()
        maps = session.exec(
            select(Map).where(
                Map.map_path.like(kw)
                | Map.map_name.like(kw)
                | Map.message.like(kw)
                | Map.map_id.in_(tag_map_ids)
            ).order_by(_beta_sort_key())
        ).all()
    return [m.map_path for m in maps]


async def print_map_search(keyword: str, ctx) -> None:
    """Search maps by keyword in path, message, or tags and send results."""
    rows = await asyncio.to_thread(_search_map_paths, keyword)
    for embed in await searcher.map_search(keyword, rows):
        await send(ctx, embed=embed)


async def print_map_info(keyword: str, session: Session, already_seen: deque, ctx) -> None:
    """Send info embed for a specific or random map."""
    current_map_path = None

    if keyword:
        if keyword in ("tutorials", "beta", "inprogress"):
            current_map_path = _get_random_map(already_seen, session, keyword)
        else:
            found, current_map_path = find_map_name(keyword, session)
    else:
        current_map_path = _get_random_map(already_seen, session)

    if current_map_path:
        result = session.exec(
            select(Map).where(Map.map_path == current_map_path)
        ).first()
        name = result.map_path if result else "No match"
        message = result.message or "" if result else ""
        tag_rows = session.exec(
            select(Tag.tag_name).where(Tag.map_id == result.map_id)
        ).all() if result else []
        tags = " ".join(tag_rows)
        if current_map_path not in already_seen:
            already_seen.append(current_map_path)
    else:
        name = "No match"
        message = "Could not find the map. Try a different keyword"
        tags = ""

    embed = await embedmaker.make_embed(name, message=message, tags=tags)
    await send(ctx, embed=embed)


def _get_random_map(already_seen: deque, session: Session, prefix: str = None) -> str:
    """Return a random map_path not recently seen, optionally filtered by path prefix."""
    if prefix:
        maps = session.exec(
            select(Map.map_path).where(Map.map_path.like(f"{prefix}%"))
        ).all()
    else:
        maps = session.exec(select(Map.map_path)).all()

    unseen = [m for m in maps if m not in already_seen]
    if not unseen:
        already_seen.clear()
        unseen = maps
    choice = random.choice(unseen)
    already_seen.append(choice)
    return choice
