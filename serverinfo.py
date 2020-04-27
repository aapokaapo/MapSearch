from socket import socket, AF_INET, SOCK_DGRAM
from parse import decode_ingame_text as decoder
import urllib

"""
ÿÿÿÿprint
\py\!0
\pr\!2!3
\po\!1
\sv_certificated\0
\mapname\beta/twilight2_preview
\TimeLeft\20:00
\_scores\Red:0 Blue:0 
\gamename\Digital Paint Paintball 2 v1.932(188)
\gameversion\DPPB2 v1.932(188)
\sv_login\1
\needpass\0
\gamedate\Aug 20 2019
\elim\30
\location\Germany - Europe
\e-mail\richard@crackgaming.de
\admin\helixx, Richar:D
\hostname\cRack' the Siege   
\protocol\34
\timelimit\20
\fraglimit\50
\version\2.00 i386 Mar  9 2020 Linux (43)
\gamedir\pball
\game\pball
\maxclients\16
0 26 "noname"
0 15 "ic3y"
0 40 "google"
0 77 "redguy"
"""
class PlayerInfo:
    def __init__(self, name, score, id, team="Unknown"):
        self.name = name
        self.score = score
        self.id = id
        self.team = team

def parse_status(data=None):
    
    status = {}
    players = []
    teams = ["pp", "pb", "pr", "py", "po"]
    
    if data:
        data = data.replace("ÿÿÿÿprint", "")
        i = 0
        for player in data.splitlines()[2:]:
            player_data = player.split()
            try:
                score = int(player_data[0])
            except ValueError:
                score = 0
            players.append(PlayerInfo(name=decoder(player_data[-1][1:-1]), score=score, id=i))
            i += 1
                
        data = data.splitlines()[1]
        data = data.split("\\")
        x = 1
        while x < len(data):
            if data[x] in teams:
                status[data[x]] = data[x+1].split('!')[1:]
            else:
                status[data[x]] = data[x+1]
            x += 2
        
        
        colors = {
                    'Red': status.get("pr"),
                    'Blue': status.get("pb"),
                    'Yellow': status.get("py"),
                    'Purple': status.get("pp"),
                    'Observer': status.get("po")
                    }
        for player in players:
            for color in colors:
                if colors[color]:
                    for id in colors.get(color):
                        if str(player.id) == id:
                            player.team = color
                
        status["players"] = players
    
    return status
        

    
def status(ip, port):
    """
    Execute status query.

    :return: Status string
    :rtype: str
    """
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.connect((ip, port))
    sock.settimeout(5)
    sock.send(b'\xFF\xFF\xFF\xFFstatus\n')
    try:
        data = sock.recv(2048).decode('latin-1')
    except:
        data = None
    return parse_status(data)
    sock.close
    
def get_serverlist():
    url = "https://otb-server.de/serverlist.txt"
    file = urllib.request.urlopen(url)
    servers = []
    for line in file:
        if line.decode("utf-8")[0].isdigit():
            ip, port = line.decode("utf-8").split(":")[0], int(line.decode("utf-8").split(":")[1])
            data = status(ip, port)
            if data.get("players"):
                servers.append([data, ip, port])
                
    return servers
    
