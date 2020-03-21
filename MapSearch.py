import os
import codecs
import asyncio
import discord
import random
from config import TOKEN, channel_id, path, mapshot_path, users
import shutil
import mapmover
import embedmaker


client = discord.Client()

already_seen = []

map_memory = []


class MapData:
	def __init__(self, name, message):
		"""
		name: type: str
		name: example: 'beta/greenhill_b1', 'airtime'
		message: type: str
		"""
		self.name = name
		self.message = message


def save():
    with open('savefile.txt', 'w') as myfile:
	    string = ""
	    for map in already_seen:
		    string += map + "\n"
	    myfile.write(string)
    message = "Already seen maps saved"
    print(already_seen)
    return message
		
def load():
    with open('savefile.txt', 'r') as myfile:
        already_seen.clear()
        lines = myfile.readlines()
        for line in lines:
            already_seen.append(line.replace('\n', ''))
    message = "Already seen maps loaded"
    print(already_seen)
    return message
        

#load maps to memory, slow af!
def load_maps():
    map_memory.clear()
    bsps = [] 
    for filename in os.listdir(path):
        # if filename is dir, add it to path and search that too
        if os.path.isdir(path + filename):
            new_path = path + filename + "/"
            for file in os.listdir(new_path):
                if file.endswith(".bsp"): 
                    bsps.append(filename + "/" + file) # for maps in 'maps/beta/' etc.
        else:
            if filename.endswith(".bsp"): # don't include txt, ent etc.
                bsps.append(filename) # for maps in 'maps/'
       
    for bsp in bsps:
        # default if no message is set in worldspawn
        message = "Message not found"
        # open the map as text, ignore bits        
        with codecs.open(path + bsp, 'r', encoding='utf-8',
                                     errors='ignore') as myfile:
                    print(bsp)
                    lines = myfile.readlines()
                    for line in lines:
                        # search bsp for first message which is the worldspawn message (hopefully/usually)
                        if "message".lower() in line.lower():
                            tmp = line.split(' ', 1)[-1] [1:-2] # strip quotation marks
                            print(tmp)
                            message = tmp.replace("\\n", " ") # strip linebreaks
                            break
        map_memory.append(MapData(bsp[:-4], message.strip('"')))
# great! this should be snappier than opening and closing bunch of files
print("Mapdata loaded to memory!")
load_maps() # run on load
load()


async def update_status():
	sorting_progress = len(already_seen) / len(map_memory)
    junk = len(os.listdir(path + "junk/"))
    classic = len(os.listdir(path + "classic/"))
    pub = len(os.listdir(path + "pub/"))
    match = len(os.listdir(path + "match/"))
    fix = len(os.listdir(path + "fix/"))
    beta = len(os.listdir(path + "beta/"))
    total = junk + classic + pub + match + fix + beta
    
    activity = discord.Game(name="with {} maps in database".format(total))
    await client.change_presence(activity=activity)
    
    
    mapshot_junk = len(os.listdir(mapshot_path + "junk/"))
    mapshot_classic = len(os.listdir(mapshot_path + "classic/"))
    mapshot_pub = len(os.listdir(mapshot_path + "pub/"))
    mapshot_match = len(os.listdir(mapshot_path + "match/"))
    mapshot_fix = len(os.listdir(mapshot_path + "fix/"))
    mapshot_beta = len(os.listdir(mapshot_path + "beta/"))
    mapshot_total = mapshot_junk + mapshot_classic + mapshot_pub + mapshot_match + mapshot_fix + mapshot_beta
    
    msg = "```Sorting progress for junk: {:.1%}\n".format(sorting_progress)
    msg += "Total maps {} and mapshots {} - {:.1%}\n".format(total, mapshot_total, mapshot_total/total)
    msg += "{} / {} Junk {:.1%}\n".format(junk, mapshot_junk, mapshot_junk/junk)
    msg += "{} / {} Classic {:.1%}\n".format(classic, mapshot_classic, mapshot_classic/classic)
    msg += "{} / {} Pub {:.1%}\n".format(pub, mapshot_pub, mapshot_pub/pub)
    msg += "{} / {} Match {:.1%}\n".format(match, mapshot_match, mapshot_match/match)
    msg += "{} / {} Fix {:.1%}\n".format(fix, mapshot_fix, mapshot_fix/fix)
    msg += "{} / {} Beta {:.1%}```".format(beta, mapshot_beta, mapshot_beta/beta)
    return msg

