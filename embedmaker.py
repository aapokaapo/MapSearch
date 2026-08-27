import discord
from config import public_mapshot_path, public_topshot_path, public_map_path


async def split_string(maps_string):
    """
    map_string: type: str
    map_string: example: "[map.name](url + map.name) [map.name](url + map.name)"
    """
    maps = maps_string.split()
    strings = []
    string = ""
    last_map = maps[-1]
    i = 0
    while True:
        if not len(string + maps[i]) >= 1024:
            string += maps[i] + " "
            if not last_map in string:
                i += 1
            else:
                strings.append(string)
                break
        else:
            strings.append(string)
            if last_map in string:
                break
            string = ""

    return strings


async def make_embed(keyword, maps=None, message=None, tags=None):
    """
    keyword: type: str
    maps: type: dict (category -> space-separated clickable map links)
    message: type: str (map worldspawn message)
    tags: type: str
    """
    embeds = []
    embed = discord.Embed(title="MapSearch", description="Searching for: {}".format(keyword), color=0xfed900)
    if maps:
        i = 1
        for category in maps:
            if len(maps[category]) != 0:
                strings = [maps[category]]
                last_string = maps[category]
                if len(maps[category]) >= 1024:
                    strings = await split_string(maps[category])
                    last_string = strings[-1]

                x = 0
                while True:
                    if i <= 5:
                        embed.add_field(name=category, value=strings[x], inline=False)
                        if last_string != strings[x]:
                            i += 1
                            x += 1
                        else:
                            x += 1
                            i += 1
                            break
                    else:
                        embeds.append(embed)
                        embed = discord.Embed(title="MapSearch", description="Searching for: {}".format(keyword), color=0xfed900)
                        i = 1

        embeds.append(embed)
        return embeds

    elif message:
        if message == "":
            message = "No map message"
        embed.add_field(name="Description", value=message, inline=False)
        if tags:
            embed.add_field(name="Tags", value=tags, inline=False)
        if keyword != "No match":
            embed.add_field(
                name="Download",
                value="[CLICK HERE TO DOWNLOAD](" + public_map_path + keyword + ".bsp)",
                inline=False,
            )
            embed.set_image(url=public_mapshot_path + keyword + ".jpg")
            embed.set_thumbnail(url=public_topshot_path + keyword + ".jpg")
        return embed
