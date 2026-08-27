# MapSearch (Node.js)

Modernized Discord bot for Digital Paintball 2 map discovery and metadata management.

## What changed

- Migrated the bot runtime from Python to Node.js.
- Replaced legacy `!chat` commands with Discord slash commands.
- Added structured command permissions (admin/user/public) through environment-based ID lists.
- Added safer command handling, explicit error responses, and central configuration validation.
- Kept SQLite as the source of truth (`sqlite_mapdata.db`).

## Supported slash commands

### Public
- `/help`
- `/mapsearch keyword`
- `/mapinfo [map]`
- `/files`
- `/requiredfiles map`

### Authorized users (`USER_IDS` or admins)
- `/addtag map tags`
- `/deltag map tags`
- `/mapshot map image`

### Admins (`ADMIN_IDS`)
- `/updatefiles`
- `/reloadmaps`
- `/reloadrequirements` *(currently disabled until a Node-compatible BSP dependency parser is integrated)*

## Setup

1. Install Node.js 20+.
2. Copy `.env.example` to `.env` and fill values.
3. Install dependencies:

```bash
npm install
```

4. Start the bot:

```bash
npm start
```

## Configuration

Environment variables are documented in `.env.example`.

Important values:
- `DISCORD_TOKEN`
- `DISCORD_CLIENT_ID`
- `DISCORD_GUILD_ID` (optional; recommended for faster command updates)
- `DATABASE_PATH`
- `CHANNEL_IDS`, `USER_IDS`, `ADMIN_IDS` (optional ACLs)
- `MAP_PATH`, `PBALL_PATH`, `TEXTURE_PATH`, `ENV_PATH`, `MAPSHOT_PATH` (needed for file-sync features)

## Notes

- Command registration happens automatically at startup.
- If `DISCORD_GUILD_ID` is set, commands are registered to that guild; otherwise globally.
- Python files are kept in the repository as legacy reference material during migration.
