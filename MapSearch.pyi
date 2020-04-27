import os
import codecs
import asyncio
import discord
import random
from config import TOKEN, path, mapshot_path, users, whoa, savefile, mapdata, channels, help_message
import shutil
import mapmover
import embedmaker
import pickle
import searcher
from serverinfo import status



client = discord.Client()
channel = None


already_seen = []

map_memory = []


class MapData:
	def __init__(self, name, message, tags):
		"""
		name: type: str
		name: example: 'beta/greenhill_b1', 'airtime'
		message: type: str
		"""
		self.name = name
		self.message = message
		self.tags = tags
   

#load maps to memory, slow af! //  TODO create a db out of the list so ideally you would have to generate the db just once
def get_bsps():
	
    bsps = [] 
    
    for filename in os.listdir(path):
        # if filename is dir, add it to path and search that too // TODO make it search subdirs subdir
        if os.path.isdir(path + filename):
            new_path = path + filename + "/"
            for file in os.listdir(new_path):
                if file.endswith(".bsp"): # don't include txt, ent etc
                    bsps.append(filename + "/" + file[:-4]) # for maps in 'maps/beta/' etc.
        else:
            if filename.endswith(".bsp"): # don't include txt, ent etc.
                bsps.append(filename[:-4]) # for maps in 'maps/'
                
    return bsps

def reload_maps():
    # remove map from database that has been deleted
    bsps = get_bsps()
    for map in map_memory:
        if map.name not in bsps:
            map_memory.remove(map)
            if map.name in already_seen:
                already_seen.remove(map.name)
            
    # add new bsp to database
    for bsp in bsps:
        found = False
        for map in map_memory:
            if bsp == map.name:
                found = True
        if not found:
            message = "Message not found"
            # open the map as text, ignore bits        
            with codecs.open(path + bsp + ".bsp", 'r', encoding='utf-8',
                                         errors='ignore') as myfile:
                        print(bsp)
                        lines = myfile.readlines()
                        for line in lines:
                            # search bsp for first message which is the worldspawn message (hopefully/usually)
                            if "message".lower() in line.lower():
                                tmp = line.split(' ', 1)[-1] [1:-2] # line is '"message" "<data>"', we want just data
                                print(tmp)
                                message = tmp.replace("\\n", " ") # strip linebreaks
                                break
            map_memory.append(MapData(bsp, message.strip('"'), tags=[])) # strip the fileextension from bsp
    

def make_database():
    bsps = get_bsps()            
    for bsp in bsps:
        # default if no message is set in worldspawn
        message = "Message not found"
        # open the map as text, ignore bits        
        with codecs.open(path + bsp + ".bsp", 'r', encoding='utf-8',
                                     errors='ignore') as myfile:
                    print(bsp)
                    lines = myfile.readlines()
                    for line in lines:
                        # search bsp for first message which is the worldspawn message (hopefully/usually)
                        if "message".lower() in line.lower():
                            tmp = line.split(' ', 1)[-1] [1:-2] # line is '"message" "<data>"', we want just data
                            print(tmp)
                            message = tmp.replace("\\n", " ") # strip linebreaks
                            break
        map_memory.append(MapData(bsp, message.strip('"'), tags=[])) # strip the fileextension from bsp
        with open(mapdata, "wb+") as mydata:
            pickle.dump(map_memory, mydata)
# great! this should be snappier than opening and closing bunch of files

def save():
    with open(savefile, 'wb+') as myfile:
	    pickle.dump(already_seen, myfile)
    message = "Already seen maps saved"
    with open(mapdata, "wb+") as mydata:
        pickle.dump(map_memory, mydata)
    return message
		
def load():
    global map_memory
    global already_seen
    with open(savefile, 'rb') as myfile:
        try:
            already_seen = pickle.load(myfile)
        except EOFError:
            pass
    message = "Already seen maps loaded"
    with open(mapdata, "rb") as mydata:
        map_memory = pickle.load(mydata)
    return message

if os.path.exists(mapdata):
    load() # load also the already seen maps (for "random")
else:
    make_database()


