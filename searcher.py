import embedmaker
import os
from config import mapshot_path, public_mapshot_path


async def map_search(keyword, input_maps):
    maps = {
                'beta': "",
                'inprogress': "",
                'tutorials': "",
    }
    for current_map in input_maps:
        # check the prefix
        prefix = current_map.split('/')[0]
        # prefix could be map.name, if it didn't have '/' in it
        if prefix == current_map:
            prefix = 'finished'
        if not 'finished' in maps.keys():
            maps['finished'] = ""
        print(maps[prefix])
        if os.path.exists(mapshot_path + current_map + '.jpg'):
            # discord markdown for clickable link
            maps[prefix] += f"[{current_map.split('/')[-1]}]({public_mapshot_path}{current_map}.jpg) "
        else:
            # add just the name of the map if there's no mapshot
            maps[prefix] += current_map.split('/')[-1] + " "
    # print("new shit", maps)
    embeds = await embedmaker.make_embed(keyword, maps)
    # print(keyword)
    return embeds
