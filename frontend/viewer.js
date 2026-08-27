// viewer.js — Three.js BSP 3D viewer
// Parses a Quake 2 BSP file and renders its geometry.

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

  // ── Load BSP ────────────────────────────────────────────────────
  try {
    loadMsg.textContent = "Downloading BSP…";
    const url = `${base}/api/maps/${encodeURIComponent(mapPath)}/bsp`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const buf = await resp.arrayBuffer();

    loadMsg.textContent = "Parsing geometry…";
    const geo = parseQ2BSP(buf);

    if (!geo) throw new Error("Could not parse BSP geometry.");

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

// ── Quake 2 BSP parser ─────────────────────────────────────────────
// Lump indices (Q2 BSP format)
const LUMP_VERTICES  = 2;
const LUMP_EDGES     = 11;
const LUMP_SURFEDGES = 12;
const LUMP_FACES     = 6;

function parseQ2BSP(buffer) {
  const dv = new DataView(buffer);
  const magic = String.fromCharCode(
    dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3)
  );
  if (magic !== "IBSP") {
    console.warn("Not a Quake 2 BSP (magic=" + magic + ")");
    return null;
  }
  const version = dv.getInt32(4, true);
  if (version !== 38) {
    console.warn("Unexpected BSP version:", version);
  }

  // Each lump entry: offset (4) + length (4), starting at byte 8
  function lump(idx) {
    const off = 8 + idx * 8;
    return { offset: dv.getUint32(off, true), length: dv.getUint32(off + 4, true) };
  }

  const vl = lump(LUMP_VERTICES);
  const el = lump(LUMP_EDGES);
  const sl = lump(LUMP_SURFEDGES);
  const fl = lump(LUMP_FACES);

  // Vertices: 3 floats each (12 bytes)
  const numVerts = Math.floor(vl.length / 12);
  const verts = new Float32Array(numVerts * 3);
  for (let i = 0; i < numVerts; i++) {
    const base = vl.offset + i * 12;
    verts[i * 3]     = dv.getFloat32(base,     true);
    verts[i * 3 + 1] = dv.getFloat32(base + 4, true);
    verts[i * 3 + 2] = dv.getFloat32(base + 8, true);
  }

  // Edges: 2 × uint16 each (4 bytes)
  const numEdges = Math.floor(el.length / 4);
  const edges = new Uint16Array(numEdges * 2);
  for (let i = 0; i < numEdges; i++) {
    const base = el.offset + i * 4;
    edges[i * 2]     = dv.getUint16(base,     true);
    edges[i * 2 + 1] = dv.getUint16(base + 2, true);
  }

  // Surfedges: 1 × int32 each (4 bytes)
  const numSurfEdges = Math.floor(sl.length / 4);
  const surfedges = new Int32Array(numSurfEdges);
  for (let i = 0; i < numSurfEdges; i++) {
    surfedges[i] = dv.getInt32(sl.offset + i * 4, true);
  }

  // Faces: 20 bytes each
  // first_edge (uint32 @0), num_edges (uint16 @4)
  const FACE_SIZE = 20;
  const numFaces = Math.floor(fl.length / FACE_SIZE);

  const positions = [];

  for (let f = 0; f < numFaces; f++) {
    const fBase = fl.offset + f * FACE_SIZE;
    const firstEdge = dv.getUint32(fBase, true);
    const numEdgesF = dv.getUint16(fBase + 4, true);
    if (numEdgesF < 3) continue;

    // Fan-triangulate: v0 + vi + vi+1
    const faceVerts = [];
    for (let e = 0; e < numEdgesF; e++) {
      const seIdx = firstEdge + e;
      if (seIdx >= numSurfEdges) continue;
      const se = surfedges[seIdx];
      let edgeIdx, vi;
      if (se >= 0) {
        edgeIdx = se * 2;
        if (edgeIdx >= numEdges * 2) continue;
        vi = edges[edgeIdx];
      } else {
        edgeIdx = (-se) * 2 + 1;
        if (edgeIdx >= numEdges * 2) continue;
        vi = edges[edgeIdx];
      }
      if (vi >= numVerts) continue;
      faceVerts.push(vi);
    }
    if (faceVerts.length < 3) continue;
    for (let t = 1; t < faceVerts.length - 1; t++) {
      const i0 = faceVerts[0];
      const i1 = faceVerts[t];
      const i2 = faceVerts[t + 1];
      // Q2 coords: x, z, -y  →  Three.js x, y, z
      positions.push(
        verts[i0 * 3], verts[i0 * 3 + 2], -verts[i0 * 3 + 1],
        verts[i1 * 3], verts[i1 * 3 + 2], -verts[i1 * 3 + 1],
        verts[i2 * 3], verts[i2 * 3 + 2], -verts[i2 * 3 + 1]
      );
    }
  }

  if (!positions.length) return null;

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(positions), 3));
  geometry.computeVertexNormals();
  return geometry;
}
