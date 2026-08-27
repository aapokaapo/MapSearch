// viewer.js — Three.js BSP 3D viewer
// Fetches mesh + material data from the server and renders it.

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

  // ── Load mesh from server ────────────────────────────────────────
  try {
    loadMsg.textContent = "Building BSP mesh…";
    const url = `${base}/api/maps/${encodeURIComponent(mapPath)}/viewer-mesh`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const meshData = await resp.json();

    loadMsg.textContent = "Parsing geometry…";
    const geo = buildGeometry(meshData);
    const materials = await buildMaterials(meshData.materials || [], base);

    if (!geo) throw new Error("Could not parse geometry.");

    const mesh = new THREE.Mesh(geo, materials);
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

function buildGeometry(meshData) {
  const positions = meshData.positions || [];
  const uvs = meshData.uvs || [];
  if (!positions.length || positions.length % 3 !== 0) return null;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(positions), 3));
  if (uvs.length === (positions.length / 3) * 2) {
    geometry.setAttribute("uv", new THREE.Float32BufferAttribute(new Float32Array(uvs), 2));
  }
  if (Array.isArray(meshData.groups)) {
    geometry.clearGroups();
    for (const group of meshData.groups) {
      if (!Number.isInteger(group.start) || !Number.isInteger(group.count) || !Number.isInteger(group.material_index)) continue;
      geometry.addGroup(group.start, group.count, group.material_index);
    }
  }
  geometry.computeVertexNormals();
  return geometry;
}

async function buildMaterials(materialDefs, base) {
  const textureLoader = new THREE.TextureLoader();
  const mats = await Promise.all(materialDefs.map(async (def) => {
    const color = hashColor(def.name || "__default__");
    let map = null;
    if (def.texture_url) {
      const textureUrl = `${base}${def.texture_url}`;
      map = await loadTexture(textureLoader, textureUrl);
      if (map) {
        map.wrapS = THREE.RepeatWrapping;
        map.wrapT = THREE.RepeatWrapping;
        const w = map.image.width || 256;
        const h = map.image.height || 256;
        map.repeat.set(1 / w, 1 / h);
      }
    }
    return new THREE.MeshLambertMaterial({
      color,
      map,
      side: THREE.DoubleSide,
      wireframe: false
    });
  }));
  if (!mats.length) {
    mats.push(new THREE.MeshLambertMaterial({ color: 0x4f8ef7, side: THREE.FrontSide, wireframe: false }));
  }
  return mats;
}

function loadTexture(loader, url) {
  return new Promise((resolve) => {
    loader.load(url, resolve, undefined, () => resolve(null));
  });
}

function hashColor(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i++) hash = ((hash << 5) - hash) + text.charCodeAt(i);
  const r = 120 + ((hash >> 16) & 0x7f);
  const g = 120 + ((hash >> 8) & 0x7f);
  const b = 120 + (hash & 0x7f);
  return (r << 16) | (g << 8) | b;
}
