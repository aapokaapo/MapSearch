const fs = require('node:fs');
const path = require('node:path');
const AdmZip = require('adm-zip');
const { SlashCommandBuilder, EmbedBuilder } = require('discord.js');
const { discord, paths, publicUrls } = require('../config');
const db = require('../db/queries');
const { extractMapMessage, walkBsps, updateProvidedByType } = require('../utils/maps');

const commandData = [
  new SlashCommandBuilder().setName('help').setDescription('Show available commands'),
  new SlashCommandBuilder()
    .setName('mapsearch')
    .setDescription('Search maps by keyword in path, message, and tags')
    .addStringOption((o) => o.setName('keyword').setDescription('Search keyword').setRequired(true)),
  new SlashCommandBuilder()
    .setName('mapinfo')
    .setDescription('Show random or specific map information')
    .addStringOption((o) => o.setName('map').setDescription('Map path, name, or category (beta/tutorials/inprogress)')),
  new SlashCommandBuilder()
    .setName('addtag')
    .setDescription('Add one or more tags to a map')
    .addStringOption((o) => o.setName('map').setDescription('Map path or name').setRequired(true))
    .addStringOption((o) => o.setName('tags').setDescription('Space-separated tags').setRequired(true)),
  new SlashCommandBuilder()
    .setName('deltag')
    .setDescription('Delete one or more tags from a map')
    .addStringOption((o) => o.setName('map').setDescription('Map path or name').setRequired(true))
    .addStringOption((o) => o.setName('tags').setDescription('Space-separated tags').setRequired(true)),
  new SlashCommandBuilder()
    .setName('mapshot')
    .setDescription('Upload a mapshot for a map')
    .addStringOption((o) => o.setName('map').setDescription('Map path or name').setRequired(true))
    .addAttachmentOption((o) => o.setName('image').setDescription('Mapshot image').setRequired(true)),
  new SlashCommandBuilder()
    .setName('uploadmap')
    .setDescription('Upload a BSP map file or a game-structured ZIP package')
    .addAttachmentOption((o) => o.setName('file').setDescription('BSP or ZIP file').setRequired(true)),
  new SlashCommandBuilder().setName('files').setDescription('Show database file coverage stats'),
  new SlashCommandBuilder()
    .setName('requiredfiles')
    .setDescription('Show required files tracked for a map')
    .addStringOption((o) => o.setName('map').setDescription('Map path or name').setRequired(true)),
  new SlashCommandBuilder().setName('updatefiles').setDescription('Refresh provided flags for tracked media files'),
  new SlashCommandBuilder().setName('reloadmaps').setDescription('Rescan map BSP files and sync map table'),
  new SlashCommandBuilder()
    .setName('reloadrequirements')
    .setDescription('Legacy Python feature not yet ported (BSP dependency parser)')
    .addStringOption((o) => o.setName('map').setDescription('Map path or name (optional)')),
].map((x) => x.toJSON());

const splitField = (text, chunk = 1000) => {
  if (!text) return ['-'];
  const words = text.split(' ');
  const out = [];
  let line = '';
  for (const w of words) {
    if ((line + w).length > chunk) {
      out.push(line.trim());
      line = '';
    }
    line += `${w} `;
  }
  if (line.trim()) out.push(line.trim());
  return out;
};

const deny = (interaction, message) => interaction.reply({ content: message, ephemeral: true });
const isAdmin = (id) => discord.adminIds.has(id);
const isUser = (id) => isAdmin(id) || discord.userIds.has(id);

function isAllowedChannel(interaction) {
  return discord.channelIds.size === 0 || discord.channelIds.has(interaction.channelId);
}

