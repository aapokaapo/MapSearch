from config import path, mapshot_path
import os
import shutil

async def move_to(map_memory, keyword, type):
    """
    keyword: type: str
    """
    found = False
    message = "Couldn't find the map you're trying to move!"
    for map in map_memory:
        if map.name.split('/')[-1] == keyword:
            found = True
            mapname = map.name
            map.name = type + "/" + keyword.split('/')[-1]
        else:
            pass
		
    if found:
        message = "{} already in {}™".format(keyword, type)  
        if not os.path.exists("{}{}/{}.bsp".format(path, type, keyword)):
            message = "{} moved to {}™!".format(keyword, type)        
            shutil.move("{}{}.bsp".format(path, mapname), "{}{}/{}.bsp".format(path, type, keyword))
            try:
                shutil.move("{}{}.jpg".format(mapshot_path, mapname), "{}{}/{}.jpg".format(mapshot_path, type, keyword))
            except FileNotFoundError:
                pass
        
    return message
    

