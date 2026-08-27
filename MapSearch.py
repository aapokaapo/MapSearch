import asyncio
import os
import sys
import zipfile

import discord
from config import TOKEN, admins, upload_path, database_path, map_path
from collections import deque
from db_io import create_connection, select, find_map_name
from db_queries import print_map_search, print_map_info
from db_updates import (
    add_tags, delete_tags, add_mapshot, reload_maps, reload_requirements,
    update_files_provided,
)
from map_requirements import print_requirements, print_required_files
from broadcaster import broadcast, server_status
from trivia import trivia

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking"))
from Q2BSP import Q2BSP


bot = discord.Bot()
already_seen: deque = deque(maxlen=50)


# ---------------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------------

@bot.slash_command(description="Search for maps by keyword (name, message or tag)")
async def mapsearch(ctx: discord.ApplicationContext, keyword: str):
    conn = create_connection(database_path)
    await ctx.defer()
    await print_map_search(keyword, conn, ctx)
    conn.commit()


@bot.slash_command(description="Show map info for a specific map, subdirectory, or random")
async def mapinfo(ctx: discord.ApplicationContext, keyword: str = None):
    conn = create_connection(database_path)
    await ctx.defer()
    await print_map_info(keyword, conn, already_seen, ctx)
    conn.commit()


@bot.slash_command(description="Show database file statistics")
async def files(ctx: discord.ApplicationContext):
    conn = create_connection(database_path)
    await ctx.defer()
    queries = [
        ("requiredfile", 1), ("requiredfile", 0),
        ("texture", 1), ("texture", 0),
        ("externalfile", 1), ("externalfile", 0),
        ("linkedfile", 1), ("linkedfile", 0),
        ("mapshot", 1), ("mapshot", 0),
    ]
    results = {}
    for ftype, provided in queries:
        key = (ftype, provided)
        results[key] = select(conn, "select * from media_files where type=? and provided=?", (ftype, provided))
    map_entries = select(conn, "select * from maps", ())
    await ctx.respond(
        f"**Database file entries:**\n"
        f"Number of maps: {len(map_entries)}\n"
        f"Number of required_files: {len(results[('requiredfile',1)])} with {len(results[('requiredfile',0)])} missing\n"
        f"Number of textures: {len(results[('texture',1)])} with {len(results[('texture',0)])} missing\n"
        f"Number of models, skins, sound files: {len(results[('externalfile',1)])} with {len(results[('externalfile',0)])} missing\n"
        f"Number of model-associated files: {len(results[('linkedfile',1)])} with {len(results[('linkedfile',0)])} missing"
    )
    conn.commit()


@bot.slash_command(description="Update which required files are provided by the server")
async def updatefiles(ctx: discord.ApplicationContext):
    conn = create_connection(database_path)
    await ctx.defer()
    await update_files_provided(conn)
    conn.commit()
    await ctx.respond("Done updating")


@bot.slash_command(description="Show required files for a map from the database")
async def requiredfiles(ctx: discord.ApplicationContext, map_name: str):
    conn = create_connection(database_path)
    await ctx.defer()
    found, mapname = find_map_name(map_name, conn)
    if found:
        await print_required_files(mapname, conn, ctx)
    else:
        await ctx.respond("Error: Map not found!")
    conn.commit()


@bot.slash_command(description="Show live-computed requirements for a map")
async def requirements(ctx: discord.ApplicationContext, map_name: str):
    conn = create_connection(database_path)
    await ctx.defer()
    found, mapname = find_map_name(map_name, conn)
    if found:
        my_map = Q2BSP(map_path + mapname + ".bsp")
        await print_requirements(mapname, ctx, my_map)
    else:
        await ctx.respond("Error: Map not found!")
    conn.commit()


@bot.slash_command(description="Show populated servers")
async def broadcast_servers(ctx: discord.ApplicationContext):
    conn = create_connection(database_path)
    await ctx.defer()
    await broadcast(ctx.author, ctx, bot, admins, conn)
    conn.commit()


@bot.slash_command(description="Broadcast a server by direct IP and port")
async def scores(ctx: discord.ApplicationContext, address: str):
    conn = create_connection(database_path)
    await ctx.defer()
    try:
        ip, port = address.split(":")[0], int(address.split(":")[-1])
        asyncio.create_task(server_status(ctx.author, ip, port, conn, ctx, bot, admins))
    except (ValueError, IndexError):
        await ctx.respond("Error! Invalid address format. Use `ip:port`.")
    conn.commit()


@bot.slash_command(description="Start a map trivia game")
async def trivia_game(ctx: discord.ApplicationContext):
    conn = create_connection(database_path)
    await ctx.defer()
    await trivia(conn, bot, ctx)
    conn.commit()


