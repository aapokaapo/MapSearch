const path = require('node:path');
const dotenv = require('dotenv');

dotenv.config();

const asIdSet = (value) =>
  new Set(
    String(value || '')
      .split(',')
      .map((v) => v.trim())
      .filter(Boolean),
  );

const required = ['DISCORD_TOKEN', 'DISCORD_CLIENT_ID'];
const missing = required.filter((key) => !process.env[key]);
if (missing.length) {
  throw new Error(`Missing required environment variables: ${missing.join(', ')}`);
}

module.exports = {
  discord: {
    token: process.env.DISCORD_TOKEN,
    clientId: process.env.DISCORD_CLIENT_ID,
    guildId: process.env.DISCORD_GUILD_ID || null,
    channelIds: asIdSet(process.env.CHANNEL_IDS),
    userIds: asIdSet(process.env.USER_IDS),
    adminIds: asIdSet(process.env.ADMIN_IDS),
  },
  paths: {
    database: path.resolve(process.cwd(), process.env.DATABASE_PATH || './sqlite_mapdata.db'),
    map: process.env.MAP_PATH || '',
    mapshot: process.env.MAPSHOT_PATH || '',
    pball: process.env.PBALL_PATH || '',
    texture: process.env.TEXTURE_PATH || '',
    env: process.env.ENV_PATH || '',
    topshot: process.env.TOPSHOT_PATH || '',
  },
  publicUrls: {
    mapshot: process.env.PUBLIC_MAPSHOT_URL || '',
    topshot: process.env.PUBLIC_TOPSHOT_URL || '',
    map: process.env.PUBLIC_MAP_URL || '',
  },
};
