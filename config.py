import os

path = "/var/www/html/maps/"

mapshot_path = "/var/www/html/mapshots/"

savefile = "savefile.dat"
mapdata = "mapdata.dat"

channels = []

token = token (string)

# discord.Member.id
users = []

whoa = 232103087806873600

help_message = """
    `!mapsearch` `<keyword>` - Returns a list of maps with the keyword in either name or message
    `!mapinfo` `<map name>` - Returns info about the map
    `!tagsearch` `<tag>` - Returns a list of maps with the tag
    `!status` - Returns map database info and status for sorting
    
    User commands:
    `!mapshot` `<map name>` (attached image) - Adds attached image as the maps mapshot
    `!addtag` `<map name>` `<tags>` - Adds tags for the map, separate tags with whitespace
    `!deltag` `<map name>` `<tags>` - Removes tags from the map, separate tags with whitespace
    
    Admin commands:
    `!delete` `<map name>` `<optional reason>` - Deletes the map and its mapshot, writes down reason for removal
    `!reload` - Reloads the map data
    
    Broadcast commands:
    `!broadcast` - shows a list of populated servers
    `!scores` `<ip>:<port>` - broadcast the server specified with direct ip and port
    
    Trivia commands:
    `!trivia` - starts a trivia instance, if nobody answers correctly in 50 messages, closes itself
    `pass` - passes the question
    `hint` - gives the answer letter by letter
    `quit` - closes all trivia instances
    """
