// app.js — shared utilities

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(text || res.statusText);
  }
  return res.json();
}

function escHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function makeCard(map) {
  const BASE = window.BASE_URL || "";
  const card = document.createElement("div");
  card.className = "map-card";
  const imageUrl = `${BASE}/api/maps/${encodeURIComponent(map.map_path)}/image`;
  const tags = (map.tags || [])
    .map((t) => `<span class="tag">${escHtml(t.tag_name)}</span>`)
    .join("");
  card.innerHTML = `
    <img src="${imageUrl}" alt="${escHtml(map.map_name)}" loading="lazy" />
    <div class="card-body">
      <div class="card-title">${escHtml(map.map_name)}</div>
      <div class="card-msg">${escHtml((map.message || "").slice(0, 80))}${(map.message || "").length > 80 ? "…" : ""}</div>
      ${tags ? `<div class="card-tags">${tags}</div>` : ""}
    </div>
  `;
  return card;
}