async def update_status():
	# creates a multiline code message of the sorting status // TODO i think this could be optimized (and prettified)
    sorting_progress = len(already_seen) / len(map_memory)
    junk = len(os.listdir(path + "junk/"))
    classic = len(os.listdir(path + "classic/"))
    pub = len(os.listdir(path + "pub/"))
    match = len(os.listdir(path + "match/"))
    fix = len(os.listdir(path + "fix/"))
    beta = len(os.listdir(path + "beta/"))
    total = junk + classic + pub + match + fix + beta
    
    # changes bots status "Playing with 2017 maps"
    activity = discord.Game(name="with {} maps in database".format(total))
    await client.change_presence(activity=activity)
    
    
    mapshot_junk = len(os.listdir(mapshot_path + "junk/"))
    mapshot_classic = len(os.listdir(mapshot_path + "classic/"))
    mapshot_pub = len(os.listdir(mapshot_path + "pub/"))
    mapshot_match = len(os.listdir(mapshot_path + "match/"))
    mapshot_fix = len(os.listdir(mapshot_path + "fix/"))
    mapshot_beta = len(os.listdir(mapshot_path + "beta/"))
    mapshot_total = mapshot_junk + mapshot_classic + mapshot_pub + mapshot_match + mapshot_fix + mapshot_beta
    
    msg = "```Sorting progress of all maps: {:.1%}\n".format(sorting_progress)
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
    found = False
    message = "Couldn't find the map you're uploading mapshot for"
    # check if the map user is trying to submit image for exists
    for map in map_memory:
        # without prefix eg. "beta/"
        if map.name.split('/')[-1] == keyword:
            found = True
            mapname = map.name
        # with prefix eg. "beta/"
        elif map.name == keyword:
            found = True
            mapname = map.name
        else:
            pass
		
    if found:
        # check if mapshot for the map already exists
        if not os.path.exists("/var/www/html/mapshots/{}.jpg".format(mapname)):
            await image[0].save("/var/www/html/mapshots/{}.jpg".format(mapname))
            message = "Image saved as {}.jpg".format(mapname)
        
        else:
            # ask user to confirm overwrite
            msg = await channel.send("{}.jpg already exists. Do you want to overwrite it?".format(keyword))
            await msg.add_reaction(emoji="✔️")
            await msg.add_reaction(emoji="❌")
            # wait until reaction from the user who executed commamd
            while True:
                res, user = await client.wait_for('reaction_add', 
                                       check=lambda reaction, user: reaction.emoji == '✔️' or '❌')
                if res.message.id == msg.id:
                    if user == author or user.id == whoa:
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
    """
    keyword: type: str
    reason: type: str
    author: type: discord.Member
    """
    found = False
    delete_this = None
    message = "Couldn't find the map you're trying to delete"
    
    # check if the map exists
    for map in map_memory:
        if map.name.split('/')[-1].lower() == keyword.lower():
            found = True
            delete_this = map
            mapname = map.name            
        else:
            pass
            
    if found:
        # ask user for confirmation
        msg = await channel.send("Do you really want to remove {}?".format(keyword))
        await msg.add_reaction(emoji="✔️")
        await msg.add_reaction(emoji="❌")
        # wait until confirmation from user who executed the command
        while True:
                res, user = await client.wait_for('reaction_add', 
                                       check=lambda reaction, user: reaction.emoji == '✔️' or '❌')
                if res.message.id == msg.id:
                    if user == author or user.id == whoa:
                        if res.emoji == "✔️":
                            os.remove("{}{}.bsp".format(path,mapname))
                            try:
                                os.remove("{}{}.jpg".format(mapshot_path, mapname))
                            except FileNotFoundError:
                                pass
                            map_memory.remove(delete_this)
                            try:
                                already_seen.remove(mapname)
                            except ValueError:
                                pass
                            await update_status()
                            with open('/home/aapo/deleted_maps.txt', 'a+') as myfile:
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
    for embed in await searcher.mapsearch(map_memory, keyword):
        await channel.send(embed=embed)
        
        
async def tagsearch(author, keyword):
    for embed in await searcher.mapsearch(map_memory, keyword, tags=True):
        await channel.send(embed=embed)

def choose_random_map(keyword=None):
    # choose a random map from maps dir, loop until get a map that is not already seen
    global already_seen
    map = None
    while True:
        # start all over again, if every map on the list has been seen   
        if len(already_seen) == len(map_memory):
            already_seen.clear()
        random_map = random.choice(map_memory)
        
        if keyword:
            if random_map.name.startswith(keyword):
                if random_map.name not in already_seen:
                    already_seen.append(random_map.name)
                    map = random_map
                    break
        else:  
            if random_map.name not in already_seen:
                if not random_map.name.startswith("beta"):
                    already_seen.append(random_map.name)
                    map = random_map
                    break
    
    print(map.name)
    print(map.message)         
    return map


