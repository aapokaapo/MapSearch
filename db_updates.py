import codecs
import sys

from db_io import *
import os
from config import TOKEN, mapshot_path, users, admins, savefile, mapdata, channels, help_message
from config import texture_path, env_path, pball_path, map_path
from discord.channel import TextChannel
from sqlite3 import Connection
from typing import List, Iterator
from skm import *
from map_requirements import *

sys.path.append("../image")  # Adds higher directory to python modules path.
from Q2BSP import *

sys.path.append("../md2-importer")  # Adds higher directory to python modules path.
from md2 import *


async def insert_requirements(conn, mapname):
    """
    inserts file entry into media_files table and reference into requirements table
    :param conn:
    :param mapname:
    :return:
    """
    select_sql = """insert into media_files(path, type, provided) select ?, ?, ? where not exists(select * from media_files where path=?)"""
    _ = select(conn, select_sql, (f"pics/mapshots/{mapname}", "mapshot", 0, f"pics/mapshots/{mapname}"))
    select_sql = """insert into requirements(map_id, file_id) select (select map_id from maps where map_path=?), (select file_id from media_files where path=?)"""
    _ = select(conn, select_sql, (mapname, f"pics/mapshots/{mapname}"))
    (reqs, sky, texs, exts, linkeds) = await get_required_files(mapname)
    if reqs:
        for req in reqs:
            select_sql = """insert into media_files(path, type, provided) select ?, ?, ?
            where not exists(select * from media_files where path=?)"""
            _ = select(conn, select_sql, (req, "requiredfile", 0, req))
            select_sql = """insert into requirements(map_id, file_id) select (select map_id from maps where map_path=?), (select file_id from media_files where path=?)"""
            _ = select(conn, select_sql, (mapname, req))
    if sky:
        for suffix in ["bk", "dn", "ft", "lf", "rt", "up"]:
            select_sql = """insert into media_files(path, type, provided) select ?, ?, ?
            where not exists(select * from media_files where path=?)"""
            _ = select(conn, select_sql, (sky + suffix, "sky", 0, sky + suffix))
            select_sql = """insert into requirements(map_id, file_id) select (select map_id from maps where map_path=?), (select file_id from media_files where path=?)"""
            _ = select(conn, select_sql, (mapname, sky + suffix))

    if texs:
        for req in texs:
            select_sql = """insert into media_files(path, type, provided) select ?, ?, ?
            where not exists(select * from media_files where path=?)"""
            _ = select(conn, select_sql, (req, "texture", 0, req))
            select_sql = """insert into requirements(map_id, file_id) select (select map_id from maps where map_path=?), (select file_id from media_files where path=?)"""
            _ = select(conn, select_sql, (mapname, req))
    if exts:
        for req in exts:
            select_sql = """insert into media_files(path, type, provided) select ?, ?, ?
            where not exists(select * from media_files where path=?)"""
            _ = select(conn, select_sql, (req, "externalfile", 0, req))
            select_sql = """insert into requirements(map_id, file_id) select (select map_id from maps where map_path=?), (select file_id from media_files where path=?)"""
            _ = select(conn, select_sql, (mapname, req))
    if linkeds:
        for req in linkeds:
            select_sql = """insert into media_files(path, type, provided) select ?, ?, ?
            where not exists(select * from media_files where path=?)"""
            _ = select(conn, select_sql, (req, "linkedfile", 0, req))
            select_sql = """insert into requirements(map_id, file_id) select (select map_id from maps where map_path=?), (select file_id from media_files where path=?)"""
            _ = select(conn, select_sql, (mapname, req))


