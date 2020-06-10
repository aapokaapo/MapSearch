import os
import sys

from db_io import *
from sqlite3 import Connection
from discord.channel import TextChannel
from config import map_path, pball_path, topshot_path, mapshot_path, texture_path, env_path

from skm import *

sys.path.append("../image")  # Adds higher directory to python modules path.
from Q2BSP import *

sys.path.append("../md2-importer")  # Adds higher directory to python modules path.
from md2 import *


async def get_required_files(mapname):
    """
    Returns the path of all files required by the map
    :param mapname:
    :return:
    """
    my_map = Q2BSP(map_path + mapname + ".bsp")
    required_files = list()
    if "requiredfiles" in my_map.worldspawn.keys():
        required_files = my_map.worldspawn["requiredfiles"].split(" ")
    required_files = list(dict.fromkeys(required_files))

    sky = None
    if "sky" in my_map.worldspawn.keys():
        sky = my_map.worldspawn["sky"].split(" ")[0]

    tex_names = [x.get_texture_name().lower() for x in my_map.tex_infos]
    tex_names = list(dict.fromkeys(tex_names))

    external_files = list()
    for ent in my_map.entities:
        if "model" in ent.keys() and not ent["model"].startswith("*"):
            model_path = ent["model"]
            if model_path.endswith(".md2"):
                model_path = model_path.replace(".md2", "")
            elif model_path.endswith(".skm"):
                model_path = model_path.replace(".skm", "")
            external_files.extend((model_path+".md2", model_path+".skm"))
        if "skin" in ent.keys():
            external_files.append(ent["skin"])
        if "noise" in ent.keys():
            external_files.append(ent["noise"].split(" ")[0].replace(".wav", "") + ".wav")
    external_files = list(dict.fromkeys(external_files))

    linked_skins = list()
    if external_files:
        for external_file in external_files:
            try:
                print(external_file)
                if external_file.endswith(".md2"):
                    temp_model = load_file(pball_path + external_file)
                    linked_skins.append(temp_model.skin_names[0].split("\x00")[0])
                elif external_file.endswith(".skm"):
                    _, skm_mesh = load_skm(pball_path + external_file)
                    linked_skins.extend(
                        ["/".join(external_file.split("/")[:-1]) + "/" + x.shadername for x in skm_mesh])
                    linked_skins.append(external_file.replace(".skm", "") + ".skp")
            except:
                # file doesnt exist
                print("some error with linking")
                pass

    print("linked", mapname, linked_skins)

    return required_files, sky, tex_names, external_files, linked_skins


async def print_images_provided(map_name: str, channel: TextChannel):
    """
    prints if mapshot and topshot of a map are provided
    :param map_name:
    :param channel:
    :return:
    """
    if os.path.isfile(topshot_path + map_name + ".jpg"):
        await channel.send("Topshot provided: :white_check_mark:")
    else:
        await channel.send("Topshot provided: :no_entry_sign:")
    if os.path.isfile(mapshot_path + map_name + ".jpg"):
        await channel.send("Mapshot provided: :white_check_mark:")
    else:
        await channel.send("Mapshot provided: :no_entry_sign:")