async function handleMapSearch(interaction) {
  const keyword = interaction.options.getString('keyword', true).trim();
  const rows = db.mapSearch(keyword);
  if (!rows.length) {
    await interaction.reply({ content: `No maps matched \`${keyword}\`.`, ephemeral: true });
    return;
  }

  const grouped = new Map();
  for (const row of rows) {
    const prefix = row.map_path.includes('/') ? row.map_path.split('/')[0] : 'finished';
    const mapName = row.map_path.split('/').pop();
    const mapshotUrl = publicUrls.mapshot ? `${publicUrls.mapshot}${row.map_path}.jpg` : null;
    const printable = mapshotUrl ? `[${mapName}](${mapshotUrl})` : mapName;
    if (!grouped.has(prefix)) grouped.set(prefix, []);
    grouped.get(prefix).push(printable);
  }

  const embed = new EmbedBuilder().setTitle('MapSearch').setDescription(`Search: **${keyword}**`).setColor(0xfed900);
  for (const [category, maps] of grouped) {
    const chunks = splitField(maps.join(' '));
    chunks.forEach((part, index) => {
      embed.addFields({ name: index === 0 ? category : `${category} (cont.)`, value: part, inline: false });
    });
  }

  await interaction.reply({ embeds: [embed] });
}

async function handleMapInfo(interaction) {
  const keyword = interaction.options.getString('map')?.trim();
  const map = db.mapInfo(keyword);
  if (!map) {
    await interaction.reply({ content: 'Map not found.', ephemeral: true });
    return;
  }

  const tags = db.mapTags(map.map_id).join(' ') || '-';
  const embed = new EmbedBuilder()
    .setTitle(map.map_path)
    .setDescription(map.message || 'No map message')
    .setColor(0xfed900)
    .addFields({ name: 'Tags', value: tags, inline: false });

  if (publicUrls.map) {
    embed.addFields({ name: 'Download', value: `[CLICK HERE TO DOWNLOAD](${publicUrls.map}${map.map_path}.bsp)`, inline: false });
  }
  if (publicUrls.mapshot) embed.setImage(`${publicUrls.mapshot}${map.map_path}.jpg`);
  if (publicUrls.topshot) embed.setThumbnail(`${publicUrls.topshot}${map.map_path}.jpg`);

  await interaction.reply({ embeds: [embed] });
}

async function handleAddDelTag(interaction, mode) {
  if (!isUser(interaction.user.id)) return deny(interaction, 'Unauthorized user.');

  const mapQuery = interaction.options.getString('map', true).trim();
  const tags = interaction.options
    .getString('tags', true)
    .split(/\s+/)
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);

  if (!tags.length) return deny(interaction, 'No tags provided.');

  const map = db.findMap(mapQuery);
  if (!map) return deny(interaction, 'Map not found.');

  if (mode === 'add') db.addTags(map.map_id, tags);
  else db.deleteTags(map.map_id, tags);

  await interaction.reply(`${mode === 'add' ? 'Added' : 'Removed'} tags \`${tags.join(' ')}\` for **${map.map_path}**.`);
}

async function handleMapshot(interaction) {
  if (!isUser(interaction.user.id)) return deny(interaction, 'Unauthorized user.');

  const mapQuery = interaction.options.getString('map', true).trim();
  const attachment = interaction.options.getAttachment('image', true);
  const map = db.findMap(mapQuery);
  if (!map) return deny(interaction, 'Map not found.');
  if (!paths.mapshot) return deny(interaction, 'MAPSHOT_PATH is not configured.');

  const targetPath = path.join(paths.mapshot, `${map.map_path}.jpg`);
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });

  const response = await fetch(attachment.url);
  if (!response.ok) throw new Error(`Image download failed: ${response.status}`);
  const arrayBuffer = await response.arrayBuffer();
  fs.writeFileSync(targetPath, Buffer.from(arrayBuffer));

  await interaction.reply(`Saved mapshot as \`${map.map_path}.jpg\`.`);
}

async function handleFiles(interaction) {
  const stats = db.fileStats();
  await interaction.reply(
    [
      '**Database file entries:**',
      `Number of maps: ${stats.maps}`,
      `Required files: ${stats.requiredfile_yes} with ${stats.requiredfile_no} missing`,
      `Textures: ${stats.texture_yes} with ${stats.texture_no} missing`,
      `Models/skins/sounds: ${stats.externalfile_yes} with ${stats.externalfile_no} missing`,
      `Linked files: ${stats.linkedfile_yes} with ${stats.linkedfile_no} missing`,
    ].join('\n'),
  );
}

