import os
import codecs
import asyncio
import discord
import random
import config
import imagetool

TOKEN = config.token
channel_id = config.channel_id
client = discord.Client()


already_seen = []

map_memory = []

path = config.path

class MapData:
	def __init__(self, name, message):
		"""
		name: type: str
		message: type: str
		"""
		
		self.name = name
		self.message = message

def load_maps():
    map_memory.clear()
    bsps = []
    # default if no message is set in worldspawn
    message = "Message not found"
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
        # open the map as text, ignore bits        
        with codecs.open(path + bsp, 'r', encoding='utf-8',
                                     errors='ignore') as myfile:
                    print(bsp)
                    lines = myfile.readlines()
                    for line in lines:
                        # search bsp for first message which is the worldspawn message (hopefully/usually)
                        if "message".lower() in line.lower():
                            tmp= line.split(' ', 1)[-1] # strip quotation marks
                            message = tmp.replace("\\n", " ") # strip linebreaks
                            break
        map_memory.append(MapData(bsp[:-4], message))
# great! this should be snappier than opening and closing bunch of files
print("Mapdata loaded to memory!")
load_maps() # run on load

# TODO: make links work for betas and map based links

async def make_link(keyword):
    with open('/var/www/html/redirect/{}.html'.format(keyword), 'w') as myfile:
        html_str = """
        <html>
            <head>
                <title>HTML Meta Tag</title>
                    <meta http-equiv = "refresh" content = "2; url = ftp://otb-server.de/pub/Maps/{}.bsp" />
            </head>
            <body>
                <p>Redirecting to ftp OTB</p>
            </body>
        </html>
        """.format(keyword)
        myfile.write(html_str)


async def make_embed(keyword, maps=None, message=None):
    """
    keyword: type: str
    maps: type: list
    message: type: str
    """
    embed = discord.Embed(title="whoa's map search tool", description="Searching for: {}".format(keyword), color=0xfed900)
    if maps:
        hit_maps = ""
        if len(maps) != 0:
            for map in maps:
                hit_maps += map + " "
            embed.add_field(name="Results", value=hit_maps,
                            inline=False)
            embed.set_image(url="http://whoa.gq/gridshots/{}-grid.jpg".format(keyword))
            # DirtyTaco add code here for mapshots in grid, maps is a list of strings (mapnames)
      
    elif message:
        embed.add_field(name="Results", value=message.replace("\\n", " "),
                        inline=False)
        # await make_link(keyword)
        # embed.add_field(name="Download", value="[CLICK HERE TO DOWNLOAD](http://whoa.gq/redirect/{}.html)".format(keyword),
        #                inline=False)
        embed.set_image(url="http://whoa.gq/mapshots/{}.jpg".format(keyword))
        
    return embed
    


async def mapsearch(author, keyword):
    """
    author: type: discord.Author
    keyword: type: str
    """
	
    maps = []
    
    # create an empty embed and send it, edit it later
    embed = await make_embed(keyword, maps)
    channel = client.get_channel(channel_id)
    message = await channel.send(embed=embed)
    
    # search the maps and their messages in memory for keyword
    for map in map_memory:
        if keyword.lower() in map.message.lower():
            maps.append(map.name)
            
    # create a new embed with actual data and edit sent message
    # imagetool.imagetool(keyword, maps)
    embed = await make_embed(keyword, maps)
    await message.edit(embed=embed)
    
    # notify user that search is done
    await channel.send(author.mention)


async def mapinfo(author, keyword):
    """
    author: type: discord.Author
    keyword: type: str
    """
    # create an empty embed, edit it later
    embed = await make_embed(keyword)
    channel = client.get_channel(channel_id)
    bot_message = await channel.send(embed=embed)
    
    # search for the bsp, and look for worldspawn message
    message = None
    for map in map_memory:
        if map.name.lower() == keyword.lower():
            message = map.message
        elif map.name.replace('beta/', ' ').lower() == keyword.lower():
            message = map.message
        
    embed = await make_embed(keyword, message=message)
    await bot_message.edit(embed=embed)                    
        
        
async def random_map():
    # choose a random map from maps dir
    while True:
        if len(already_seen) == len(map_memory):
            already_seen.clear()
        random_map = random.choice(map_memory)
        if random_map not in already_seen:
            already_seen.append(random_map)
            break

    embed = await make_embed(random_map.name, random_map.message)
    channel = client.get_channel(channel_id)
    message = await channel.send(embed=embed) 


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
                asyncio.create_task(random_map())
                
        elif message.content.startswith("!reload"):
            await channel.send("Reloading maps! Please hold...")
            asyncio.create_task(load_maps())
            await channel.send("Map database reloaded. Currently {} maps in database".format(len(map_memory)))
        

@client.event
async def on_ready():
    channel = client.get_channel(channel_id)
    print('Success. Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    await channel.send("Hello world! I, the Digital Paintball 2 Map Database, have awaken. I currently have {} maps loaded!".format(len(map_memory)))

client.run(TOKEN)