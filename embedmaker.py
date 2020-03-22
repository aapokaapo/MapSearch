import discord


def split_string(maps_string):
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
        # if adding next map doesn't make the string longer than 1024, do it
        if not len(string + maps[i]) >= 1024:
            string += maps[i] + " "
            # added map wasn't last_map, continue adding
            if not last_map in string:
                i += 1
            # last_map met, break
            else:
                strings.append(string)
                break
        # string would be over 1024, append current and create empty string
        else:
            strings.append(string)
            string = ""
            
    # return a list of strings
    return strings
	    

async def make_embed(keyword, maps=None, message=None):
    """
    keyword: type: str
    maps: type: dict
    maps: keys: 'junk', 'beta', 'fix', 'inprogress', 'match', 'pub', 'finished', 'classic'
    message: type: str
    """
    embeds = []
    embed = discord.Embed(title="whoa's map search tool", description="Searching for: {}".format(keyword), color=0xfed900)
    if maps:
        i = 1
        # cycle through all the categories
        for category in maps:
            # check if category is not empty
            if len(maps[category]) != 0:
                # default to these if category length is less than 1024
                strings = [ maps[category] ]
                last_string = maps[category]          
                # embed field[value] limit is 1024, split data to chunks of 1024 if exceeds limit
                if len(maps[category]) >= 1024:
                    strings = split_string(maps[category])                    
                    last_string = strings[-1]
                    
                # cycle through all the strings, embed can fit 5 fields max (6000 chars max, 5 * 1024 = 5120, but just to be sure...)
                x = 0
                while True:
                    if i <= 5:
                        print(i)
                        embed.add_field(name=category,  value=strings[x],
                                   inline=False)
                        # keep going until last_string
                        if last_string != strings[x]:
                            i += 1
                            x += 1
                        # last_string, break
                        else:
                            x += 1
                            i += 1
                            print("last string met! breaking")
                            break
                    # if embed has 5 fields, append current and make an empty one
                    else:
                        print("5 fields, creating new embes")
                        embeds.append(embed)
                        embed = discord.Embed(title="whoa's map search tool", description="Searching for: {}".format(keyword), color=0xfed900)
                        i += 1
                        
        # when done with all strings, append the last embed
        embeds.append(embed)
        # returns a list if embeds
        return embeds
      
    elif message:
        # if message is not empty
        if message != "":
            # add the map message to embed
            embed.add_field(name="Results", value=message,
                            inline=False)
            # add download link
            embed.add_field(name="Download", value="[CLICK HERE TO DOWNLOAD](http://whoa.gq/maps/{}.bsp)".format(keyword),
                            inline=False)
            # add a mapshot
            embed.set_image(url="http://whoa.gq/mapshots/{}.jpg".format(keyword))
            
        # returns a single embed
        return embed
    
    