async def mapinfo(author, keyword=None):
    """
    author: type: discord.Member
    keyword: type: str
    keyword: example: 'beta/greenhill_b1'
    """
    # search for the bsp, and look for worldspawn message
    tags = ""
    map = None
    if keyword:
        if keyword in ['pub', 'beta', 'fix', 'classic', 'inprogress', 'junk', 'match']:
            map = choose_random_map(keyword)
        else:
            for match in map_memory:
                if match.name.split('/')[-1] == keyword.lower():
                    map = match
    else:
        map = choose_random_map()
        
    if map:
        name = map.name
        message = map.message
        if len(map.tags) != 0:
            for tag in map.tags:
                tags += tag + " "
                    
        if map.name not in already_seen:
            already_seen.append(map.name)
    else:
        name = "No match"
        message = "Could not find the map. Try a different keyword"
        
    embed = await embedmaker.make_embed(name, message=message, tags=tags)
    await channel.send(embed=embed)                    
   
async def move_map(message, type):
    msg = message.content.split()
    try:
        keyword = msg[1]
        await channel.send(await mapmover.move_to(map_memory, already_seen, keyword, type))
    except IndexError:
        await channel.send("Error! No map name given!")

async def check_authorization(message):
    authorized = False
    # check if user is authorized
    if message.author.id in users:
        authorized = True
    
    return authorized
        
async def add_tags(message):
    msg = message.content.replace("!addtag ", "").split()
    found = False
    print
    for map in map_memory:
        if map.name.split('/')[-1] == msg[0]:
            found = True
            i = 1
            string = ""
            while True:
                if not msg[i].lower() in map.tags:
                    map.tags.append(msg[i].lower())
                    string += "`{}` ".format(msg[i])
                i += 1
                if i == len(msg):
                    break
            await channel.send("Added tags {}for {}".format(string, map.name.split('/')[-1]))
                    
    if not found:
        await channel.send("Error! Couldn't find the map")
        
async def delete_tags(message):
    msg = message.content.replace("!deltag ", "").split()
    found = False
    for map in map_memory:
        if map.name.split('/')[-1] == msg[0]:
            found = True
            i = 1
            string = ""
            while True:
                if msg[i].lower() in map.tags:
                    map.tags.remove(msg[i].lower())
                    string += "`{}` ".format(msg[i])
                i += 1
                if i == len(msg):
                    break
            await channel.send("Removed tags {}from {}".format(string, map.name.split('/')[-1]))
                    
    if not found:
        await channel.send("Error! Couldn't find the map")


