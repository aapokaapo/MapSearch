import os
import re
import shutil
import sys
import zipfile
from pathlib import PurePosixPath

import discord
from config import TOKEN, upload_path, map_path, mapshot_path
from collections import deque
from database import engine
from db_io import find_map_name
from db_queries import print_map_search, print_map_info
from db_updates import add_map_to_db, request_topshot_via_api, add_tag, remove_tag
from sqlmodel import Session

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "bsp_hacking"))


bot = discord.Bot()
already_seen: deque = deque(maxlen=50)
_BETA_MAP_RE = re.compile(r"(?:_beta\d+|_b\d+)$", re.IGNORECASE)
_MAPSHOT_EXTENSIONS = {".jpg", ".jpeg"}


def _normalize_relative_path(value: str) -> str:
    normalized = os.path.normpath((value or "").replace("\\", "/")).replace("\\", "/")
    if normalized in {"", "."}:
        return ""
    parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
    return "/".join(parts)


def _is_beta_map_filename(filename: str) -> bool:
    stem = os.path.splitext(os.path.basename(filename))[0]
    return bool(_BETA_MAP_RE.search(stem))


def _map_rel_from_filename(filename: str, subfolder: str = "") -> str:
    stem = os.path.splitext(os.path.basename(filename))[0]
    normalized_subfolder = _normalize_relative_path(subfolder)
    if _is_beta_map_filename(filename) and normalized_subfolder not in {"beta"} and not normalized_subfolder.startswith("beta/"):
        normalized_subfolder = f"beta/{normalized_subfolder}" if normalized_subfolder else "beta"
    return f"{normalized_subfolder}/{stem}" if normalized_subfolder else stem


def _zip_bsp_to_map_rel(entry: str) -> str:
    entry_parts = PurePosixPath(entry).parts
    entry_maps_idx = [p.lower() for p in entry_parts].index("maps")
    entry_subfolder = "/".join(entry_parts[entry_maps_idx + 1:-1])
    return _map_rel_from_filename(entry_parts[-1], entry_subfolder)


def _find_existing_map_rel(keyword: str, session: Session) -> tuple[str | None, list[str]]:
    normalized = _normalize_relative_path(keyword)
    if normalized.lower().endswith(".bsp"):
        normalized = normalized[:-4]
    if not normalized:
        return None, []

    exact_bsp = os.path.join(map_path, normalized + ".bsp")
    if os.path.isfile(exact_bsp):
        return normalized, []

    found, db_map_rel = find_map_name(normalized, session)
    if found and db_map_rel and os.path.isfile(os.path.join(map_path, db_map_rel + ".bsp")):
        return db_map_rel, []

    basename = os.path.basename(normalized).lower()
    matches = []
    for root, _, files in os.walk(map_path):
        for candidate in files:
            if candidate.lower() != f"{basename}.bsp":
                continue
            match_path = os.path.join(root, candidate)
            matches.append(os.path.splitext(os.path.relpath(match_path, map_path).replace("\\", "/"))[0])

    matches = sorted(set(matches))
    if len(matches) == 1:
        return matches[0], []
    if len(matches) > 1:
        return None, matches
    return None, []


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

