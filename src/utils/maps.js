const fs = require('node:fs');
const path = require('node:path');

const imageExts = ['.png', '.jpg', '.tga', '.pcx', '.wal'];

const existsAny = (prefix, exts) => exts.some((ext) => fs.existsSync(`${prefix}${ext}`));

function extractMapMessage(filePath) {
  try {
    const text = fs.readFileSync(filePath, 'latin1');
    const match = text.match(/"message"\s+"([^"]+)"/i);
    return match ? match[1].replace(/\\n/g, ' ') : 'Message not found';
  } catch {
    return 'Message not found';
  }
}

function walkBsps(rootPath, rel = '') {
  const current = path.join(rootPath, rel);
  const entries = fs.readdirSync(current, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    if (entry.name.startsWith('.')) continue;
    if (entry.isDirectory()) {
      out.push(...walkBsps(rootPath, path.join(rel, entry.name)));
      continue;
    }
    if (entry.isFile() && entry.name.toLowerCase().endsWith('.bsp')) {
      out.push(path.join(rel, entry.name.slice(0, -4)).replace(/\\/g, '/'));
    }
  }
  return out;
}

function updateProvidedByType(row, type, paths) {
  const relPath = row.path;
  switch (type) {
    case 'mapshot':
      return existsAny(path.join(paths.pball, relPath), imageExts);
    case 'texture':
      return existsAny(path.join(paths.texture, relPath), imageExts);
    case 'sky':
      return existsAny(path.join(paths.env, relPath), imageExts);
    case 'requiredfile':
      return fs.existsSync(path.join(paths.pball, relPath));
    case 'externalfile':
      return (
        existsAny(path.join(paths.pball, relPath.replace(/\.(md2|skm)$/i, '')), ['.md2', '.skm']) ||
        existsAny(path.join(paths.pball, relPath), ['', ...imageExts]) ||
        fs.existsSync(path.join(paths.pball, 'sound', relPath))
      );
    case 'linkedfile': {
      const noExt = relPath.split('.').slice(0, -1).join('.') || relPath;
      return existsAny(path.join(paths.pball, relPath), ['', '.skp']) || existsAny(path.join(paths.pball, noExt), ['', ...imageExts]);
    }
    default:
      return false;
  }
}

module.exports = {
  extractMapMessage,
  walkBsps,
  updateProvidedByType,
};
