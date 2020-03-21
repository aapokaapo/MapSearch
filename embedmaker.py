import discord
import math

def split_string(map_string, maps_length):
    maps = map_string.split()
    strings = []
    string = ""
    last_map = maps[-1]
    i = 0
    while True:
        # if string is not longer than 1024, add next map
        if not len(string + maps[i]) > 1024:
            string += maps[i] + " "
            if not last_map in string:
                i += 1
            else:
                strings.append(string)
                break
        else:
            strings.append(string)
            if not last_map in string:
                string = ""
                i += 1
            else:
                break
    return strings
	    

    #middle = math.floor(maps_length/2)
    #splitter = map_string.find(" ", middle, maps_length)
    #first_half = map_string[0:splitter]
    #second_half = map_string[splitter:maps_length]
    #return first_half, second_half

async def make_embed(keyword, maps=None, message=None):
    """
    keyword: type: str
    maps: type: list
    message: type: str
    """
    embed = discord.Embed(title="whoa's map search tool", description="Searching for: {}".format(keyword), color=0xfed900)
    if maps:
        for category in maps:
            if len(maps[category]) !=0:
                length = len(maps[category])
                if length >= 1024:
                    strings = split_string(maps[category], length)
                    for string in strings:
                        embed.add_field(name=category,  value=string,
                                    inline=False)
                else:
                    embed.add_field(name=category, value=maps[category],
                                inline=False)
        # DirtyTaco add code here for mapshots in grid, maps is a list of strings (mapnames)
      
    elif message:
        embed.add_field(name="Results", value=message.replace("\\n", " "),
                        inline=False)
        #await make_link(keyword)
        embed.add_field(name="Download", value="[CLICK HERE TO DOWNLOAD](http://whoa.gq/maps/{}.bsp)".format(keyword),
                        inline=False)
        embed.set_image(url="http://whoa.gq/mapshots/{}.jpg".format(keyword))
        
    return embed
    
    