class _ConfirmView(discord.ui.View):
    """A simple Yes / No confirmation view."""

    def __init__(self):
        super().__init__(timeout=60, disable_on_timeout=True)
        self.confirmed: bool | None = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.danger)
    async def yes(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.confirmed = False
        self.stop()
        await interaction.response.defer()


@bot.slash_command(
    description="Upload a BSP, ZIP, or JPG mapshot; generates topshot and updates maps (admin only)",
    default_member_permissions=discord.Permissions(administrator=True),
)
async def upload_map(
    ctx: discord.ApplicationContext,
    file: discord.Attachment,
    subfolder: str = "",
    map_name: str = "",
):
    await ctx.defer()

    filename = file.filename
    lower_filename = filename.lower()
    is_mapshot = any(lower_filename.endswith(ext) for ext in _MAPSHOT_EXTENSIONS)
    if not (lower_filename.endswith(".bsp") or lower_filename.endswith(".zip") or is_mapshot):
        await ctx.respond("Error: Only `.bsp`, `.zip`, `.jpg`, and `.jpeg` files are accepted.")
        return

    safe_subfolder = _normalize_relative_path(subfolder)

    saved_bsps = []

    if lower_filename.endswith(".bsp"):
        if not upload_path:
            await ctx.respond("Error: upload_path is not configured on the server.")
            return

        map_rel = _map_rel_from_filename(filename, safe_subfolder)
        dest_path = os.path.join(map_path, map_rel + ".bsp")
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        overwrite_confirmed = False
        if os.path.exists(dest_path):
            view = _ConfirmView()
            await ctx.respond(
                f"⚠️ `maps/{map_rel}.bsp` already exists. Overwrite?",
                view=view,
            )
            await view.wait()
            if not view.confirmed:
                cancel_msg = "⏱️ Confirmation timed out. Upload cancelled." if view.confirmed is None else "❌ Upload cancelled."
                await ctx.edit(content=cancel_msg, view=None)
                return
            overwrite_confirmed = True
            await ctx.edit(content="⏳ Overwriting…", view=None)

        await file.save(dest_path)
        saved_bsps.append(map_rel)
        bsp_msg = f"✅ BSP saved as `maps/{map_rel}.bsp`"
        if overwrite_confirmed:
            await ctx.edit(content=bsp_msg, view=None)
        else:
            await ctx.respond(bsp_msg)

    elif lower_filename.endswith(".zip"):
        if not upload_path:
            await ctx.respond("Error: upload_path is not configured on the server.")
            return

        already_responded = False
        tmp_path = os.path.join("/tmp", os.path.basename(filename))
        await file.save(tmp_path)
        try:
            with zipfile.ZipFile(tmp_path, "r") as zf:
                members = zf.namelist()

                # First pass: validate all entries for safety (no absolute paths or traversal).
                for member in members:
                    if os.path.isabs(member) or ".." in PurePosixPath(member).parts:
                        await ctx.respond("Error: ZIP contains unsafe paths.")
                        return

                # Find any .bsp file in the zip regardless of nesting depth.
                bsp_entries = [m for m in members if m.lower().endswith(".bsp") and not m.endswith("/")]
                if not bsp_entries:
                    await ctx.respond("Error: ZIP does not contain any `.bsp` files.")
                    return

                # Determine the zip-internal root prefix from the first BSP.
                # The BSP must live inside a "maps/" directory component.
                def _bsp_prefix(bsp_path: str) -> str | None:
                    parts = PurePosixPath(bsp_path).parts
                    try:
                        idx = [p.lower() for p in parts].index("maps")
                    except ValueError:
                        return None
                    prefix = "/".join(parts[:idx])
                    return prefix + "/" if prefix else ""

                first_prefix = _bsp_prefix(bsp_entries[0])
                if first_prefix is None:
                    await ctx.respond("Error: BSP file is not inside a `maps/` directory in the ZIP.")
                    return

                # Verify all BSPs share the same prefix so nothing is silently skipped.
                mismatched = [e for e in bsp_entries if _bsp_prefix(e) != first_prefix]
                if mismatched:
                    await ctx.respond(
                        "Error: ZIP contains BSP files at inconsistent nesting levels:\n"
                        + "\n".join(f"`{e}`" for e in mismatched[:10])
                    )
                    return
                zip_prefix = first_prefix

                # Check for BSP files that already exist and ask before overwriting.
                existing_bsps = []
                bsp_destinations = {}
                for entry in bsp_entries:
                    map_rel = _zip_bsp_to_map_rel(entry)
                    bsp_destinations[entry] = map_rel
                    dest_check = os.path.join(map_path, map_rel + ".bsp")
                    if os.path.exists(dest_check):
                        existing_bsps.append(f"maps/{map_rel}.bsp")

                if existing_bsps:
                    names_str = "\n".join(f"`{n}`" for n in existing_bsps[:20])
                    if len(existing_bsps) > 20:
                        names_str += "\n…and more"
                    view = _ConfirmView()
                    await ctx.respond(
                        f"⚠️ The following map(s) already exist. Overwrite?\n{names_str}",
                        view=view,
                    )
                    already_responded = True
                    await view.wait()
                    if not view.confirmed:
                        cancel_msg = "⏱️ Confirmation timed out. Upload cancelled." if view.confirmed is None else "❌ Upload cancelled."
                        await ctx.edit(content=cancel_msg, view=None)
                        return
                    await ctx.edit(content="⏳ Overwriting…", view=None)

                # Allowed top-level directories within the pball root.
                ALLOWED_DIRS = {"maps", "textures", "sound", "env", "scripts", "pics"}

                real_upload = os.path.realpath(upload_path)
                extracted_count = 0

                for member in members:
                    if member.endswith("/"):  # skip directory entries
                        continue

                    # Strip the zip prefix to get the pball-relative path.
                    if zip_prefix and not member.startswith(zip_prefix):
                        continue
                    rel = member[len(zip_prefix):]
                    if not rel:
                        continue

                    # Only extract files under known safe directories.
                    first_component = PurePosixPath(rel).parts[0].lower() if PurePosixPath(rel).parts else ""
                    if first_component not in ALLOWED_DIRS:
                        continue

                    dest_rel = rel
                    if first_component == "maps" and rel.lower().endswith(".bsp"):
                        dest_rel = f"maps/{bsp_destinations[member]}.bsp"

                    dest = os.path.normpath(os.path.join(upload_path, dest_rel))
                    # Final path-traversal guard after normpath.
                    if not os.path.realpath(dest).startswith(real_upload + os.sep):
                        await ctx.respond("Error: ZIP contains unsafe paths.")
                        return

                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(member) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    extracted_count += 1

                saved_bsps.extend(dict.fromkeys(bsp_destinations.values()))

            success_msg = (
                f"✅ ZIP extracted ({extracted_count} files). Found BSP files:\n"
                + "\n".join(f"`maps/{m}.bsp`" for m in saved_bsps[:20])
                + ("\n…and more" if len(saved_bsps) > 20 else "")
            )
            if already_responded:
                await ctx.edit(content=success_msg, view=None)
            else:
                await ctx.respond(success_msg)
        except zipfile.BadZipFile:
            await ctx.respond("Error: The uploaded file is not a valid ZIP archive.")
            return
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    else:
        if not mapshot_path:
            await ctx.respond("Error: mapshot_path is not configured on the server.")
            return

        requested_map_name = map_name or os.path.splitext(filename)[0]
        with Session(engine) as session:
            target_map_rel, matches = _find_existing_map_rel(requested_map_name, session)

        if matches:
            names_str = "\n".join(f"`{match}`" for match in matches[:10])
            if len(matches) > 10:
                names_str += "\n…and more"
            await ctx.respond(
                "Error: Multiple BSPs match that mapshot name. Provide `map_name` with the full map path.\n"
                + names_str
            )
            return

        if not target_map_rel:
            await ctx.respond("Error: No matching BSP exists for that mapshot name.")
            return

        dest_path = os.path.join(mapshot_path, target_map_rel + ".jpg")
        real_mapshot_root = os.path.realpath(mapshot_path)
        if not os.path.realpath(dest_path).startswith(real_mapshot_root + os.sep):
            await ctx.respond("Error: Invalid mapshot destination path.")
            return
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        overwrite_confirmed = False
        if os.path.exists(dest_path):
            view = _ConfirmView()
            await ctx.respond(
                f"⚠️ `pics/mapshots/{target_map_rel}.jpg` already exists. Overwrite?",
                view=view,
            )
            await view.wait()
            if not view.confirmed:
                cancel_msg = "⏱️ Confirmation timed out. Upload cancelled." if view.confirmed is None else "❌ Upload cancelled."
                await ctx.edit(content=cancel_msg, view=None)
                return
            overwrite_confirmed = True
            await ctx.edit(content="⏳ Overwriting…", view=None)

        await file.save(dest_path)
        mapshot_msg = f"✅ Mapshot saved as `pics/mapshots/{target_map_rel}.jpg`"
        if overwrite_confirmed:
            await ctx.edit(content=mapshot_msg, view=None)
        else:
            await ctx.respond(mapshot_msg)
        return

    # Add each new BSP to the database and generate its topshot
    with Session(engine) as session:
        for map_rel in saved_bsps:
            add_map_to_db(map_rel, session)
        session.commit()

    for map_rel in saved_bsps:
        request_topshot_via_api(map_rel)

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
