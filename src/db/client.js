const Database = require('better-sqlite3');
const { paths } = require('../config');

const db = new Database(paths.database);
db.pragma('journal_mode = WAL');

module.exports = { db };