async def reload_requirements(conn: Connection, channel: TextChannel = None, mapname = None) -> None:
    """
    Wipes the media_files and requirements tables and re-calculates all the requirements
    :param conn:
    :param channel:
    :return:
    """
    if mapname:
        if channel:
            await channel.send("mapname "+mapname)
        try:
            found, mapname = find_map_name(mapname, conn)
            if found:
                # delete all requirements of the map
                requirements_delete_sql = """delete from requirements where map_id in (select map_id from maps where map_path = ?)"""
                # delete all media_files entries that are only required by the specified map (the query could probably be improved)
                specific_files_delete_sql = """delete from media_files where path in (select path from (select f.path, m.map_path,count(m.map_path) as cnt from media_files f join requirements r on f.file_id=r.file_id join maps m on r.map_id = m.map_id group by f.path) where path in (select path from media_files where file_id in (select file_id from requirements where map_id in (select map_id from maps where map_path = ?))) and cnt=1);"""

                # execute the queries
                select(conn, requirements_delete_sql, (mapname, ))
                select(conn, specific_files_delete_sql, (mapname, ))

                await insert_requirements(conn, mapname)
            else:
                if channel:
                    await channel.send("Error: Map "+mapname+" not found!")
                else:
                    return -1
        except:
            if channel:
                await channel.send("An unknown error occurred!")
            else:
                return -2
    else:
        select_sql = """ select * from maps"""
        rows = select(conn, select_sql, ())
        await channel.send("Reloading requirements of " + str(len(rows)) + " files ...")

        clear_requirements(conn)
        conn.commit()
        await channel.send("passed clearing")
        for idx, row in enumerate(rows):
            try:
                found, mapname = find_map_name(row[2], conn)
                print(row, mapname)
                if found:
                    await insert_requirements(conn, mapname)
                else:
                    print("not found")
                conn.commit()
            except:
                print("except!", row)
    await update_files_provided(conn)
    if channel:
        await channel.send("Done.")
    conn.commit()


async def update_files_provided(conn):
    """
    Checks for all game files in the media_files table if they are on the server
    :param conn:
    :return:
    """
    select_sql = """ select * from media_files where type = ?"""
    rows = select(conn, select_sql, ("mapshot",))
    for row in rows:
        print(texture_path + row[1])
        if any([os.path.isfile(pball_path + row[1] + x) for x in (".png", ".jpg", ".tga", ".pcx", ".wal")]):
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (1, row[0]))
        else:
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (0, row[0]))

    select_sql = """ select * from media_files where type = ?"""
    rows = select(conn, select_sql, ("texture",))
    for row in rows:
        print(texture_path + row[1])
        if any([os.path.isfile(texture_path + row[1] + x) for x in (".png", ".jpg", ".tga", ".pcx", ".wal")]):
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (1, row[0]))
        else:
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (0, row[0]))

    select_sql = """ select * from media_files where type = ?"""
    rows = select(conn, select_sql, ("sky",))
    for row in rows:
        print(texture_path + row[1])
        if any([os.path.isfile(env_path + row[1] + x) for x in (".png", ".jpg", ".tga", ".pcx", ".wal")]):
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (1, row[0]))
        else:
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (0, row[0]))

    select_sql = """ select * from media_files where type = ?"""
    rows = select(conn, select_sql, ("requiredfile",))
    for row in rows:
        if os.path.isfile(pball_path + row[1]):
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (1, row[0]))
        else:
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (0, row[0]))

    select_sql = """ select * from media_files where type = ?"""
    rows = select(conn, select_sql, ("externalfile",))
    for row in rows:
        if any([any([os.path.isfile(pball_path + row[1] + x) for x in (".skm", ".md2")]),
                any([os.path.isfile(pball_path + row[1] + x) for x in
                 (".png", ".jpg", ".tga", ".pcx", ".wal", "")]),
                os.path.isfile(pball_path + "sound/" + row[1])]):
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (1, row[0]))
        else:
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (0, row[0]))

    select_sql = """ select * from media_files where type = ?"""
    rows = select(conn, select_sql, ("linkedfile",))
    print("rows", rows)
    for row in rows:
        if any([any([os.path.isfile(pball_path + row[1] + x) for x in (".skp", "")]), any(
                [os.path.isfile(pball_path + row[1].split(".")[0] + x) for x in
                 (".png", ".jpg", ".tga", ".pcx", ".wal", "")])]):
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (1, row[0]))
        else:
            select_sql = """update media_files set provided=? where file_id=?"""
            select(conn, select_sql, (0, row[0]))


def get_bsps(maps_path: str) -> Iterator[str]:
    """
    yields all bsp files with extension stripped in the specified directory recursively
    :param maps_path:
    :return:
    """
    for root, directories, filenames in os.walk(maps_path):
        root = root.replace(maps_path, "")
        for directory in directories:
            # print(os.path.join(root, directory))
            pass
        for filename in filenames:
            if filename.endswith(".bsp"):
                yield os.path.join(root, filename[:-4])


