from config import path, mapshot_path
import os
import shutil

async def move_to(map_memory, keyword, type):
    """
    map_memory: type: list
    keyword: type: str
    type: type: str
    """
    found = False
    message = "Couldn't find the map you're trying to move!"
    # check if the map user tries to move is in memory
    for map in map_memory:
        if map.name.split('/')[-1] == keyword:
            found = True
            mapname = map.name
            # rename the map in memory with new prefix
            map.name = type + "/" + keyword.split('/')[-1]
		
        if found:
            message = "{} already in {}™".format(keyword, type)
            # check if the file is already in the dir user tries to move in
            if not os.path.exists("{}{}/{}.bsp".format(path, type, keyword)):
                message = "{} moved to {}™!".format(keyword, type)        
                shutil.move("{}{}.bsp".format(path, mapname), "{}{}/{}.bsp".format(path, type, keyword))
                # if there is a mapshot for the map, move it too
                try:
                    shutil.move("{}{}.jpg".format(mapshot_path, mapname), "{}{}/{}.jpg".format(mapshot_path, type, keyword))
                except FileNotFoundError:
                    pass
        
    return message
    

