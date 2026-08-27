// viewer.js — Three.js BSP 3D viewer
// Fetches OBJ geometry from the server and renders it.

async function initViewer(base, mapPath) {
  const canvas = document.getElementById("viewer-canvas");
  const overlay = document.getElementById("loading-overlay");
  const loadMsg = document.getElementById("loading-msg");

  function showError(msg) {
    if (overlay) overlay.classList.add("hidden");
    const el = document.getElementById("error-msg");
    const txt = document.getElementById("error-text");
    if (el && txt) { txt.textContent = msg; el.classList.add("visible"); }
    else { const p = document.createElement("p"); p.style.color = "var(--danger)"; p.textContent = msg; canvas.parentElement.appendChild(p); }
  }

  // ── Three.js setup ──────────────────────────────────────────────
  let renderer, scene, camera, controls;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(devicePixelRatio);
    renderer.setClearColor(0x080a0f);

    scene = new THREE.Scene();
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(1, 2, 1);
    scene.add(dirLight);

    camera = new THREE.PerspectiveCamera(60, 1, 1, 100000);
    camera.position.set(0, 500, 1500);

    controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.screenSpacePanning = true;
  } catch (err) {
    showError(`3D renderer failed to initialise: ${err.message}`);
    return;
  }

  function resize() {
    const w = canvas.parentElement.clientWidth;
    const h = canvas.parentElement.clientHeight - document.getElementById("viewer-controls").offsetHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  // ── Load OBJ from server (BSP → OBJ converted server-side) ──────
  try {
    loadMsg.textContent = "Converting BSP to OBJ…";
    const url = `${base}/api/maps/${encodeURIComponent(mapPath)}/obj`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const objText = await resp.text();

    loadMsg.textContent = "Parsing geometry…";
    const geo = parseOBJGeometry(objText);

    if (!geo) throw new Error("Could not parse OBJ geometry.");

    const mesh = new THREE.Mesh(
      geo,
      new THREE.MeshLambertMaterial({ color: 0x4f8ef7, side: THREE.DoubleSide, wireframe: false })
    );
    scene.add(mesh);

    // Center camera on bounding box
    geo.computeBoundingBox();
    const box = geo.boundingBox;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    camera.position.copy(center).add(new THREE.Vector3(0, maxDim * 0.4, maxDim * 1.2));
    controls.target.copy(center);
    controls.update();

    overlay.classList.add("hidden");
  } catch (err) {
    showError(`Could not load 3D view: ${err.message}`);
  }
}

// ── Minimal OBJ parser ─────────────────────────────────────────────
// Supports "v" and "f" directives; faces may be triangles or simple polygons
// (fan-triangulated).  Handles only vertex indices (no UV or normal indices).
function parseOBJGeometry(text) {
  const verts = [];   // flat [x, y, z, ...]
  const positions = [];

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const parts = line.split(/\s+/);
    if (parts[0] === "v" && parts.length >= 4) {
      verts.push(parseFloat(parts[1]), parseFloat(parts[2]), parseFloat(parts[3]));
    } else if (parts[0] === "f" && parts.length >= 4) {
      // Strip any "vi/vt/vn" → just the vertex index (1-based)
      const indices = parts.slice(1).map((p) => parseInt(p.split("/")[0], 10) - 1);
      const numV = verts.length / 3;
      const v0 = indices[0];
      if (v0 < 0 || v0 >= numV) continue;
      for (let t = 1; t < indices.length - 1; t++) {
        const v1 = indices[t];
        const v2 = indices[t + 1];
        if (v1 < 0 || v1 >= numV || v2 < 0 || v2 >= numV) continue;
        for (const vi of [v0, v1, v2]) {
          const base = vi * 3;
          positions.push(verts[base], verts[base + 1], verts[base + 2]);
        }
      }
    }
  }

  if (!positions.length) return null;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(positions), 3));
  geometry.computeVertexNormals();
  return geometry;
}
