import embedmaker
import os
from config import mapshot_path

async def mapsearch(map_memory, keyword, tags=False):
    """
    author: type: discord.Member
    keyword: type: str
    keyword: example: 'dirtytaco'
    """
    maps = {
                'beta': "",
                'inprogress': "",
                'junk': "",
                'pub': "",
                'match': "",
                'fix': "",
                'classic': "",
                'finished': "",
                'tutorials': ""
    }

    # search the maps and their messages in memory for keyword
    for map in map_memory:
        # check the prefix
        prefix = map.name.split('/')[0]
        # prefix could be map.name, if it didn't have '/' in it
        if prefix == map.name:
            prefix = 'finished'
        if not tags:
            # check if keyword can be found in the map message or the map name
            if keyword.lower() in map.message.lower() or keyword.lower() in map.name.lower():
                # check if the map has mapshot, create a link to image if so
                if os.path.exists(mapshot_path + map.name + '.jpg'):
                    # discord markdown for clickable link
                    maps[prefix] += "[{}](http://whoa.ml/mapshots/{}.jpg)".format(map.name.split('/')[-1], map.name) + " "
                else:
                    # add just the name of the map if there's no mapshot
                    maps[prefix] += map.name.split('/')[-1] + " "
                
        else:
            if keyword.lower() in map.tags:
                # check if the map has mapshot, create a link to image if so
                if os.path.exists(mapshot_path + map.name + '.jpg'):
                    # discord markdown for clickable link
                    maps[prefix] += "[{}](http://whoa.ml/mapshots/{}.jpg)".format(map.name.split('/')[-1], map.name) + " "
                else:
                    # add just the name of the map if there's no mapshot
                    maps[prefix] += map.name.split('/')[-1] + " "
    # creates list of embeds from the maps
    embeds = await embedmaker.make_embed(keyword, maps)
    
    return embeds