async def add_mapshot(author, keyword, image):
    """
    keyword: type: str
    keyword: example: 'beta/greenhill_b1'
    image: type: discord.Attachments
    """
    channel = client.get_channel(channel_id)
    found = False
    message = "Couldn't find the map you're uploading mapshot for"
    for map in map_memory:
        if map.name.split('/')[-1] == keyword:
            found = True
            mapname = map.name
        else:
            pass
		
    if found:
        if not os.path.exists("/var/www/html/mapshots/{}.jpg".format(mapname)):
            await image[0].save("/var/www/html/mapshots/{}.jpg".format(mapname))
            message = "Image saved as {}.jpg".format(mapname)
        else:
            msg = await channel.send("{}.jpg already exists. Do you want to overwrite it?".format(keyword))
            await msg.add_reaction(emoji="✔️")
            await msg.add_reaction(emoji="❌")
            while True:
                res, user = await client.wait_for('reaction_add', 
                                       check=lambda reaction, user: reaction.emoji == '✔️' or '❌')
                if user != author:
                    pass
                else:
                    if res.emoji == "✔️":
                        await image[0].save("/var/www/html/mapshots/{}.jpg".format(mapname))
                        message = "Image saved as {}.jpg".format(mapname)
                        break
                    else:
                        message = "Image not saved"
                        break
            await msg.delete()
            
                
    return message
    
    
async def delete_map(keyword, reason, author):
    channel = client.get_channel(channel_id)
    found = False
    delete_this = None
    message = "Couldn't find the map you're trying to delete"
    for map in map_memory:
        if map.name.split('/')[-1] == keyword:
            found = True
            delete_this = map
            mapname = map.name            
        else:
            pass
            
    if found:
        msg = await channel.send("Do you really want to remove {}?".format(keyword))
        await msg.add_reaction(emoji="✔️")
        await msg.add_reaction(emoji="❌")
        while True:
                res, user = await client.wait_for('reaction_add', 
                                       check=lambda reaction, user: reaction.emoji == '✔️' or '❌')
                if user != author:
                    pass
                else:
                    if res.emoji == "✔️":
                        os.remove(path+mapname+".bsp")
                        map_memory.remove(delete_this)
                        await update_status()
                        with open('/home/aapo/deleted_maps.txt', 'a') as myfile:
                            str = "{} - reason: {}\n".format(keyword, reason)
                            myfile.write(str)
                        message = "{} deleted, reason: {}".format(mapname, reason)
                        break
                    else:
                        message = "Did not delete {}".format(keyword)
                        break
        await msg.delete()
    return message


async def mapsearch(author, keyword):
    """
    author: type: discord.Member
    keyword: type: str
    keyword: example: 'dirtytaco'
    """
    maps = {
                'beta': "",
                'inproress': "",
                'junk': "",
                'pub': "",
                'match': "",
                'fix': "",
                'classic': "",
                'finished': ""
    }
    
    # create an empty embed and send it, edit it later
    embed = await embedmaker.make_embed(keyword, maps)
    channel = client.get_channel(channel_id)
    message = await channel.send(embed=embed)
    
    # search the maps and their messages in memory for keyword
    for map in map_memory:
        already_triggered = []
        prefix = map.name.split('/')[0]
        if prefix != map.name:
            if keyword.lower() in map.message.lower():
                if os.path.exists(mapshot_path + map.name + '.jpg'):
                    maps[prefix] += "[{}](http://whoa.gq/mapshots/{}.jpg)".format(map.name.split('/')[-1], map.name) + " "
                else:
                    maps[prefix] += map.name.split('/')[-1] + " "
                already_triggered.append(map.name)
            if keyword.lower() in map.name.lower():
                if map.name not in already_triggered:
                    if os.path.exists(mapshot_path + map.name + '.jpg'):
                        maps[prefix] += "[{}](http://whoa.gq/mapshots/{}.jpg)".format(map.name.split('/')[-1], map.name) + " "
                    else:
                        maps[prefix] += map.name.split('/')[-1] + " "
        else:
            if keyword.lower() in map.message.lower():
                if os.path.exists(mapshot_path + map.name + '.jpg'):
                    maps['finished'] += "[{}](http://whoa.gq/mapshots/{}.jpg)".format(map.name, map.name) + " "
                else:
                    maps['finished'] += map.name.split('/')[-1] + " "
                already_triggered.append(map.name)
            if keyword.lower() in map.name.lower():
                if map.name not in already_triggered:
                    if os.path.exists(mapshot_path + map.name + '.jpg'):
                        maps['finished'] += "[{}](http://whoa.gq/mapshots/{}.jpg)".format(map.name, map.name) + " "
                    else:
                        maps['finished'] += map.name.split('/')[-1] + " "
                
    # create a new embed with actual data and edit sent message
    embed = await embedmaker.make_embed(keyword, maps)
    await message.edit(embed=embed)
    
    # notify user that search is done
    await channel.send(author.mention)


async def mapinfo(author, keyword):
    """
    author: type: discord.Member
    keyword: type: str
    keyword: example: 'beta/greenhill_b1'
    """
    # create an empty embed, edit it later
    embed = await embedmaker.make_embed(keyword)
    channel = client.get_channel(channel_id)
    bot_message = await channel.send(embed=embed)
    
    # search for the bsp, and look for worldspawn message
    message = "Couldn't find the map"
    name = keyword
    for map in map_memory:
        if map.name.split('/')[-1] == keyword.lower():
            message = map.message
            name = map.name
                        
            if map.name not in already_seen:
                already_seen.append(map.name)
    
    embed = await embedmaker.make_embed(name, message=message)
    await bot_message.edit(embed=embed)                    
   
     
