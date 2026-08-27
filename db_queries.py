from utils import send
from db_io import *
import searcher
from sqlite3 import Connection
import random
import embedmaker
from collections import deque

async def _send(ctx_or_channel, **kwargs):
    """Send a message to either a slash-command context or a raw channel."""
    if hasattr(ctx_or_channel, "respond"):
        # ApplicationContext: first call uses respond(), subsequent ones use channel.send()
        if not getattr(ctx_or_channel, "_responded", False):
            await ctx_or_channel.respond(**kwargs)
            ctx_or_channel._responded = True
        else:
            await ctx_or_channel.channel.send(**kwargs)
    else:
        await ctx_or_channel.send(**kwargs)

async def print_map_search(keyword: str, conn: Connection, ctx) -> None:
    """
    prints all maps with the specified keyword in name, message or tags
    :param keyword: the query string
    :param conn: connection object of the sqlite database
    :param ctx: discord ApplicationContext or TextChannel
    :return: None
    """
    select_sql = """ SELECT map_path from maps where 
    map_path like ? or 
    message like ? or 
    map_id in (select map_id from tags where tag_name like ?)"""
    rows = [a for b in select(conn, select_sql, (f"%{keyword}%",) * 3) for a in b]

    for embed in await searcher.map_search(keyword, rows):
        await send(ctx, embed=embed)

async def print_map_info(keyword: str, conn: Connection, already_seen: deque, ctx) -> None:
    """
    prints info of either random map, random map of set subdirectory or specified map
    :param keyword:
    :param conn
    :param already_seen:
    :param ctx:
    :return: None
    """
    if keyword:
        if keyword in ['tutorials', 'beta', 'inprogress']:
            current_map = get_random_map(already_seen, conn, keyword)
        else:
            found, current_map = find_map_name(keyword, conn)
    else:
        current_map = get_random_map(already_seen, conn)

    if current_map:
        select_sql = """ select * from maps where map_path = ?"""
        rows = select(conn, select_sql, (current_map,))
        rows = [a for b in rows for a in b]
        name = rows[2]
        message = rows[3]

        select_sql = """select tag_name from tags where map_id in (select map_id from maps where map_path=?)"""
        rows = select(conn, select_sql, (current_map,))
        rows = [a for b in rows for a in b]
        tags = " ".join(rows)

        if current_map not in already_seen:
            already_seen.append(current_map)
    else:
        name = "No match"
        message = "Could not find the map. Try a different keyword"
        tags = ""

    embed = await embedmaker.make_embed(name, message=message, tags=tags)
    await send(ctx, embed=embed)

def get_random_map(already_seen: deque, conn: Connection, keyword: str = None) -> str:
    """
    get a random map name out of all maps or maps of specified subdirectory
    :param already_seen:
    :param conn:
    :param keyword:
    :return:
    """
    if keyword:
        select_sql = """select map_path from maps where map_path like ?"""
        map_memory = [a for b in select(conn, select_sql, (f"{keyword}%",)) for a in b]
    else:
        select_sql = """select map_path from maps"""
        map_memory = [a for b in select(conn, select_sql, ()) for a in b]

    while True:
        random_map = random.choice(map_memory)
        if random_map not in already_seen:
            already_seen.append(random_map)
            return random_map

