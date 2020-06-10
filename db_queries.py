from db_io import *
import searcher
from sqlite3 import Connection
from discord.channel import TextChannel
import random
import embedmaker
from collections import deque


async def print_map_search(keyword: str, conn: Connection, channel: TextChannel) -> None:
    """
    prints all maps with the specified keyword in name, message or tags
    :param keyword: the query string
    :param conn: connection object of the sqlite database
    :param channel: discord channel object
    :return: None
    """
    select_sql = """ SELECT map_path from maps where 
    map_path like ? or 
    message like ? or 
    map_id in (select map_id from tags where tag_name like ?)"""
    rows = [a for b in select(conn, select_sql, (f"%{keyword}%",) * 3) for a in b]

    for embed in await searcher.map_search(keyword, rows):
        await channel.send(embed=embed)


async def print_map_info(keyword: str, conn: Connection, already_seen: deque, channel: TextChannel) -> None:
    """
    prints info of either random map, random map of set subdirectory or specified map
    :param keyword:
    :param conn
    :param already_seen:
    :param channel:
    :return: None
    """
    tags = ""

    # get list of all maps (as path relative to maps/)
    select_sql = """select map_path from maps"""
    map_memory = [a for b in select(conn, select_sql, ()) for a in b]
    print(map_memory)
    if keyword:
        # if keyword is a maps/ subdir, pick random map out of that
        if keyword in ['tutorials', 'beta', 'inprogress']:
            current_map = get_random_map(already_seen, conn, keyword)
        # if keyword is not a maps/ subdir, find exact match within all maps in database
        else:
            found, current_map = find_map_name(keyword, conn)
    # if no keyword is specified, pick random map
    else:
        current_map = get_random_map(already_seen, conn)

    if current_map:
        # get map information (name, message, tags)
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

    # print map info as embed
    embed = await embedmaker.make_embed(name, message=message, tags=tags)
    await channel.send(embed=embed)


def get_random_map(already_seen: deque, conn: Connection, keyword: str = None) -> str:
    """
    get a random map name out of all maps or maps of specified subdirectory
    :param already_seen:
    :param conn:
    :param keyword:
    :return:
    """
    # get all maps of subdirectory keyword
    if keyword:
        select_sql = """select map_path from maps where map_path like ?"""
        map_memory = [a for b in select(conn, select_sql, (f"{keyword}%",)) for a in b]
    # get absolutely all maps in db
    else:
        select_sql = """select map_path from maps"""
        map_memory = [a for b in select(conn, select_sql, ()) for a in b]

    # get random map until it is not among the last 50 displayed maps
    while True:
        random_map = random.choice(map_memory)

        if random_map not in already_seen:
            already_seen.append(random_map)
            return random_map