async def wait_for_reaction(author, msg):
    numbers = ["1️⃣","2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    while True:
        res, user = await client.wait_for('reaction_add', 
                               check=lambda reaction, user: reaction.emoji == '♻️' or '❌')
        if user == author or user.id == whoa:
            if res.message.id == msg.id:
                if res.emoji == "❌":
                    await msg.delete()
                    break
                
            
async def server_status(author, ip, port):
    embed, playercount = embedmaker.make_status(ip, port, map_memory)
    msg = await channel.send(embed=embed)
    await msg.add_reaction(emoji="❌")
    await msg.add_reaction(emoji="♻️")
    future = asyncio.ensure_future(wait_for_reaction(author, msg))
    already_sent = False
    while not future.done():
        embed, results = embedmaker.make_status(ip, port, map_memory)
        await msg.edit(embed=embed)
        if results:
            if not already_sent:
                await msg.channel.send(embed=results)
                already_sent = True
        else:
            already_sent = False
            
        
        await asyncio.sleep(3)
    

async def broadcast(author):
    numbers = ["1️⃣","2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    servers, embed = embedmaker.get_servers()
    msg = await channel.send(embed=embed)
    await msg.add_reaction(emoji="❌")
    x = 0
    while x < len(servers):
        await msg.add_reaction(emoji=numbers[x])
        x += 1
    future = asyncio.ensure_future(wait_for_reaction(author, msg))
    while not future.done():
        res, user = await client.wait_for('reaction_add', 
                               check=lambda reaction, user: reaction.emoji == '♻️' or '❌')
        if user == author or user.id == whoa:
            if res.message.id == msg.id:
                if res.emoji in numbers:
                    index = numbers.index(res.emoji)
                    asyncio.create_task(server_status(author, servers[index][1], servers[index][2]))
   

async def wait_for_answer(msg, map):
    x = 0
    i = 0
    hint = ""
    while True:     
        message = await client.wait_for('message', check=lambda message: message.channel.id == msg.channel.id)
        x += 1
        if map in message.content.lower().split():
            await msg.channel.send("Correct! The answer was {}".format(map))
            await trivia()
            await asyncio.sleep(10)
            await msg.delete()
            break
        elif x == 50:
            await msg.channel.send("Wow nobody got it right? The answer was {}. Trivia has ended.".format(map))
            await msg.delete()
            break
        elif message.content.lower() == "pass":
            await msg.channel.send("The answer was {}. -10 points to {}".format(map, random.choice(["Gryffindor", "John Cena", "your mom", "you, you idiot", "Gandalf", "DirtyTaco", "whoa", " everyone", "James Bond", "Sub-Zero", "Spyro the Dragon", "BlueBalls Studios", "DPBot01"])))
            await msg.delete()
            await trivia()
            break
        elif message.content.lower() == "quit":
            await msg.channel.send("Trivia has ended!")
            await msg.delete()
            break
        elif message.content.lower() == "hint":
            if i < len(map):
                hint += map[i]
            i += 1
            embed = msg.embeds[0]
            embed.clear_fields()
            embed.add_field(name="Map name", value=hint, inline=False)
            await msg.edit(embed=embed)
                        
async def trivia():
    chosen_map = None
    while True:
        map = random.choice(map_memory)
        if map.name.split("/")[0] in ["classic", "match", "pub", "fix", "junk"]:
            chosen_map = map
            break
    if chosen_map:
        msg = await channel.send(embed=embedmaker.trivia(chosen_map.name))
        future = asyncio.ensure_future(wait_for_answer(msg, map.name.split("/")[-1]))



@client.event
async def on_message(message):
	
    author=message.author
    
    # don't respond to own messages
    if message.author == client.user:
        pass
        
    # don't respond to messages in wrong channel
    elif message.channel.id not in channels:
        pass
        
    else:
        
        global channel
        channel = message.channel
        
        if message.content.startswith('!tagsearch'):
            msg = message.content.split()
            try:
                keyword = msg[1]
                asyncio.create_task(tagsearch(author, keyword))
            except IndexError:
                await channel.send("Error! No keyword!")
        
        elif message.content.startswith('!mapsearch'):
            msg = message.content.split()
            try:
                keyword = msg[1]
                asyncio.create_task(mapsearch(author, keyword))
            except IndexError:
                await channel.send("Error! No keyword!")
                
        elif message.content.startswith('!mapinfo'):
            msg = message.content.split()
            keyword = None
            try:
                keyword = msg[1]
            except IndexError:
                pass
            asyncio.create_task(mapinfo(author, keyword))
            save()
            
        elif message.content.startswith("!help"):
            await channel.send(help_message)
           
        elif message.content.startswith("!load"):
            if message.author.id == whoa:
                await channel.send(load())
        elif message.content.startswith("!save"):
            if message.author.id == whoa:
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
            if await check_authorization(message):
                await move_map(message, type="junk")
                    
        elif message.content.startswith("!classic"):
            if await check_authorization(message):
                await move_map(message, type="classic")
        
        elif message.content.startswith("!fix"):
            if await check_authorization(message):
                await move_map(message, type="fix")
            
        elif message.content.startswith("!match"):
            if await check_authorization(message):
                await move_map(message, type="match")
            
        elif message.content.startswith("!pub"):
            if await check_authorization(message):
                await move_map(message, type="pub")
            
        
        elif message.content.startswith("!addtag"):
            if await check_authorization(message):
                await add_tags(message)
                save()
        
        elif message.content.startswith("!deltag"):
            if await check_authorization(message):
                await delete_tags(message)
                save()
            
            
        elif message.content.startswith("!reload"):
            if message.author.id == whoa: # whoa
                await channel.send("Reloading maps! Please hold...")
                reload_maps()
                await channel.send("Done!")
                await channel.send(await update_status())
                
            
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
            if message.author.id == whoa: # whoa
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
            if message.author.id == whoa:
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
            
        elif message.content.startswith("!scores"):
            msg = message.content.split()
            try:
                addr = msg[1]
                ip, port = addr.split(":")[0], int(addr.split(":")[-1])
                asyncio.create_task(server_status(author, ip, port))
                
            except IndexError:
                await channel.send("Error! You didn't give ip")
                
        elif message.content.startswith("!broadcast"):
            await broadcast(author)
        
        elif message.content.startswith("!trivia"):
            await trivia()
                                 

@client.event
async def on_ready():
    print('Success. Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await update_status()

client.run(TOKEN)