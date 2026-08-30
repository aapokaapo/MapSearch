# MapSearch

Discord bot and web application for Digital Paintball 2 map discovery and metadata management — built with **py-cord** slash commands and a **FastAPI** backend with a browser-based frontend.

## Slash commands

### Public
- `/mapsearch keyword` — search maps by name, message or tag
- `/mapinfo [map]` — show map info (or random if omitted); supports `beta`, `inprogress`, `tutorials` as sub-directory keywords
- `/files` — database file statistics
- `/requiredfiles map` — show required files from the database for a map
- `/requirements map` — compute required files live from the BSP
- `/broadcast_servers` — list populated game servers
- `/scores address` — broadcast a server by `ip:port`
- `/trivia_game` — start a map trivia game

### Authorized users
- `/addtag map tags` — add space-separated tags to a map
- `/deltag map tags` — remove tags from a map
- `/mapshot map image` — upload a mapshot image

### Admins
- `/upload_map file [subfolder] [map_name]` — upload a `.bsp`, `.zip`, or `.jpg`/`.jpeg` mapshot file
- `/updatefiles` — update which required files are provided by the server
- `/reloadmaps` — sync the map database with the file system
- `/reloadrequirements [map]` — reload the requirements table (optionally for one map)
- `/op member` — grant user permissions to a member
- `/deop member` — revoke user permissions from a member

## Web API

The FastAPI backend (`api.py`) exposes a REST API and serves the web frontend.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/maps` | List all maps |
| `GET` | `/api/maps/search?keyword=…` | Search maps by name, path, message, or tag |
| `GET` | `/api/maps/{map_path}` | Get info for a specific map |
| `GET` | `/api/maps/{map_path}/image` | Redirect to mapshot or topshot image (auto-generates topshot fallback) |
| `GET` | `/api/maps/{map_path}/topshot` | Always return/create topshot image for a map |
| `GET` | `/api/maps/{map_path}/files` | List required files for a map |
| `GET` | `/api/maps/{map_path}/download` | Download a ZIP archive of the map |
| `GET` | `/api/maps/{map_path}/bsp` | Stream the raw BSP file |
| `POST` | `/api/export-bsp?map_name=…` | Generate a topshot radar image |

## Web Frontend

The `frontend/` directory contains a static browser UI served automatically by the API:

- **`index.html`** — search page; query maps and browse results as cards
- **`map.html`** — map detail page; shows metadata, mapshot, and download link
- **`viewer.html`** — in-browser 3-D BSP viewer

## Setup

1. Install Python 3.10+ and pip.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Initialize the git submodule dependency:

```bash
git submodule update --init --recursive
```

4. Copy `.env.example` to `.env` and add the Discord bot token there.
5. Edit `config.py` and fill in all paths and IDs.
6. Start the bot:

```bash
python MapSearch.py
```

7. *(Optional)* Start the web API:

```bash
uvicorn api:app --host 127.0.0.1 --port 8080
```

## Configuration (`config.py`)

| Variable | Description |
|---|---|
| `pball_path` | Root path of the game installation (`pball/` subfolder) |
| `map_path` | Path to the `maps/` directory on the server |
| `mapshot_path` | Local path for mapshot images |
| `topshot_path` | Local path for topshot radar images |
| `database_path` | Path to the SQLite database file |
| `upload_path` | Destination for uploaded BSP/ZIP files |
| `base_url` | Public base URL (e.g. `https://mapsearch.website`) |
| `public_mapshot_path` | Public URL prefix for mapshot images |
| `public_topshot_path` | Public URL prefix for topshot images |
| `public_map_path` | Public URL prefix for map downloads |
| `admins` | List of Discord admin user IDs |

## Deployment

The production site (`mapsearch.website`) is served by **Caddy**. Place the following block in your `Caddyfile`:

```caddy
mapsearch.website {
    route /api/* {
        reverse_proxy localhost:8080
    }
    root * /var/www/html
    @notStatic not file
    reverse_proxy @notStatic localhost:4000
    file_server
    php_fastcgi unix//run/php/php8.2-fpm.sock
}
```

| Component | Port / Socket | Description |
|---|---|---|
| FastAPI (`api.py`) | `localhost:8080` | REST API — handles all `/api/*` requests |
| Secondary service | `localhost:4000` | Handles dynamic non-static routes |
| Static files | `/var/www/html` | Frontend files (`frontend/`) deployed here |
| PHP | `/run/php/php8.2-fpm.sock` | PHP scripts served via FastCGI |

Deploy the `frontend/` directory contents to `/var/www/html` and start the API with:

```bash
uvicorn api:app --host 127.0.0.1 --port 8080
```

## Environment (`.env`)

| Variable | Description |
|---|---|
| `TOKEN` | Discord bot token |

## Upload format

The `/upload_map` command accepts:
- **`.bsp`** — placed under `{upload_path}/maps/[subfolder]/`; filenames ending in `_betaN` or `_bN` are automatically stored under `maps/beta/`
- **`.zip`** — extracted to `upload_path`; must contain a `maps/` directory at the archive root with at least one `.bsp` file inside. BSP filenames ending in `_betaN` or `_bN` are automatically stored under `maps/beta/`. The zip must not contain absolute paths or `..` components.
- **`.jpg` / `.jpeg`** — stored as a mapshot in `{mapshot_path}` if a matching BSP already exists. The BSP is matched by the image filename stem or by the optional `map_name` argument when provided.
