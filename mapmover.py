from config import path, mapshot_path
import os
import shutil
from db_io import *
#from MapSearch import find_map_name


async def move_to(map_memory, already_seen, keyword, conn, type):
    """
    map_memory: type: list
    keyword: type: str
    type: type: str
    """
    found = False
    message = "Couldn't find the map you're trying to move!"
    # select_sql = """ select map_path from maps where map_path = ? or map_name = ?"""
    # rows = select(conn, select_sql, (keyword,)*2)
    # rows = [a for b in rows for a in b]
    # print(rows)

    # if rows:
    #     found = True
    # map_name = rows[0]  # there might be multiple hits?

    # check if the map user tries to move is in memory
    for map in map_memory:
        if map.name.split('/')[-1] == keyword:
            found = True
            mapname = map.name
            # rename the map in memory with new prefix
            map.name = type + "/" + keyword.split('/')[-1]
    print("keyword", keyword)
    found, mapname = find_map_name(keyword, conn)
    print(found, mapname)
    if found:
        message = "{} already in {}™".format(keyword, type)
        # check if the file is already in the dir user tries to move in
        if not os.path.exists("{}{}/{}.bsp".format(path, type, keyword)):
            try:
                message = "{} moved to {}™!".format(keyword, type)
                shutil.move("{}{}.bsp".format(path, mapname), "{}{}/{}.bsp".format(path, type, keyword))
            except FileNotFoundError:
                message = "Error occured while trying to move the map!"

            # if in already_seen, rename
            if mapname in already_seen:
                already_seen.remove(mapname)
                already_seen.append("{}/{}".format(type, keyword))
            # if there is a mapshot for the map, move it too
            try:
                shutil.move("{}{}.jpg".format(mapshot_path, mapname), "{}{}/{}.jpg".format(mapshot_path, type, keyword))
            except FileNotFoundError:
                pass

    return message