async def print_required_files(map_name: str, conn: Connection, channel: TextChannel) -> None:
    """
    prints required files of a map based on database entries
    :param map_name:
    :param conn:
    :param channel:
    :return:
    """
    await channel.send("__**" + map_name + "**__")

    # all database entries of files required by the map
    select_sql = """select * from media_files where file_id in (select file_id from requirements where map_id in (select map_id from maps where map_path=?))"""
    requirement_entries = select(conn, select_sql, (map_name,))

    # MAPSHOT AND TOPSHOT PROVIDED?
    if os.path.isfile(topshot_path + map_name + ".jpg"):
        await channel.send("Topshot provided: :white_check_mark:")
    else:
        await channel.send("Topshot provided: :no_entry_sign:")

    required_mapshot = [row for row in requirement_entries if row[2] == "mapshot"]
    print(required_mapshot)
    if required_mapshot[0][3] == 1:
        await channel.send("Mapshot provided: :white_check_mark:")
    else:
        await channel.send("Mapshot provided: :no_entry_sign:")

    sky_files = [row for row in requirement_entries if row[2] == "sky"]
    if sky_files:
        sky_provided = any([x[3] == 1 for x in sky_files])
        if sky_provided:
            await channel.send("**Sky:**\n"+sky_files[0][1][:-2]+" :white_check_mark:")
        else:
            await channel.send("**Sky:**\n"+sky_files[0][1][:-2]+" :no_entry_sign:")
    else:
        await channel.send("**Sky:**\n*No sky specified*")
    # REQUIRED FILES PROVIDED
    required_files = [row for row in requirement_entries if row[2] == "requiredfile"]
    if required_files:
        await channel.send("**Required files:**\n```" + " ".join([x[1] for x in required_files]) + "```")
        if any([x[3] is False for x in required_files]):
            await channel.send("**Missing required files:** :no_entry_sign:\n```" + " ".join(
                [x[1] for x in required_files if not x[3]]) + "```")
        else:
            await channel.send("*All required files are provided by whoa.ml* :white_check_mark:")
    else:
        await channel.send("**Required files:**\n*No requiredfiles specified*")

    # TEXTURES PROVIDED?
    textures = [row for row in requirement_entries if row[2] == "texture"]
    await channel.send("**Textures:**\n```" + " ".join([texture[1] for texture in textures]) + "```")
    if any([x[3] == False for x in textures]):
        await channel.send("**Missing textures:** :no_entry_sign:\n```" + " ".join(
            [x[1] for x in textures if not x[3]]) + "```")
    else:
        await channel.send("*All textures are provided by whoa.ml* :white_check_mark:")

    # EXTERNAL FILES PROVIDED
    external_files = [row for row in requirement_entries if row[2] == "externalfile"]
    if external_files:
        provided_files = [x for x in external_files if x[3]==1]
        missing_files = [x for x in external_files if x[3] == 0 and not x[1].split(".")[0] in [y[1].split(".")[0] for y in provided_files]]
        await channel.send(
            "**External models, skins, sound files:**\n```" + " ".join([x[1] for x in provided_files+missing_files]) + "```")
        print("missing", missing_files)
        if any(missing_files):
            await channel.send("**Missing models, skins, sound files:** :no_entry_sign:\n```" + " ".join(
                [x[1] for x in missing_files]) + "```")
        else:
            await channel.send("*All models, skins, sound files are provided by whoa.ml* :white_check_mark:")
    else:
        await channel.send("**External models, skins, sound files:**\n*No external files specified*")

    # LINKED FILES (SKINS, SKP FILES) PROVIDED?
    linked_skins = [row for row in requirement_entries if row[2] == "linkedfile"]
    if linked_skins:
        await channel.send("**Linked skins and corresponding skp files:**\n```" + " ".join(
            [x[1] for x in linked_skins]) + "```")
        if any([x[3] == False for x in linked_skins]):
            await channel.send("**Missing skins and skp files:** :no_entry_sign:\n```" + " ".join(
                [x[1] for x in linked_skins if not x[3]]) + "```")
        else:
            await channel.send("*All linked files are provided by whoa.ml* :white_check_mark:")


