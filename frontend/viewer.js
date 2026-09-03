// viewer.js — Three.js BSP 3D viewer
// Fetches mesh + material data from the server and renders it.

async function initViewer(base, mapPath) {
  const canvas = document.getElementById("viewer-canvas");
  const overlay = document.getElementById("loading-overlay");
  const loadMsg = document.getElementById("loading-msg");
  let ambientLight, hemiLight, keyLight, fillLight;

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
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    scene = new THREE.Scene();
    ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
    scene.add(ambientLight);
    hemiLight = new THREE.HemisphereLight(0xbfd9ff, 0x2d2218, 0.85);
    scene.add(hemiLight);
    keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
    keyLight.position.set(1, 2, 1);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(2048, 2048);
    keyLight.shadow.bias = -0.0005;
    keyLight.shadow.normalBias = 0.75;
    scene.add(keyLight);
    scene.add(keyLight.target);
    fillLight = new THREE.DirectionalLight(0xaec8ff, 0.35);
    fillLight.position.set(-1.5, 1, -0.8);
    scene.add(fillLight);

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

    const skyboxUrls = meshData.skybox_urls;
    if (Array.isArray(skyboxUrls) && skyboxUrls.length === 6) {
      const cubeMap = await loadCubeTexture(skyboxUrls.map((url) => `${base}${url}`));
      if (cubeMap) {
        scene.background = cubeMap;
        scene.environment = cubeMap;
      }
    }

    loadMsg.textContent = "Parsing geometry…";
    const geo = buildGeometry(meshData);
    const materials = await buildMaterials(meshData.materials || [], base);

    if (!geo) throw new Error("Could not parse geometry.");

    const mesh = new THREE.Mesh(geo, materials);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    scene.add(mesh);

    // Center camera on bounding box
    geo.computeBoundingBox();
    const box = geo.boundingBox;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);
    const maxDim = Math.max(size.x, size.y, size.z);
    applyWorldspawnSkyLighting(meshData.sky_lighting, center, maxDim, ambientLight, hemiLight, keyLight, fillLight);
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
        map.encoding = THREE.sRGBEncoding;
        map.wrapS = THREE.RepeatWrapping;
        map.wrapT = THREE.RepeatWrapping;
        const w = map.image.width || 256;
        const h = map.image.height || 256;
        const uvScale = def.uv_scale || 1;
        map.repeat.set(uvScale / w, uvScale / h);
      }
    }
    return new THREE.MeshLambertMaterial({
      color,
      map,
      side: def.opacity < 1.0 ? THREE.DoubleSide : THREE.FrontSide,
      transparent: def.opacity < 1.0,
      opacity: def.opacity ?? 1.0,
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

function loadCubeTexture(urls) {
  return new Promise((resolve) => {
    new THREE.CubeTextureLoader().load(urls, resolve, undefined, () => resolve(null));
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

function applyWorldspawnSkyLighting(lighting, center, maxDim, ambientLight, hemiLight, keyLight, fillLight) {
  const lightOffset = Math.max(maxDim, 1);
  const sunColor = toSkyLightColor(lighting?.sunlight_color);
  const sunStrength = toSkyLightIntensity(lighting?.sunlight);
  const lightDirection = toSkyLightDirection(lighting?.sun_direction);
  const skyTint = sunColor.clone().lerp(new THREE.Color(0xbfd9ff), 0.45);
  const groundTint = sunColor.clone().lerp(new THREE.Color(0x2d2218), 0.8);

  ambientLight.color.copy(sunColor.clone().lerp(new THREE.Color(0xffffff), 0.6));
  ambientLight.intensity = Math.min(0.55, 0.16 + sunStrength * 0.12);
  hemiLight.color.copy(skyTint);
  hemiLight.groundColor.copy(groundTint);
  hemiLight.intensity = Math.min(1.15, 0.45 + sunStrength * 0.4);

  keyLight.color.copy(sunColor);
  keyLight.intensity = sunStrength;
  keyLight.position.copy(center).add(lightDirection.clone().multiplyScalar(lightOffset));
  keyLight.target.position.copy(center);
  keyLight.shadow.camera.left = -lightOffset * 0.7;
  keyLight.shadow.camera.right = lightOffset * 0.7;
  keyLight.shadow.camera.top = lightOffset * 0.7;
  keyLight.shadow.camera.bottom = -lightOffset * 0.7;
  keyLight.shadow.camera.near = 1;
  keyLight.shadow.camera.far = lightOffset * 3;
  keyLight.shadow.camera.updateProjectionMatrix();

  fillLight.color.copy(skyTint);
  fillLight.intensity = Math.max(0.18, sunStrength * 0.35);
  fillLight.position.copy(center).add(lightDirection.clone().multiplyScalar(-lightOffset * 0.7)).add(new THREE.Vector3(-lightOffset * 0.15, lightOffset * 0.2, -lightOffset * 0.1));
}

function toSkyLightColor(rawColor) {
  if (!Array.isArray(rawColor) || rawColor.length !== 3) return new THREE.Color(0xffffff);
  const values = rawColor.map((value) => Number.isFinite(value) ? Math.max(0, value) : 1);
  const scale = values.some((value) => value > 1) ? 255 : 1;
  return new THREE.Color(values[0] / scale, values[1] / scale, values[2] / scale);
}

function toSkyLightIntensity(rawIntensity) {
  if (!Number.isFinite(rawIntensity)) return 0.9;
  return THREE.MathUtils.clamp(rawIntensity / 200, 0.2, 2.5);
}

function toSkyLightDirection(rawDirection) {
  if (Array.isArray(rawDirection) && rawDirection.length === 3 && rawDirection.every((value) => Number.isFinite(value))) {
    const dir = new THREE.Vector3(rawDirection[0], rawDirection[2], -rawDirection[1]).multiplyScalar(-1);
    if (dir.lengthSq() > 0) return dir.normalize();
  }
  return new THREE.Vector3(0.65, 1, 0.65).normalize();
}
