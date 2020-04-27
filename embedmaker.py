import discord
import serverinfo
from operator import itemgetter, attrgetter


async def split_string(maps_string):
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
            if last_map in string:
                break
            string = ""
            
    # return a list of strings
    return strings
	    

async def make_embed(keyword, maps=None, message=None, tags=None):
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
                    strings = await split_string(maps[category])                    
                    last_string = strings[-1]
                    
                # cycle through all the strings, embed can fit 5 fields max (6000 chars max, 5 * 1024 = 5120, but just to be sure...)
                x = 0
                while True:
                    if i <= 5:
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
                            break
                    # if embed has 5 fields, append current and make an empty one
                    else:
                        embeds.append(embed)
                        embed = discord.Embed(title="whoa's map search tool", description="Searching for: {}".format(keyword), color=0xfed900)
                        i = 1
                        
        # when done with all strings, append the last embed
        embeds.append(embed)
        # returns a list if embeds
        return embeds
      
    elif message:
        # if message is not empty
        if message == "":
            message = "No map message"
        embed.add_field(name="Results", value=message,
                        inline=False)
        if tags:
            embed.add_field(name="Tags", value=tags, inline=False)
        if keyword != "No match":
            # add download link
            embed.add_field(name="Download", value="[CLICK HERE TO DOWNLOAD](http://whoa.ml/maps/{}.bsp)".format(keyword),
                            inline=False)
            # add a mapshot
            embed.set_image(url="http://whoa.ml/mapshots/{}.jpg".format(keyword))
            # add thumbnail
            embed.set_thumbnail(url="http://whoa.ml/topshots/{}.png".format(keyword))
            embed.set_footer(text="Powered by Toolwut's BSP images", icon_url="https://www.zwodnik.com/media/cache/c3/b9/c3b94c5c0934232730a21baa3bddcb1c.png")
        # returns a single embed
        return embed


def make_results(status, map_memory, teams=None, winner=None):
    embed = discord.Embed(title="whoa's match broadcaster", description="The map has ended!", color=0xfed900)
    winner_team = ""
    scores = status.get("_scores").split()
    winner_team = "Tie"
    for team in scores:
        for opponent in scores:
            if opponent != team:
                if int(team.split(":")[-1]) > int(opponent.split(":")[-1]):
                    winner_team = team
    string = ""
    if teams:
        for team in scores:
            string += "**{}**\n{}\n".format(team, teams[team.split(":")[0]])
            
        embed.add_field(name="Winner team: {}".format(winner_team.split(":")[0]), value=string, inline=False)
        embed.add_field(name="Map", value=status.get("mapname").split("/")[-1], inline=False)
        for map in map_memory:
            if map.name.split('/')[-1] == status.get("mapname").split("/")[-1]:
                embed.set_thumbnail(url="http://whoa.ml/mapshots/{}.jpg".format(map.name))
    
    if winner:
        embed.add_field(name="Winner: {}".format(winner.name), value="With {} kills, {} wins the map!".format(winner.score, winner.name), inline=False)
        for player in sorted(status.get("players"), key=attrgetter('score'), reverse=True):
            string += "{} - {} kills\n".format(player.name, player.score)
        embed.add_field(name="Scoreboard", value=string, inline=False)
            
    return embed

def make_status(ip, port, map_memory=None):
    teams = {"Red": "", "Blue": "", "Yellow": "", "Purple": "", "Observer": "", "Unknown": ""}
    status = serverinfo.status(ip, port)
    embed = discord.Embed(title="whoa's match broadcaster", description="Broadcasting: {}".format(status.get("hostname")), color=0xfed900)
    if status.get("_scores"):
        embed.add_field(name="Scores", value="{}".format(status.get("_scores")),
                            inline=False)
    else:
        if status.get("players"):
            scoring_leader = sorted(status.get("players"), key=attrgetter('score'), reverse=True)[0]
            embed.add_field(name="Scores", value="{} is in the lead with {} kills".format(scoring_leader.name, scoring_leader.score),
                                inline=False)
    embed.add_field(name="Map", value="{} - Time: {}".format(status.get("mapname"), status.get("TimeLeft")), inline=False)
    if status.get("mapname"):
        for map in map_memory:
            if map.name.split('/')[-1] == status.get("mapname").split("/")[-1]:
                embed.set_thumbnail(url="http://whoa.ml/mapshots/{}.jpg".format(map.name))
    if status.get("players"):
        playercount = len(status.get("players"))
        for player in status.get("players"):
            teams[player.team] += "{} - kills: {}\n".format(player.name, str(player.score))
        for team in teams:
            if teams[team]:
                embed.add_field(name=team, value=teams[team], inline=True)
                
    
    results = None
    if status.get("_scores"):
        for team in status.get("_scores").split():
            if int(team.split(":")[-1]) >= int(status.get("fraglimit")):
                results = make_results(status, map_memory, teams=teams)
            elif status.get("TimeLeft") == "0:00":
                results = make_results(status, map_memory, teams=teams)
    else:
        if status.get("players"):
            scores = sorted(status.get("players"), key=attrgetter('score'), reverse=True)
            if scores[0].score >= int(status.get("fraglimit")):
                results = make_results(status, map_memory, winner=scores[0])
            elif status.get("TimeLeft") == "0:00":
                results = make_results(status, map_memory, winner=scores[0])
        
    return embed, results
    
    
def get_servers():
    servers = serverinfo.get_serverlist()
    embed = discord.Embed(title="whoa's broadcaster serverlist", description="Currently {} servers with players".format(len(servers)), color=0xfed900)
    x = 1
    for server in servers:
        embed.add_field(name="Server #{}".format(x), value="**{}**\n{}:{}".format(server[0].get("hostname"), server[1], server[2]), inline=False)
        x += 1
    
    return servers, embed
    
    
def trivia(map):
    embed = discord.Embed(title="whoa's map trivia", description="What's this map?", color=0xfed900)
    embed.set_image(url="http://whoa.ml/topshots/{}.jpg".format(map))
    embed.set_footer(text="Powered by Toolwut's BSP images", icon_url="https://www.zwodnik.com/media/cache/c3/b9/c3b94c5c0934232730a21baa3bddcb1c.png")
    
    return embed
    
    