import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PBALL_ROOT = os.path.join(_BASE_DIR, "pball")
_ENV_FILE = os.path.join(_BASE_DIR, ".env")


def _load_env_file(path):
    if not os.path.exists(path):
        return

    with open(path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value


_load_env_file(_ENV_FILE)

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
base_url = "https://mapsearch.website"
public_mapshot_path = base_url + "/mapshots/"
local_mapshot_path = mapshot_path
trivia_path = os.path.join(_PBALL_ROOT, "trivia") + "/"
public_trivia_path = base_url + "/trivia/"
server_list = ""
public_topshot_path = base_url + "/topshots/"
public_map_path = base_url + "/maps/"

# Path where uploaded BSP/ZIP files are stored
upload_path = _PBALL_ROOT

# discord channel ids
channels = []

# discord user ids
users = []

# discord bot token
TOKEN = os.getenv("TOKEN", "")

admins = []
