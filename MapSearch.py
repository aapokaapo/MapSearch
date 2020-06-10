import asyncio
import sys

import discord
from config import TOKEN, users, admins, savefile, mapdata, channels, help_message
from config import mapshot_path, database_path, map_path
from collections import deque
from db_queries import *
from db_updates import *
from trivia import *
from map_requirements import *
from broadcaster import *

sys.path.append("../image")  # Adds higher directory to python modules path.
from Q2BSP import *


client = discord.Client()
already_seen = deque(maxlen=50)


@client.event
async def on_message(message):
    author = message.author
    command = message.content.split(" ")[0]

    if not command.startswith("!"):
        pass

    # create a database connection
    conn = create_connection(database_path)
    # don't respond to own messages
    if message.author == client.user:
        pass

    # don't respond to messages in wrong channel
    elif message.channel.id not in channels:
        pass

    else:
        if conn is not None:
            print(already_seen)
            channel = message.channel

            if command == '!mapsearch':
                # prints all maps that match the specified pattern (in name, message or tags)
                msg = message.content.split()
                try:
                    asyncio.create_task(print_map_search(msg[1], conn, channel))
                except IndexError:
                    await channel.send("Error! No keyword!")

            elif command == '!mapinfo':
                msg = message.content.split()
                keyword = None
                try:
                    keyword = msg[1]
                except IndexError:
                    pass
                asyncio.create_task(print_map_info(keyword, conn, already_seen, channel))

            elif command == "!help":
                await channel.send(help_message)

            elif command == "!port":
                select_sql = """select * from maps"""
                map_memory = select(conn, select_sql, ())
                print(map_memory)
                for current_map in map_memory:
                    if not any(current_map[2].startswith(x) for x in ("beta", "inprogress", "tutorials")):
                        new_path = current_map[2].split("/")[1]
                        select_sql = """update maps set map_path=? where map_id=?"""
                        select(conn, select_sql, (new_path, current_map[0]))
                        # await channel.send("old path: " + current_map[2] + " new path: " + "/".join(current_map[2].split("/")[1:]))
                    else:
                        print(current_map[2])


            elif command == "!mapshot":
                # check if user authorized
                if message.author.id in users:
                    msg = message.content.split()
                    try:
                        keyword = msg[1]
                    except IndexError:
                        await channel.send("Error! No map name given!")
                        return

                    if message.attachments:
                        image = message.attachments
                        await add_mapshot(author, keyword, image, conn, channel, client)
                    else:
                        await channel.send("where is the pic?")

            elif command == "!requirements":
                msg = message.content.split()
                try:
                    keyword = msg[1]
                    found, map_name = find_map_name(keyword, conn)
                    if found:
                        my_map = Q2BSP(map_path + map_name + ".bsp")
                        await print_requirements(map_name, channel, my_map)
                    else:
                        await channel.send("Error: Map not found!")
                except IndexError:
                    await channel.send("Error! No map name given!")

            elif command == "!requiredfiles":
                msg = message.content.split()
                try:
                    keyword = msg[1]
                    found, map_name = find_map_name(keyword, conn)
                    if found:
                        await print_required_files(map_name, conn, channel)
                    else:
                        await channel.send("Error: Map not found!")
                except IndexError:
                    await channel.send("Error! No map name given!")

            elif command == "!addtag":
                if message.author.id in users:
                    msg = message.content.replace("!addtag ", "").split()
                    if not len(msg) > 1:
                        await channel.send(
                            "Error! Invalid input length - Usage: `!addtag <map_name> <tag 1> ... <tag n>`")
                    else:
                        found, map_name = find_map_name(msg[0], conn)
                        if found:
                            await add_tags(msg[1:], map_name, conn, channel)
                        else:
                            await channel.send("Error! Couldn't find the map")
                else:
                    await channel.send("Unauthorized user!")

            elif command == "!deltag":
                if message.author.id in users:
                    msg = message.content.replace("!deltag ", "").split()
                    if not len(msg) > 1:
                        await channel.send(
                            "Error! Invalid input length - Usage: `!deltag <map_name> <tag 1> ... <tag n>`")
                    else:
                        found, map_name = find_map_name(msg[0], conn)
                        if found:
                            await delete_tags(msg[1:], map_name, conn, channel)
                        else:
                            await channel.send("Error! Couldn't find the map")
                else:
                    await channel.send("Unauthorized user!")

            elif command == "!reloadmaps":
                if message.author.id in admins:
                    await channel.send("Reloading maps! Please hold...")
                    reload_maps(conn)
                    await channel.send("Done!")

            elif command == "!reloadrequirements":
                if message.author.id in admins:
                    msg = message.content.replace("!reloadrequirements", "").strip().split(" ")
                    if msg:
                        await channel.send("reloading requirements for "+msg[0])
                        await reload_requirements(conn, channel, mapname=msg[0])
                    else:
                        await reload_requirements(conn, channel)

                else:
                    await channel.send("not authorized")

            elif command == "!test":
                found, mapname = find_map_name("beta/tlc2dm", conn)
                if found:
                    await channel.send("mapname of eclissi2 is "+ mapname)

            elif command == "!op":
                if message.author.id in admins:
                    try:
                        user = message.mentions[0]
                        if user.id not in users:
                            users.append(user.id)
                            await channel.send("{} added to users!".format(user.display_name))
                        else:
                            await channel.send("{} already in users!".format(user.display_name))
                    except IndexError:
                        await channel.send("You didn't mention anyone!")

            elif command == "!deop":
                if message.author.id in admins:
                    try:
                        user = message.mentions[0]
                        if user.id in users:
                            users.remove(user.id)
                            await channel.send("{} removed from users!".format(user.display_name))
                        else:
                            await channel.send("{} not in users!".format(user.display_name))
                    except IndexError:
                        await channel.send("You didn't mention anyone!")

            elif command == "!files":
                select_sql = """select * from media_files where type = ? and provided=1"""
                requiredfiles1 = select(conn, select_sql, ("requiredfile",))
                select_sql = """select * from media_files where type = ? and provided=0"""
                requiredfiles0 = select(conn, select_sql, ("requiredfile",))
                select_sql = """select * from media_files where type = ? and provided=1"""
                textures1 = select(conn, select_sql, ("texture",))
                select_sql = """select * from media_files where type = ? and provided=0"""
                textures0 = select(conn, select_sql, ("texture",))
                select_sql = """select * from media_files where type = ? and provided=1"""
                externalfiles1 = select(conn, select_sql, ("externalfile",))
                select_sql = """select * from media_files where type = ? and provided=0"""
                externalfiles0 = select(conn, select_sql, ("externalfile",))
                select_sql = """select * from media_files where type = ? and provided=1"""
                linkedfiles1 = select(conn, select_sql, ("linkedfile",))
                select_sql = """select * from media_files where type = ? and provided=0"""
                linkedfiles0 = select(conn, select_sql, ("linkedfile",))
                select_sql = """select * from media_files where type = ? and provided=1"""
                mapshot1 = select(conn, select_sql, ("mapshot",))
                select_sql = """select * from media_files where type = ? and provided=0"""
                mapshots0 = select(conn, select_sql, ("mapshot",))
                select_sql = """select * from maps"""
                map_entries = select(conn, select_sql, ())
                await channel.send(
                    f"**Database file entries:**\nNumber of maps: {len(map_entries)}\nNumber of required_files: {len(requiredfiles1)} with {len(requiredfiles0)} missing\nNumber of textures: {len(textures1)} with {len(textures0)} missing\nNumber of models, skins, sound files: {len(externalfiles1)} with {len(externalfiles0)} missing\nNumber of model-associated files: {len(linkedfiles1)} with {len(linkedfiles0)} missing")

            elif command == "!updatefiles":
                await update_files_provided(conn)
                await channel.send("Done updating")

            elif command == "!scores":
                msg = message.content.split()
                try:
                    addr = msg[1]
                    ip, port = addr.split(":")[0], int(addr.split(":")[-1])
                    asyncio.create_task(server_status(author, ip, port, conn, channel, client, admins))

                except IndexError:
                    await channel.send("Error! You didn't give ip")

            elif command == "!broadcast":
                asyncio.create_task(broadcast(author, channel, client, admins, conn))

            elif command == "!trivia":
                await trivia(conn, client, channel)

            conn.commit()
        else:
            print("Error! cannot create the database connection.")


@client.event
async def on_ready():
    print('Success. Logged in as', client.user.name, "with id ", client.user.id)
    print('------')
    # await update_status()


client.run(TOKEN)
