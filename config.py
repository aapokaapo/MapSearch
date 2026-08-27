import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PBALL_ROOT = "/var/www/html/pball"
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
topshot_path = "/var/www/html/topshots/"
mapshot_path = os.path.join(_PBALL_ROOT, "pics", "mapshots") + "/"
map_path = os.path.join(_PBALL_ROOT, "maps") + "/"
database_path = os.path.join(_BASE_DIR, "sqlite_mapdata.db")

base_url = "https://mapsearch.website"
public_mapshot_path = base_url + "/mapshots/"
public_topshot_path = base_url + "/topshots/"
public_map_path = base_url + "/maps/"

# Path where uploaded BSP/ZIP files are stored (root of the pball game directory)
upload_path = _PBALL_ROOT

# discord bot token
TOKEN = os.getenv("TOKEN", "")

admins = []