async function handleRequiredFiles(interaction) {
  const mapQuery = interaction.options.getString('map', true).trim();
  const map = db.findMap(mapQuery);
  if (!map) return deny(interaction, 'Map not found.');

  const files = db.requiredFiles(map.map_path);
  if (!files.length) {
    await interaction.reply(`No required files tracked for **${map.map_path}**.`);
    return;
  }

  const grouped = files.reduce((acc, row) => {
    if (!acc[row.type]) acc[row.type] = { ok: [], missing: [] };
    (row.provided ? acc[row.type].ok : acc[row.type].missing).push(row.path);
    return acc;
  }, {});

  const embed = new EmbedBuilder().setTitle(`Required files: ${map.map_path}`).setColor(0xfed900);
  for (const [type, value] of Object.entries(grouped)) {
    embed.addFields({ name: `${type} (provided)`, value: splitField(value.ok.join(' ')).join('\n') || '-', inline: false });
    if (value.missing.length) {
      embed.addFields({ name: `${type} (missing)`, value: splitField(value.missing.join(' ')).join('\n'), inline: false });
    }
  }

  await interaction.reply({ embeds: [embed] });
}

async function refreshProvidedFlags() {
  const mediaTypes = ['mapshot', 'texture', 'sky', 'requiredfile', 'externalfile', 'linkedfile'];
  for (const type of mediaTypes) {
    for (const row of db.allMediaByType(type)) {
      const provided = updateProvidedByType(row, type, paths);
      db.updateProvided(row.file_id, provided);
    }
  }
}

async function handleUpdateFiles(interaction) {
  if (!isAdmin(interaction.user.id)) return deny(interaction, 'Admin only command.');
  await interaction.deferReply();
  refreshProvidedFlags();
  await interaction.editReply('Done updating file availability.');
}

async function handleReloadMaps(interaction) {
  if (!isAdmin(interaction.user.id)) return deny(interaction, 'Admin only command.');
  if (!paths.map) return deny(interaction, 'MAP_PATH is not configured.');

  await interaction.deferReply();
  const { inserted, removed } = syncMapsFromFs();
  await interaction.editReply(`Map sync complete. Added ${inserted}, removed ${removed}.`);
}

async function handleReloadRequirements(interaction) {
  if (!isAdmin(interaction.user.id)) return deny(interaction, 'Admin only command.');
  await interaction.reply(
    'This legacy feature depends on the Python BSP parser (Q2BSP/MD2/SKM) and is intentionally disabled in the Node.js rewrite until a Node parser is integrated.',
  );
}

function syncMapsFromFs() {
  const fsMaps = new Set(walkBsps(paths.map));
  const dbMaps = new Set(db.allMapPaths());

  for (const mapPath of dbMaps) {
    if (!fsMaps.has(mapPath)) db.deleteMap(mapPath);
  }

  let inserted = 0;
  for (const mapPath of fsMaps) {
    if (dbMaps.has(mapPath)) continue;
    const msg = extractMapMessage(path.join(paths.map, `${mapPath}.bsp`));
    db.insertMap(mapPath, msg);
    inserted += 1;
  }

  return { inserted, removed: [...dbMaps].filter((m) => !fsMaps.has(m)).length };
}

function normalizeZipEntry(entryName) {
  return entryName.replace(/\\/g, '/').replace(/^\/+/, '');
}

function isUnsafePath(relPath) {
  return relPath.split('/').some((segment) => segment === '..');
}

