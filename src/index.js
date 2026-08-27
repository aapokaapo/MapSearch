const { Client, GatewayIntentBits, REST, Routes } = require('discord.js');
const { discord } = require('./config');
const { commandData, handleInteraction } = require('./commands');

async function registerCommands() {
  const rest = new REST({ version: '10' }).setToken(discord.token);

  if (discord.guildId) {
    await rest.put(Routes.applicationGuildCommands(discord.clientId, discord.guildId), { body: commandData });
    return;
  }

  await rest.put(Routes.applicationCommands(discord.clientId), { body: commandData });
}

async function start() {
  await registerCommands();

  const client = new Client({
    intents: [GatewayIntentBits.Guilds],
  });

  client.once('ready', () => {
    console.log(`Ready as ${client.user.tag}`);
  });

  client.on('interactionCreate', handleInteraction);
  await client.login(discord.token);
}

start().catch((error) => {
  console.error(error);
  process.exit(1);
});