async def print_requirements(map_name: str, channel: TextChannel, my_map) -> None:
    """
    Computes required files on runtime
    :param map_name:
    :param channel: 
    :param my_map: 
    :return: 
    """
    await channel.send("__**" + map_name + "**__")

    # MAPSHOT AND TOPSHOT PROVIDED?
    await print_images_provided(map_name, channel)

    (required_files, sky, tex_names, exts, linkeds) = await get_required_files(map_name)

    print("sky", sky)
    #sky_provided = all([any([os.path.isfile(env_path+sky+side+ext) for ext in (".png", ".jpg", ".tga", ".pcx", ".wal")]) for side in ["bk", "dn", "ft", "lf", "rt", "up"]])

    if sky:
        sky_provided = all([any([os.path.isfile(env_path+sky+side+ext) for ext in (".png", ".jpg", ".tga", ".pcx", ".wal")]) for side in ["bk", "dn", "ft", "lf", "rt", "up"]])
        if sky_provided:
            await channel.send("**Sky:**\n"+sky +" :white_check_mark:")
        else:
            await channel.send("**Sky:**\n"+sky +" :no_entry_sign:")
    else:
        await channel.send("**Sky:**\n*No sky specified*")


    # REQUIRED FILES PROVIDED?
    if "requiredfiles" in my_map.worldspawn.keys():
        await channel.send("**Required Files**:\n```" + " ".join(required_files) + "```")

        missing_req = list()
        if required_files:
            for f in required_files:
                if not os.path.isfile(pball_path + f):
                    missing_req.append(f)
            if missing_req:
                await channel.send(
                    "**Missing required files:** :no_entry_sign:\n```" + " ".join(missing_req) + "```")
            else:
                await channel.send("*All required files are provided by whoa.ml* :white_check_mark:")
    else:
        await channel.send("**Required Files**:\n*No requiredfiles specified*")

    # TEXTURES PROVIDED?
    await channel.send("**Textures**:\n```" + " ".join(tex_names) + "```")
    missing_textures = list()
    for name in tex_names:
        print(texture_path + name + ".png")
        if not any([os.path.isfile(texture_path + name + x) for x in (".png", ".jpg", ".tga", ".pcx", ".wal")]):
            missing_textures.append(name)
    if missing_textures:
        await channel.send("**Missing textures:** :no_entry_sign:\n```" + " ".join(missing_textures) + "```")
    else:
        await channel.send("*All textures are provided by whoa.ml* :white_check_mark:")

    # MODELS, SKINS AND NOISE FILES PROVIDED?
    external_files = list()
    for ent in my_map.entities:
        print(ent.items())
        if "model" in ent.keys() and not ent["model"].startswith("*"):
            model_found = False
            for extension in (".skm", ".md2"):
                if os.path.isfile(pball_path + ent["model"].split(".")[0] + extension):
                    print(ent["model"], pball_path + ent["model"].split(".")[0] + extension)
                    external_files.append([ent["model"].split(".")[0]+extension, True])
                    model_found = True
            if not model_found:
                external_files.append([ent["model"], False])

        if "skin" in ent.keys():
            external_files.append([ent["skin"], any(
                [os.path.isfile(pball_path + ent["skin"] + x) for x in
                 (".png", ".jpg", ".tga", ".pcx", ".wal", "")])])
        if "noise" in ent.keys():
            external_files.append([ent["noise"].replace(".wav", "")+".wav", os.path.isfile(pball_path + "sound/" + ent["noise"].replace(".wav", "")+".wav")])
    external_files2 = list(dict.fromkeys([x[0] for x in external_files]))
    if external_files2:
        await channel.send("**External models, skins, sound files:**\n```" + " ".join(external_files2) + "```")
        external_files = list(dict.fromkeys([x[0] for x in external_files if not x[1]]))
        if external_files:
            await channel.send("**Missing files:** :no_entry_sign:\n```" + " ".join(external_files) + "```")
        else:
            await channel.send("*All models, skins and sound files are provided by whoa.ml* :white_check_mark:")
    else:
        await channel.send("**External models, skins, sound files:**\n*No external files specified*")

    # LINKED FILES PROVIDED?
    if linkeds:
        await channel.send("**Linked skins and corresponding skp files:**\n```" + " ".join(
            linkeds) + "```")
        missing_linkeds = list()
        for linked in linkeds:
            if not any([any([os.path.isfile(pball_path + linked + x) for x in (".skp", "")]), any(
                    [os.path.isfile(pball_path + linked.split(".")[0] + x) for x in
                     (".png", ".jpg", ".tga", ".pcx", ".wal", "")])]):
                missing_linkeds.append(linked)
        if missing_linkeds:
            await channel.send("**Missing skins and skp files:** :no_entry_sign:\n```" + " ".join(
                missing_linkeds) + "```")
        else:
            await channel.send("*All linked files are provided by whoa.ml* :white_check_mark:")