async def choose_random_map():
    # choose a random map from maps dir, loop until get a map that is not already seen
    while True:
        # start all over again, if every map on the list has been seen
        if len(already_seen) == len(map_memory):
            already_seen.clear()
        random_map = random.choice(map_memory)
        
        if 'junk/' in random_map.name:
            if random_map.name not in already_seen:
                already_seen.append(random_map.name)
                break

    embed = await embedmaker.make_embed(random_map.name, message=random_map.message)
    channel = client.get_channel(channel_id)
    message = await channel.send(embed=embed) 


async def check_authorization(message, type):
    channel = client.get_channel(channel_id)
    # check if user is authorized
    if message.author.id in users:
        msg = message.content.split()
        try:
            keyword = msg[1]
            await channel.send(await mapmover.move_to(map_memory, keyword, type))
        except IndexError:
            await channel.send("Error! No map name given!")


@client.event
async def on_message(message):
	
    author=message.author
    channel = client.get_channel(channel_id)
    
    # don't respond to own messages
    if message.author == client.user:
        pass
        
    # don't respond to messages in wrong channel
    elif message.channel != channel:
        pass
        
    else:
        
        if message.content.startswith('!mapsearch'):
            msg = message.content.split()
            try:
                keyword = msg[1]
                asyncio.create_task(mapsearch(author, keyword))
            except IndexError:
                await channel.send("Error! No keyword!")
                
        elif message.content.startswith('!mapinfo'):
            msg = message.content.split()
            try:
                keyword = msg[1]
                asyncio.create_task(mapinfo(author, keyword))
            except IndexError:
                await channel.send("You didn't give a keyword! Here's a random map")
                asyncio.create_task(choose_random_map())
                 
           
        elif message.content.startswith("!load"):
            await channel.send(load())
        elif message.content.startswith("!save"):
            await channel.send(save())
  
        elif message.content.startswith("!mapshot"):
            # check if user authorized
            if message.author.id in users:
                msg = message.content.split()
                try:
                    keyword = msg[1]
                    if message.attachments:
                        image = message.attachments
                        await channel.send(await add_mapshot(author, keyword, image))
                    else:
                        await channel.send("where is the pic?")
                except IndexError:
                    await channel.send("Error! No map name given!")
                    
                    
                    
        elif message.content.startswith("!junk"):
            await check_authorization(message, type="junk")
                    
        elif message.content.startswith("!classic"):
            await check_authorization(message, type="classic")
        
        elif message.content.startswith("!fix"):
            await check_authorization(message, type="fix")
            
        elif message.content.startswith("!match"):
            await check_authorization(message, type="bob")
            
        elif message.content.startswith("!pub"):
            await check_authorization(message, type="pub")
            
            
            
            
        elif message.content.startswith("!reload"):
            if message.author.id == 232103087806873600: # whoa
                await channel.send("Reloading maps! Please hold...")
                load_maps()
            
        elif message.content.startswith("!delete"):
            # check if user authorized
            if message.author.id in users:
                author = message.author
                msg = message.content.split()
                try:
                    # mapname
                    keyword = msg[1]
                    # strip the start, we know it's always '!delete <mapname>'
                    reason = message.content.replace('!delete {}'.format(keyword), "")
                    
                    await channel.send(await delete_map(keyword, reason, author))
                    
                except IndexError:
                    await channel.send("Error! No map name give!")
                
      
        elif message.content.startswith("!op"):
            if message.author.id == 232103087806873600: # whoa
                try:
                    user = message.mentions[0]
                    if user.id not in users:
                        users.append(user.id)
                        await channel.send("{} added to users!".format(user.display_name))
                    else:
                        await channel.send("{} already in users!".format(user.display_name))
                except IndexError:
                    await channel.send("You didn't mention anyone!")
        elif message.content.startswith("!deop"):
            if message.author.id == 232103087806873600: # whoa
                try:
                    user = message.mentions[0]
                    if user.id in users:
                        users.remove(user.id)
                        await channel.send("{} removed from users!".format(user.display_name))
                    else:
                        await channel.send("{} not in users!".format(user.display_name))
                except IndexError:
                    await channel.send("You didn't mention anyone!")
        
        elif message.content.startswith("!status"):
            await channel.send(await update_status())
            
            
                    

@client.event
async def on_ready():
    channel = client.get_channel(channel_id)
    print('Success. Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await update_status()
    await channel.send("Hello world! I, the Digital Paintball 2 Map Database, have awakened. I currently have {} maps loaded!".format(len(map_memory)))

client.run(TOKEN)