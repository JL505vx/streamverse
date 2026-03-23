import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js";

const canvas = document.getElementById("cinema-scene");

if (canvas) {
  const stage = canvas.parentElement;
  const theme = document.body.dataset.sceneTheme || "audience";
  const isMobile = window.matchMedia("(max-width: 640px)").matches;
  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, isMobile ? 1.4 : 1.8));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(isMobile ? 48 : 42, 1, 0.1, 100);
  camera.position.set(0, isMobile ? 1.8 : 2.2, isMobile ? 8.1 : 9);

  scene.add(new THREE.AmbientLight(0xffe4b8, isMobile ? 1.95 : 1.7));

  const keyLight = new THREE.PointLight(0xff7b54, isMobile ? 13 : 11, 28, 2);
  keyLight.position.set(-5, 4, 6);
  scene.add(keyLight);

  const fillLight = new THREE.PointLight(0x5bb8ff, isMobile ? 10 : 8, 32, 2);
  fillLight.position.set(5, 3, 5);
  scene.add(fillLight);

  const rimLight = new THREE.PointLight(0xffd84f, isMobile ? 9 : 7, 20, 2);
  rimLight.position.set(0, 6, -3);
  scene.add(rimLight);

  const root = new THREE.Group();
  scene.add(root);

  const accentColors = {
    audience: 0xffc145,
    member: 0xff5f7a,
    admin: 0x7bc4ff,
  };
  const accent = accentColors[theme] || accentColors.audience;

  function material(color, roughness = 0.4, metalness = 0.1) {
    return new THREE.MeshStandardMaterial({ color, roughness, metalness });
  }

  function addPopcornBucket(x, y, z) {
    const group = new THREE.Group();
    const bucket = new THREE.Mesh(
      new THREE.CylinderGeometry(0.95, 0.65, 1.9, 24),
      material(0xd92d43, 0.45, 0.05),
    );
    group.add(bucket);

    for (let i = 0; i < 6; i += 1) {
      const stripe = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, 1.8, 1.05),
        material(0xfff4db, 0.55, 0.02),
      );
      stripe.position.x = -0.5 + i * 0.2;
      stripe.position.z = 0.26;
      stripe.rotation.y = 0.08;
      group.add(stripe);
    }

    for (let i = 0; i < 15; i += 1) {
      const kernel = new THREE.Mesh(
        new THREE.SphereGeometry(0.18, 10, 10),
        material(0xffe6a6, 0.85, 0.01),
      );
      kernel.position.set(
        (Math.random() - 0.5) * 1.4,
        0.95 + Math.random() * 0.45,
        (Math.random() - 0.5) * 1.1,
      );
      kernel.scale.set(1.1, 0.8 + Math.random() * 0.5, 0.9);
      group.add(kernel);
    }

    group.position.set(x, y, z);
    return group;
  }

  function addSodaCup(x, y, z) {
    const group = new THREE.Group();
    const cup = new THREE.Mesh(
      new THREE.CylinderGeometry(0.55, 0.42, 1.95, 28),
      material(0xf3f7ff, 0.42, 0.06),
    );
    group.add(cup);

    const lid = new THREE.Mesh(
      new THREE.CylinderGeometry(0.62, 0.58, 0.18, 28),
      material(0xc8d7eb, 0.35, 0.16),
    );
    lid.position.y = 1.02;
    group.add(lid);

    const straw = new THREE.Mesh(
      new THREE.CylinderGeometry(0.045, 0.045, 1.7, 14),
      material(0xff5f7a, 0.35, 0.08),
    );
    straw.position.set(0.15, 1.62, 0);
    straw.rotation.z = -0.22;
    group.add(straw);

    const band = new THREE.Mesh(
      new THREE.TorusGeometry(0.47, 0.045, 14, 36),
      material(accent, 0.3, 0.18),
    );
    band.rotation.x = Math.PI / 2;
    band.position.y = 0.1;
    group.add(band);

    group.position.set(x, y, z);
    return group;
  }

  function addClapper(x, y, z) {
    const group = new THREE.Group();
    const board = new THREE.Mesh(
      new THREE.BoxGeometry(2.15, 1.25, 0.18),
      material(0x171a24, 0.46, 0.18),
    );
    group.add(board);

    const top = new THREE.Mesh(
      new THREE.BoxGeometry(2.2, 0.34, 0.16),
      material(0xf2f5fa, 0.5, 0.08),
    );
    top.position.y = 0.82;
    top.rotation.z = -0.18;
    group.add(top);

    for (let i = 0; i < 6; i += 1) {
      const diagonal = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.34, 0.18),
        material(i % 2 === 0 ? 0x111111 : accent, 0.4, 0.1),
      );
      diagonal.position.set(-0.9 + i * 0.36, 0.82, 0);
      diagonal.rotation.z = 0.5;
      group.add(diagonal);
    }

    group.position.set(x, y, z);
    group.rotation.z = -0.12;
    return group;
  }

  function addNachos(x, y, z) {
    const group = new THREE.Group();
    const tray = new THREE.Mesh(
      new THREE.BoxGeometry(2.4, 0.34, 1.6),
      material(0x943f31, 0.58, 0.06),
    );
    tray.position.y = -0.22;
    group.add(tray);

    for (let i = 0; i < 9; i += 1) {
      const chip = new THREE.Mesh(
        new THREE.ConeGeometry(0.38, 0.14, 3),
        material(0xf4bd46, 0.86, 0.02),
      );
      chip.position.set(
        (Math.random() - 0.5) * 1.7,
        Math.random() * 0.35,
        (Math.random() - 0.5) * 1.05,
      );
      chip.rotation.set(Math.random() * 0.45, Math.random() * Math.PI, Math.random() * 0.35);
      group.add(chip);
    }

    const salsa = new THREE.Mesh(
      new THREE.CylinderGeometry(0.32, 0.32, 0.25, 20),
      material(0xc73b2d, 0.58, 0.02),
    );
    salsa.position.set(0.63, 0.08, 0.2);
    group.add(salsa);

    group.position.set(x, y, z);
    group.rotation.x = -0.12;
    return group;
  }

  root.add(addPopcornBucket(isMobile ? -2.2 : -2.7, isMobile ? -1.55 : -1.15, 0.1));
  root.add(addSodaCup(isMobile ? 2.15 : 2.8, isMobile ? -1.35 : -1.1, 0.4));
  root.add(addClapper(0.2, isMobile ? -0.05 : 0.25, -0.6));
  root.add(addNachos(0.25, isMobile ? -1.95 : -1.6, 1.1));

  if (isMobile) {
    root.scale.set(1.1, 1.1, 1.1);
  }

  const floatingRings = [];
  for (let i = 0; i < (isMobile ? 7 : 10); i += 1) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.12 + Math.random() * 0.12, 0.012, 10, 24),
      material(accent, 0.25, 0.35),
    );
    ring.position.set(
      (Math.random() - 0.5) * (isMobile ? 6.1 : 7.5),
      0.4 + Math.random() * 3.2,
      -1.8 + Math.random() * 1.4,
    );
    ring.userData.speed = 0.4 + Math.random() * 0.5;
    floatingRings.push(ring);
    scene.add(ring);
  }

  function resize() {
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  resize();
  window.addEventListener("resize", resize);

  let pointerX = 0;
  let pointerY = 0;
  window.addEventListener("pointermove", (event) => {
    pointerX = event.clientX / window.innerWidth - 0.5;
    pointerY = event.clientY / window.innerHeight - 0.5;
  });

  const clock = new THREE.Clock();

  function animate() {
    const elapsed = clock.getElapsedTime();
    root.rotation.y = Math.sin(elapsed * 0.3) * 0.18 + pointerX * (isMobile ? 0.12 : 0.28);
    root.rotation.x = Math.cos(elapsed * 0.25) * 0.05 + pointerY * (isMobile ? 0.08 : 0.16);
    root.position.y = Math.sin(elapsed * 0.7) * 0.12;

    floatingRings.forEach((ring, index) => {
      ring.rotation.x += 0.003 + index * 0.0002;
      ring.rotation.y += 0.004 + ring.userData.speed * 0.0015;
      ring.position.y += Math.sin(elapsed * ring.userData.speed + index) * 0.0025;
    });

    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }

  animate();
}