def reload_maps(conn: Connection) -> None:
    """
    detects differences between map directory and database and adjusts the database accordingly
    :param conn:
    :return:
    """
    bsps = list(get_bsps(map_path))
    select_sql = """ select map_path from maps"""
    map_entries = select(conn, select_sql, ())

    # remove map from database that has been deleted
    if map_entries:
        map_entries = [a for b in map_entries for a in b]
        print(map_entries)
        for row in map_entries:
            if row not in bsps:
                delete_sql = """delete from tags where map_id in (select map_id from maps where map_path=?)"""
                select(conn, delete_sql, (row,))

                delete_sql = """delete from maps where map_path=?"""
                select(conn, delete_sql, (row,))
                print("deleted", row)

    # add new bsp to database
    for bsp in bsps:
        if bsp not in map_entries:
            insert_sql = """ insert into maps(map_name, map_path, message)values(?,?,?) """
            message = "Message not found"
            # open the map as text, ignore bits
            with codecs.open(map_path + bsp + ".bsp", 'r', encoding='utf-8',
                             errors='ignore') as myfile:
                lines = myfile.readlines()
                for line in lines:
                    # search bsp for first message which is the worldspawn message (hopefully/usually)
                    if "message".lower() in line.lower():
                        tmp = line.split(' ', 1)[-1][1:-2]  # line is '"message" "<data>"', we want just data
                        print(tmp)
                        message = tmp.replace("\\n", " ")  # strip linebreaks
                        break
            select(conn, insert_sql, (bsp.split("/")[-1], bsp, message))
            print("inserted", bsp)


async def add_tags(tags: List[str], map_name: str, conn: Connection, channel: TextChannel) -> None:
    """
    Adds specified tags to map if they're not yet specified
    :param tags:
    :param map_name:
    :param conn:
    :param channel:
    :return:
    """
    for tag in tags:
        insert_sql = """insert into tags(tag_name, map_id) 
        select ?, (select map_id from maps where map_path=?)
        where not exists
        (select * from tags where tag_name = ? and map_id = (select map_id from maps where map_path=?)) """
        select(conn, insert_sql, (tag, map_name, tag, map_name))
    await channel.send(f"Added tags `{' '.join(tags)}` for map {map_name} if it wasn't set")


async def delete_tags(tags: List[str], map_name: str, conn: Connection, channel: TextChannel) -> None:
    """
    Deletes specified tags from map if they're specified
    :param tags:
    :param map_name:
    :param conn:
    :param channel:
    :return:
    """
    for tag in tags:
        insert_sql = """delete from tags where 
            map_id in (select map_id from maps where map_path=?) and 
            tag_name=? """
        select(conn, insert_sql, (map_name, tag))
    await channel.send(f"Removed tags `{' '.join(tags)}` from map {map_name}")


async def add_mapshot(author, keyword: str, image, conn: Connection, channel: TextChannel, client):
    """
    adds mapshot and database entry
    :param author:
    :param keyword:
    :param image:
    :param conn:
    :param channel:
    :param client:
    :return:
    """
    message = "Couldn't find the map you're uploading mapshot for"

    (found, mapname) = find_map_name(keyword, conn)  # there might be multiple hits?

    if found:
        # check if mapshot for the map already exists
        if not os.path.exists(mapshot_path + mapname + ".jpg"):
            await image[0].save(mapshot_path + mapname + ".jpg")
            message = "Image saved as {}.jpg".format(mapname)
            insert_mapshot_entry(conn, mapname)

        else:
            # ask user to confirm overwrite
            msg = await channel.send("{}.jpg already exists. Do you want to overwrite it?".format(keyword))
            await msg.add_reaction(emoji="✔️")
            await msg.add_reaction(emoji="❌")
            # wait until reaction from the user who executed command
            while True:
                res, user = await client.wait_for('reaction_add',
                                                  check=lambda reaction, user: reaction.emoji == '✔️' or '❌')
                if res.message.id == msg.id:
                    if user == author or user.id in admins:
                        if res.emoji == "✔️":
                            await image[0].save(mapshot_path + mapname + ".jpg")
                            message = "Image saved as {}.jpg".format(mapname)
                            insert_mapshot_entry(conn, mapname)
                            break
                        else:
                            message = "Image not saved"
                            break
            await msg.delete()

    await channel.send(message)


def insert_mapshot_entry(conn, mapname):
    """
    updates the provided column of map <map_name> and creates a new entry for the mapshot in media_files if not exists
    :param conn:
    :param mapname:
    :return:
    """
    select_sql = """update media_files set provided=1 where path like ?"""
    select(conn, select_sql, (f"%{mapname}%",))

    select_sql = """insert into media_files(path, type, provided) select ?, ?, ? where not exists(select * from media_files where path=?)"""
    select(conn, select_sql, (f"pics/mapshots/{mapname}", "mapshot", 1, f"pics/mapshots/{mapname}"))

