import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PBALL_ROOT = os.path.join(_BASE_DIR, "pball")

pball_path = _PBALL_ROOT + "/"
topshot_path = os.path.join(_PBALL_ROOT, "topshots") + "/"
mapshot_path = os.path.join(_PBALL_ROOT, "mapshots") + "/"
model_path = os.path.join(_PBALL_ROOT, "models") + "/"
texture_path = os.path.join(_PBALL_ROOT, "textures") + "/"
env_path = os.path.join(_PBALL_ROOT, "env") + "/"
script_path = os.path.join(_PBALL_ROOT, "scripts") + "/"
map_path = os.path.join(_PBALL_ROOT, "maps") + "/"
sound_path = os.path.join(_PBALL_ROOT, "sound") + "/"
database_path = os.path.join(_BASE_DIR, "sqlite_mapdata.db")
public_mapshot_path = "/mapshots/"
local_mapshot_path = mapshot_path
trivia_path = os.path.join(_PBALL_ROOT, "trivia") + "/"
public_trivia_path = "/trivia/"
server_list = ""
public_topshot_path = "/topshots/"
public_map_path = "/maps/"

# Path where uploaded BSP/ZIP files are stored
upload_path = _PBALL_ROOT

# discord channel ids
channels = []

# discord user ids
users = []

# discord bot token
TOKEN = ""

admins = []
