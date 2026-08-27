# MapSearch

Discord bot for Digital Paintball 2 map discovery and metadata management — built with **py-cord** and slash commands.

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
- `/upload_map file [subfolder]` — upload a `.bsp` or `.zip` file with the expected game file structure
- `/updatefiles` — update which required files are provided by the server
- `/reloadmaps` — sync the map database with the file system
- `/reloadrequirements [map]` — reload the requirements table (optionally for one map)
- `/op member` — grant user permissions to a member
- `/deop member` — revoke user permissions from a member

## Setup

1. Install Python 3.10+ and pip.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Edit `config.py` and fill in all paths and IDs.
4. Start the bot:

```bash
python MapSearch.py
```

## Configuration (`config.py`)

| Variable | Description |
|---|---|
| `TOKEN` | Discord bot token |
| `channels` | List of allowed Discord channel IDs |
| `users` | List of Discord user IDs with elevated permissions |
| `admins` | List of Discord admin user IDs |
| `database_path` | Path to the SQLite database file |
| `map_path` | Path to the `maps/` directory on the server |
| `pball_path` | Root path of the game installation |
| `upload_path` | Destination for uploaded BSP/ZIP files |
| `mapshot_path` / `public_mapshot_path` | Local and public URL paths for mapshots |
| `texture_path`, `env_path` | Paths to textures and sky images |

## Upload format

The `/upload_map` command accepts:
- **`.bsp`** — placed directly under `{upload_path}/maps/[subfolder]/`
- **`.zip`** — extracted to `upload_path`; must contain a `maps/` directory at the archive root with at least one `.bsp` file inside. The zip must not contain absolute paths or `..` components.

