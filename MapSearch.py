import os
import sys
import zipfile
from pathlib import PurePosixPath

import discord
from config import TOKEN, upload_path, map_path
from collections import deque
from database import engine
from db_queries import print_map_search, print_map_info
from db_updates import add_map_to_db, generate_topshot, add_tag, remove_tag
from sqlmodel import Session

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking"))


bot = discord.Bot()
already_seen: deque = deque(maxlen=50)


# ---------------------------------------------------------------------------
# Public commands
# ---------------------------------------------------------------------------

@bot.slash_command(description="Search for maps by keyword (name, message or tag)")
async def mapsearch(ctx: discord.ApplicationContext, keyword: str):
    await ctx.defer()
    with Session(engine) as session:
        await print_map_search(keyword, session, ctx)


@bot.slash_command(description="Show info for a specific map, or a random map if none specified")
async def mapinfo(ctx: discord.ApplicationContext, map_name: str = None):
    await ctx.defer()
    with Session(engine) as session:
        await print_map_info(map_name, session, already_seen, ctx)


# ---------------------------------------------------------------------------
# Upload command (administrator only)
# ---------------------------------------------------------------------------

@bot.slash_command(
    description="Upload a BSP or ZIP file; generates topshot and populates database (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def upload_map(
    ctx: discord.ApplicationContext,
    file: discord.Attachment,
    subfolder: str = "",
):
    await ctx.defer()

    if not upload_path:
        await ctx.respond("Error: upload_path is not configured on the server.")
        return

    filename = file.filename.lower()
    if not (filename.endswith(".bsp") or filename.endswith(".zip")):
        await ctx.respond("Error: Only `.bsp` and `.zip` files are accepted.")
        return

    safe_subfolder = os.path.normpath(subfolder).lstrip("/\\").replace("..", "")

    saved_bsps = []

    if filename.endswith(".bsp"):
        dest_dir = os.path.join(upload_path, "maps", safe_subfolder) if safe_subfolder else os.path.join(upload_path, "maps")
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, file.filename)
        await file.save(dest_path)
        map_rel = os.path.join(safe_subfolder, os.path.splitext(file.filename)[0]) if safe_subfolder else os.path.splitext(file.filename)[0]
        saved_bsps.append(map_rel)
        await ctx.respond(f"✅ BSP saved as `maps/{map_rel}.bsp`")

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
                for member in members:
                    if os.path.isabs(member) or ".." in PurePosixPath(member).parts:
                        await ctx.respond("Error: ZIP contains unsafe paths.")
                        return
                zf.extractall(upload_path)
            for entry in bsp_entries:
                map_rel = os.path.splitext(entry[len("maps/"):])[0]
                saved_bsps.append(map_rel)
            await ctx.respond(
                f"✅ ZIP extracted. Found BSP files:\n"
                + "\n".join(f"`{e}`" for e in bsp_entries[:20])
                + ("\n…and more" if len(bsp_entries) > 20 else "")
            )
        except zipfile.BadZipFile:
            await ctx.respond("Error: The uploaded file is not a valid ZIP archive.")
            return
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # Add each new BSP to the database and generate its topshot
    with Session(engine) as session:
        for map_rel in saved_bsps:
            add_map_to_db(map_rel, session)
        session.commit()

    for map_rel in saved_bsps:
        generate_topshot(map_rel)

    if saved_bsps:
        await ctx.channel.send(f"📦 Database updated and topshots generated for: {', '.join(f'`{m}`' for m in saved_bsps)}")


# ---------------------------------------------------------------------------
# Tag management commands (administrator only)
# ---------------------------------------------------------------------------

@bot.slash_command(
    description="Add a tag to a map (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def add_map_tag(
    ctx: discord.ApplicationContext,
    map_name: str,
    tag: str,
):
    await ctx.defer()
    with Session(engine) as session:
        msg = add_tag(map_name, tag, session)
    await ctx.respond(msg)


@bot.slash_command(
    description="Remove a tag from a map (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def remove_map_tag(
    ctx: discord.ApplicationContext,
    map_name: str,
    tag: str,
):
    await ctx.defer()
    with Session(engine) as session:
        msg = remove_tag(map_name, tag, session)
    await ctx.respond(msg)


# ---------------------------------------------------------------------------
# Bot lifecycle
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (id: {bot.user.id})")
    print("------")


bot.run(TOKEN)