async function handleUploadMap(interaction) {
  if (!isAdmin(interaction.user.id)) return deny(interaction, 'Admin only command.');

  const attachment = interaction.options.getAttachment('file', true);
  const originalName = String(attachment.name || '').trim();
  const lowerName = originalName.toLowerCase();
  if (!lowerName.endsWith('.bsp') && !lowerName.endsWith('.zip')) {
    return deny(interaction, 'Only `.bsp` and `.zip` uploads are supported.');
  }
  if (lowerName.endsWith('.bsp') && !paths.map) return deny(interaction, 'MAP_PATH is not configured.');
  if (lowerName.endsWith('.zip') && !paths.pball) return deny(interaction, 'PBALL_PATH is not configured.');

  await interaction.deferReply();
  const response = await fetch(attachment.url);
  if (!response.ok) throw new Error(`Upload download failed: ${response.status}`);
  const fileBuffer = Buffer.from(await response.arrayBuffer());

  if (lowerName.endsWith('.bsp')) {
    const safeName = path.basename(originalName);
    const targetPath = path.join(paths.map, safeName);
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, fileBuffer);
  } else {
    const zip = new AdmZip(fileBuffer);
    const entries = zip.getEntries();
    const allowedRoots = new Set(['maps', 'textures', 'models', 'sound', 'pics', 'env', 'scripts', 'players']);
    const baseDir = path.resolve(paths.pball);

    let totalUncompressed = 0;
    let hasBsp = false;
    for (const entry of entries) {
      if (entry.isDirectory) continue;
      const relPath = normalizeZipEntry(entry.entryName);
      if (!relPath || isUnsafePath(relPath)) throw new Error('ZIP contains an unsafe file path.');

      const rootDir = relPath.split('/')[0].toLowerCase();
      if (!allowedRoots.has(rootDir)) throw new Error(`ZIP contains unsupported root directory: ${rootDir}`);
      if (rootDir === 'maps' && relPath.toLowerCase().endsWith('.bsp')) hasBsp = true;

      totalUncompressed += entry.header.size;
      if (totalUncompressed > 1024 * 1024 * 1024) throw new Error('ZIP exceeds 1GB uncompressed size limit.');

      const targetPath = path.resolve(path.join(baseDir, relPath));
      if (!targetPath.startsWith(`${baseDir}${path.sep}`)) throw new Error('ZIP extraction path escaped base directory.');

      fs.mkdirSync(path.dirname(targetPath), { recursive: true });
      fs.writeFileSync(targetPath, entry.getData());
    }

    if (!hasBsp) throw new Error('ZIP must include at least one `.bsp` file under `maps/`.');
  }

  let syncMessage = '';
  if (paths.map) {
    const { inserted, removed } = syncMapsFromFs();
    syncMessage = ` Map sync: added ${inserted}, removed ${removed}.`;
  }

  await interaction.editReply(`Upload complete for \`${originalName}\`.${syncMessage}`);
}

async function handleHelp(interaction) {
  const lines = [
    '/mapsearch keyword',
    '/mapinfo [map]',
    '/requiredfiles map',
    '/files',
    '/addtag map tags (authorized users)',
    '/deltag map tags (authorized users)',
    '/mapshot map image (authorized users)',
    '/uploadmap file (admins; accepts .bsp or .zip)',
    '/updatefiles (admins)',
    '/reloadmaps (admins)',
    '/reloadrequirements (admins; currently disabled)',
  ];
  await interaction.reply(lines.join('\n'));
}

const handlers = {
  help: handleHelp,
  mapsearch: handleMapSearch,
  mapinfo: handleMapInfo,
  addtag: (i) => handleAddDelTag(i, 'add'),
  deltag: (i) => handleAddDelTag(i, 'del'),
  mapshot: handleMapshot,
  files: handleFiles,
  requiredfiles: handleRequiredFiles,
  uploadmap: handleUploadMap,
  updatefiles: handleUpdateFiles,
  reloadmaps: handleReloadMaps,
  reloadrequirements: handleReloadRequirements,
};

async function handleInteraction(interaction) {
  if (!interaction.isChatInputCommand()) return;
  if (!isAllowedChannel(interaction)) {
    await deny(interaction, 'This command is not enabled in this channel.');
    return;
  }

  const handler = handlers[interaction.commandName];
  if (!handler) {
    await deny(interaction, 'Unknown command.');
    return;
  }

  try {
    await handler(interaction);
  } catch (err) {
    const message = `Command failed: ${err.message}`;
    if (interaction.deferred || interaction.replied) await interaction.editReply(message);
    else await deny(interaction, message);
  }
}

module.exports = {
  commandData,
  handleInteraction,
};
