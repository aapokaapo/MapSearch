const { db } = require('./client');

const mapSearchStmt = db.prepare(`
  SELECT DISTINCT m.map_path, m.map_name, m.message
  FROM maps m
  LEFT JOIN tags t ON t.map_id = m.map_id
  WHERE m.map_path LIKE @query OR m.message LIKE @query OR t.tag_name LIKE @query
  ORDER BY m.map_path COLLATE NOCASE
`);

const mapInfoStmt = db.prepare(`
  SELECT map_id, map_name, map_path, COALESCE(message, '') AS message
  FROM maps
  WHERE map_path = ? OR map_name = ?
  LIMIT 1
`);

const randomMapStmt = db.prepare(`
  SELECT map_id, map_name, map_path, COALESCE(message, '') AS message
  FROM maps
  ORDER BY RANDOM()
  LIMIT 1
`);

const randomMapByPrefixStmt = db.prepare(`
  SELECT map_id, map_name, map_path, COALESCE(message, '') AS message
  FROM maps
  WHERE map_path LIKE ?
  ORDER BY RANDOM()
  LIMIT 1
`);

const tagsByMapIdStmt = db.prepare('SELECT tag_name FROM tags WHERE map_id = ? ORDER BY tag_name COLLATE NOCASE');

const addTagStmt = db.prepare(`
  INSERT INTO tags(tag_name, map_id)
  SELECT ?, ?
  WHERE NOT EXISTS (SELECT 1 FROM tags WHERE tag_name = ? AND map_id = ?)
`);

const delTagStmt = db.prepare('DELETE FROM tags WHERE map_id = ? AND tag_name = ?');

const mapByKeywordStmt = db.prepare(`
  SELECT map_id, map_name, map_path, COALESCE(message, '') AS message
  FROM maps
  WHERE map_path = ? OR map_name = ?
  LIMIT 1
`);

const mapStatsStmt = db.prepare(`
  SELECT
    COUNT(*) FILTER (WHERE type = 'requiredfile' AND provided = 1) AS requiredfile_yes,
    COUNT(*) FILTER (WHERE type = 'requiredfile' AND provided = 0) AS requiredfile_no,
    COUNT(*) FILTER (WHERE type = 'texture' AND provided = 1) AS texture_yes,
    COUNT(*) FILTER (WHERE type = 'texture' AND provided = 0) AS texture_no,
    COUNT(*) FILTER (WHERE type = 'externalfile' AND provided = 1) AS externalfile_yes,
    COUNT(*) FILTER (WHERE type = 'externalfile' AND provided = 0) AS externalfile_no,
    COUNT(*) FILTER (WHERE type = 'linkedfile' AND provided = 1) AS linkedfile_yes,
    COUNT(*) FILTER (WHERE type = 'linkedfile' AND provided = 0) AS linkedfile_no
  FROM media_files
`);

const mapCountStmt = db.prepare('SELECT COUNT(*) AS c FROM maps');

const requiredFilesStmt = db.prepare(`
  SELECT f.path, f.type, f.provided
  FROM requirements r
  JOIN media_files f ON f.file_id = r.file_id
  JOIN maps m ON m.map_id = r.map_id
  WHERE m.map_path = ?
  ORDER BY f.type, f.path COLLATE NOCASE
`);

const mediaByTypeStmt = db.prepare('SELECT file_id, path FROM media_files WHERE type = ?');
const updateProvidedStmt = db.prepare('UPDATE media_files SET provided = ? WHERE file_id = ?');

const deleteMapTagsStmt = db.prepare('DELETE FROM tags WHERE map_id IN (SELECT map_id FROM maps WHERE map_path = ?)');
const deleteMapStmt = db.prepare('DELETE FROM maps WHERE map_path = ?');
const insertMapStmt = db.prepare('INSERT INTO maps(map_name, map_path, message) VALUES (?, ?, ?)');
const allMapPathsStmt = db.prepare('SELECT map_path FROM maps');

module.exports = {
  mapSearch(keyword) {
    return mapSearchStmt.all({ query: `%${keyword}%` });
  },
  findMap(keyword) {
    return mapByKeywordStmt.get(keyword, keyword) || null;
  },
  mapInfo(keyword) {
    if (!keyword) return randomMapStmt.get() || null;
    if (['beta', 'inprogress', 'tutorials'].includes(keyword)) {
      return randomMapByPrefixStmt.get(`${keyword}%`) || null;
    }
    return mapInfoStmt.get(keyword, keyword) || null;
  },
  mapTags(mapId) {
    return tagsByMapIdStmt.all(mapId).map((x) => x.tag_name);
  },
  addTags(mapId, tags) {
    const tx = db.transaction((input) => {
      for (const tag of input) addTagStmt.run(tag, mapId, tag, mapId);
    });
    tx(tags);
  },
  deleteTags(mapId, tags) {
    const tx = db.transaction((input) => {
      for (const tag of input) delTagStmt.run(mapId, tag);
    });
    tx(tags);
  },
  fileStats() {
    return {
      maps: mapCountStmt.get().c,
      ...mapStatsStmt.get(),
    };
  },
  requiredFiles(mapPath) {
    return requiredFilesStmt.all(mapPath);
  },
  allMediaByType(type) {
    return mediaByTypeStmt.all(type);
  },
  updateProvided(fileId, provided) {
    updateProvidedStmt.run(provided ? 1 : 0, fileId);
  },
  allMapPaths() {
    return allMapPathsStmt.all().map((r) => r.map_path);
  },
  deleteMap(path) {
    deleteMapTagsStmt.run(path);
    deleteMapStmt.run(path);
  },
  insertMap(mapPath, message) {
    const mapName = mapPath.split('/').pop();
    insertMapStmt.run(mapName, mapPath, message || 'Message not found');
  },
};
