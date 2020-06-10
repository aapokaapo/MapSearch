pball_path = 
topshot_path = 
mapshot_path = 
model_path = 
texture_path = 
env_path = 
script_path = 
map_path = 
sound_path = 
database_path = 
public_mapshot_path = 
local_mapshot_path = 
trivia_path = 
public_trivia_path = 
server_list = 
public_topshot_path = 
public_map_path = 

# discord channel ids
channels = []


# discord user ids
users = []

# discord bot token
TOKEN = 

admins = []

help_message = """
    **Admin commands:**
    `!reloadmaps` - Updates the map data (in comparison to the file system)
    `!reloadrequirements` - Reloads tables for map requirements and specified if they're provided

    **User commands:**
    `!mapshot` `<map name>` (attached image) - Adds attached image as the maps mapshot
    `!addtag` `<map name>` `<tags>` - Adds tags for the map, separate tags with whitespace
    `!deltag` `<map name>` `<tags>` - Removes tags from the map, separate tags with whitespace

    **Public commands:**
    `!updatefiles` - Updates if required files are provided by the server
    `!files` - lists how many maps are on the server and how many of their required files are provided or not
    
    *Map Browser*
    `!mapsearch` `<keyword>` - Returns a list of maps with the keyword in either name or message
    `!mapinfo` `<map name>` - Returns map information (path, message, tags etc.)
    
    *Broadcast*
    `!broadcast` - shows a list of populated servers
    `!scores` `<ip>:<port>` - broadcast the server specified with direct ip and port
    
    *Trivia*
    `!trivia` - starts a trivia instance, if nobody answers correctly in 50 messages, closes itself
    `pass` - passes the question
    `hint` - gives the answer letter by letter
    `quit` - closes all trivia instances
    """