# ---------------------------------------------------------------------------
# Upload command
# ---------------------------------------------------------------------------

@bot.slash_command(
    description="Upload a BSP file or a ZIP with the expected game file structure (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def upload_map(
    ctx: discord.ApplicationContext,
    file: discord.Attachment,
    subfolder: str = "",
):
    """Upload a .bsp or .zip file. The zip must contain a maps/ directory at its root."""
    await ctx.defer(ephemeral=False)

    if not upload_path:
        await ctx.respond("Error: upload_path is not configured on the server.")
        return

    filename = file.filename.lower()
    if not (filename.endswith(".bsp") or filename.endswith(".zip")):
        await ctx.respond("Error: Only `.bsp` and `.zip` files are accepted.")
        return

    # Sanitise subfolder to prevent path traversal
    safe_subfolder = os.path.normpath(subfolder).lstrip("/\\").replace("..", "")

    if filename.endswith(".bsp"):
        dest_dir = os.path.join(upload_path, "maps", safe_subfolder) if safe_subfolder else os.path.join(upload_path, "maps")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, file.filename)
        await file.save(dest_path)
        await ctx.respond(f"✅ BSP saved as `maps/{(safe_subfolder + '/') if safe_subfolder else ''}{file.filename}`")

    else:  # .zip
        tmp_path = os.path.join("/tmp", file.filename)
        await file.save(tmp_path)
        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                members = zf.namelist()
                bsp_entries = [m for m in members if m.startswith("maps/") and m.endswith(".bsp")]
                if not bsp_entries:
                    await ctx.respond("Error: ZIP does not contain any `maps/*.bsp` files.")
                    return
                # Reject path-traversal by checking individual path components
                from pathlib import PurePosixPath
                for member in members:
                    if os.path.isabs(member) or ".." in PurePosixPath(member).parts:
                        await ctx.respond("Error: ZIP contains unsafe paths.")
                        return
                zf.extractall(upload_path)
            await ctx.respond(
                f"✅ ZIP extracted to upload directory. Found BSP files:\n"
                + "\n".join(f"`{e}`" for e in bsp_entries[:20])
                + ("\n…and more" if len(bsp_entries) > 20 else "")
            )
        except zipfile.BadZipFile:
            await ctx.respond("Error: The uploaded file is not a valid ZIP archive.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


# ---------------------------------------------------------------------------
# User commands (require Manage Messages permission)
# ---------------------------------------------------------------------------

@bot.slash_command(
    description="Add a mapshot image for a map",
    default_member_permissions=discord.Permissions(manage_messages=True),
)
async def mapshot(ctx: discord.ApplicationContext, map_name: str, image: discord.Attachment):
    conn = create_connection(database_path)
    await ctx.defer()
    await add_mapshot(ctx.author, map_name, [image], conn, ctx, bot)
    conn.commit()


@bot.slash_command(
    description="Add tags to a map",
    default_member_permissions=discord.Permissions(manage_messages=True),
)
async def addtag(ctx: discord.ApplicationContext, map_name: str, tags: str):
    conn = create_connection(database_path)
    tag_list = tags.split()
    await ctx.defer()
    found, mapname = find_map_name(map_name, conn)
    if found:
        await add_tags(tag_list, mapname, conn, ctx)
    else:
        await ctx.respond("Error! Couldn't find the map")
    conn.commit()


@bot.slash_command(
    description="Remove tags from a map",
    default_member_permissions=discord.Permissions(manage_messages=True),
)
async def deltag(ctx: discord.ApplicationContext, map_name: str, tags: str):
    conn = create_connection(database_path)
    tag_list = tags.split()
    await ctx.defer()
    found, mapname = find_map_name(map_name, conn)
    if found:
        await delete_tags(tag_list, mapname, conn, ctx)
    else:
        await ctx.respond("Error! Couldn't find the map")
    conn.commit()


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------

@bot.slash_command(
    description="Reload map database from file system (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def reloadmaps(ctx: discord.ApplicationContext):
    conn = create_connection(database_path)
    await ctx.defer()
    await ctx.respond("Reloading maps! Please hold...")
    reload_maps(conn)
    conn.commit()
    await ctx.channel.send("Done!")


@bot.slash_command(
    description="Reload map requirements table (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def reloadrequirements(ctx: discord.ApplicationContext, map_name: str = None):
    conn = create_connection(database_path)
    await ctx.defer()
    await reload_requirements(conn, ctx, mapname=map_name)
    conn.commit()


# ---------------------------------------------------------------------------
# Bot lifecycle
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (id: {bot.user.id})")
    print("------")


bot.run(TOKEN)
