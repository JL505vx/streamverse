import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.161.0/build/three.module.js";

const canvas = document.getElementById("cinema-scene");

if (canvas) {
  const stage = canvas.parentElement;
  const theme = document.body.dataset.sceneTheme || "audience";
  const sceneMode = document.body.dataset.sceneMode || "default";
  const isMobile = window.matchMedia("(max-width: 640px)").matches;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const scenePresets = {
    default: {
      cameraY: isMobile ? 1.7 : 2.2,
      cameraZ: isMobile ? 8.2 : 9.4,
      rootScale: 1,
      motionScale: 1,
      pointerParallax: isMobile ? 0.32 : 0.55,
      particleCount: isMobile ? 110 : 180,
      ringCount: isMobile ? 7 : 11,
      scrollLift: 0.28,
    },
    premiere: {
      cameraY: isMobile ? 1.95 : 2.55,
      cameraZ: isMobile ? 7.8 : 8.8,
      rootScale: isMobile ? 1.14 : 1.22,
      motionScale: 1.18,
      pointerParallax: isMobile ? 0.36 : 0.68,
      particleCount: isMobile ? 130 : 220,
      ringCount: isMobile ? 8 : 15,
      scrollLift: 0.18,
    },
    "member-cockpit": {
      cameraY: isMobile ? 1.82 : 2.36,
      cameraZ: isMobile ? 8.05 : 8.95,
      rootScale: isMobile ? 1.12 : 1.18,
      motionScale: 1.08,
      pointerParallax: isMobile ? 0.34 : 0.6,
      particleCount: isMobile ? 118 : 195,
      ringCount: isMobile ? 7 : 12,
      scrollLift: 0.22,
    },
    "player-focus": {
      cameraY: isMobile ? 1.45 : 1.9,
      cameraZ: isMobile ? 9.2 : 10.8,
      rootScale: isMobile ? 0.98 : 1.06,
      motionScale: 0.72,
      pointerParallax: isMobile ? 0.18 : 0.32,
      particleCount: isMobile ? 72 : 120,
      ringCount: isMobile ? 4 : 7,
      scrollLift: 0.12,
    },
  };
  const scenePreset = scenePresets[sceneMode] || scenePresets.default;

  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, isMobile ? 1.3 : 1.85));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(isMobile ? 50 : 42, 1, 0.1, 120);
  camera.position.set(0, scenePreset.cameraY, scenePreset.cameraZ);

  const palette = {
    audience: {
      accent: 0x0ea5e9,
      secondary: 0x06b6d4,
      cool: 0x38bdf8,
      glow: 0x0a1e3a,
    },
    member: {
      accent: 0x6366f1,
      secondary: 0x0ea5e9,
      cool: 0x38bdf8,
      glow: 0x0d1a3a,
    },
    admin: {
      accent: 0x38bdf8,
      secondary: 0x6366f1,
      cool: 0x7dd3fc,
      glow: 0x0a1630,
    },
  };
  const colors = palette[theme] || palette.audience;

  scene.add(new THREE.AmbientLight(0xb8d4f8, isMobile ? 1.75 : 1.55));

  const keyLight = new THREE.PointLight(colors.secondary, isMobile ? 13 : 11.5, 32, 2);
  keyLight.position.set(-5.2, 4.3, 5.8);
  scene.add(keyLight);

  const fillLight = new THREE.PointLight(colors.cool, isMobile ? 10.5 : 9.4, 34, 2);
  fillLight.position.set(5.1, 2.8, 5.6);
  scene.add(fillLight);

  const rimLight = new THREE.PointLight(colors.accent, isMobile ? 8.8 : 7.2, 22, 2);
  rimLight.position.set(0, 6.2, -3.2);
  scene.add(rimLight);

  const projectorLight = new THREE.SpotLight(colors.cool, isMobile ? 10 : 8.2, 32, Math.PI / 5.5, 0.6, 1.5);
  projectorLight.position.set(-2.8, 4.4, 8.4);
  projectorLight.target.position.set(0, 0.8, -1.5);
  scene.add(projectorLight);
  scene.add(projectorLight.target);

  const root = new THREE.Group();
  scene.add(root);

  const dynamicMeshes = [];
  const accentMaterial = (color, roughness = 0.4, metalness = 0.12, emissive = 0x000000, emissiveIntensity = 0) =>
    new THREE.MeshStandardMaterial({ color, roughness, metalness, emissive, emissiveIntensity });

  function registerDynamic(mesh, options = {}) {
    mesh.userData.floatSpeed = options.floatSpeed ?? 0.35;
    mesh.userData.floatAmplitude = options.floatAmplitude ?? 0.12;
    mesh.userData.spinSpeed = options.spinSpeed ?? 0.003;
    mesh.userData.baseY = mesh.position.y;
    dynamicMeshes.push(mesh);
    return mesh;
  }

  function addStageScreen() {
    const screenGroup = new THREE.Group();

    const screenGlow = new THREE.Mesh(
      new THREE.PlaneGeometry(isMobile ? 7.8 : 9.2, isMobile ? 4.8 : 5.6),
      new THREE.MeshBasicMaterial({
        color: colors.glow,
        transparent: true,
        opacity: 0.18,
        depthWrite: false,
      }),
    );
    screenGlow.position.set(0, 1.25, -2.9);
    screenGroup.add(screenGlow);

    const screen = new THREE.Mesh(
      new THREE.PlaneGeometry(isMobile ? 7.1 : 8.5, isMobile ? 4.2 : 5),
      new THREE.MeshStandardMaterial({
        color: 0x0d1220,
        roughness: 0.4,
        metalness: 0.1,
        emissive: colors.glow,
        emissiveIntensity: 0.12,
      }),
    );
    screen.position.set(0, 1.15, -2.75);
    screenGroup.add(screen);

    const frame = new THREE.Mesh(
      new THREE.BoxGeometry(isMobile ? 7.5 : 8.9, isMobile ? 4.5 : 5.3, 0.16),
      accentMaterial(0x151b28, 0.52, 0.18),
    );
    frame.position.set(0, 1.15, -2.92);
    screenGroup.add(frame);

    root.add(screenGroup);
  }

  function addProjectorBeam(x, z, color, lean = 0) {
    const beam = new THREE.Mesh(
      new THREE.ConeGeometry(1.1, 5.6, 24, 1, true),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.08,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    beam.position.set(x, 2.2, z);
    beam.rotation.z = lean;
    beam.rotation.x = Math.PI * 0.5;
    scene.add(beam);
    registerDynamic(beam, { floatSpeed: 0.18, floatAmplitude: 0.04, spinSpeed: 0 });
  }

  function addPopcornBucket(x, y, z) {
    const group = new THREE.Group();
    const bucket = new THREE.Mesh(
      new THREE.CylinderGeometry(0.95, 0.65, 1.9, 26),
      accentMaterial(0xd92d43, 0.45, 0.05),
    );
    group.add(bucket);

    for (let i = 0; i < 6; i += 1) {
      const stripe = new THREE.Mesh(
        new THREE.BoxGeometry(0.18, 1.8, 1.05),
        accentMaterial(0xfff4db, 0.55, 0.02),
      );
      stripe.position.x = -0.5 + i * 0.2;
      stripe.position.z = 0.26;
      stripe.rotation.y = 0.08;
      group.add(stripe);
    }

    for (let i = 0; i < 16; i += 1) {
      const kernel = new THREE.Mesh(
        new THREE.SphereGeometry(0.18, 10, 10),
        accentMaterial(0xffe6a6, 0.84, 0.01),
      );
      kernel.position.set(
        (Math.random() - 0.5) * 1.45,
        0.95 + Math.random() * 0.45,
        (Math.random() - 0.5) * 1.15,
      );
      kernel.scale.set(1.12, 0.82 + Math.random() * 0.45, 0.92);
      group.add(kernel);
    }

    group.position.set(x, y, z);
    registerDynamic(group, { floatSpeed: 0.32, floatAmplitude: 0.08, spinSpeed: 0.0012 });
    return group;
  }

  function addSodaCup(x, y, z) {
    const group = new THREE.Group();
    const cup = new THREE.Mesh(
      new THREE.CylinderGeometry(0.55, 0.42, 1.95, 28),
      accentMaterial(0xf3f7ff, 0.42, 0.06),
    );
    group.add(cup);

    const lid = new THREE.Mesh(
      new THREE.CylinderGeometry(0.62, 0.58, 0.18, 28),
      accentMaterial(0xc8d7eb, 0.35, 0.16),
    );
    lid.position.y = 1.02;
    group.add(lid);

    const straw = new THREE.Mesh(
      new THREE.CylinderGeometry(0.045, 0.045, 1.7, 14),
      accentMaterial(colors.accent, 0.35, 0.08),
    );
    straw.position.set(0.15, 1.62, 0);
    straw.rotation.z = -0.22;
    group.add(straw);

    const band = new THREE.Mesh(
      new THREE.TorusGeometry(0.47, 0.045, 14, 36),
      accentMaterial(colors.secondary, 0.3, 0.18),
    );
    band.rotation.x = Math.PI / 2;
    band.position.y = 0.1;
    group.add(band);

    group.position.set(x, y, z);
    registerDynamic(group, { floatSpeed: 0.36, floatAmplitude: 0.07, spinSpeed: -0.0011 });
    return group;
  }

  function addClapper(x, y, z) {
    const group = new THREE.Group();
    const board = new THREE.Mesh(
      new THREE.BoxGeometry(2.15, 1.25, 0.18),
      accentMaterial(0x171a24, 0.46, 0.18),
    );
    group.add(board);

    const top = new THREE.Mesh(
      new THREE.BoxGeometry(2.2, 0.34, 0.16),
      accentMaterial(0xf2f5fa, 0.5, 0.08),
    );
    top.position.y = 0.82;
    top.rotation.z = -0.18;
    group.add(top);

    for (let i = 0; i < 6; i += 1) {
      const diagonal = new THREE.Mesh(
        new THREE.BoxGeometry(0.22, 0.34, 0.18),
        accentMaterial(i % 2 === 0 ? 0x111111 : colors.secondary, 0.4, 0.1),
      );
      diagonal.position.set(-0.9 + i * 0.36, 0.82, 0);
      diagonal.rotation.z = 0.5;
      group.add(diagonal);
    }

    group.position.set(x, y, z);
    group.rotation.z = -0.12;
    registerDynamic(group, { floatSpeed: 0.28, floatAmplitude: 0.06, spinSpeed: 0.0007 });
    return group;
  }

  function addNachos(x, y, z) {
    const group = new THREE.Group();
    const tray = new THREE.Mesh(
      new THREE.BoxGeometry(2.4, 0.34, 1.6),
      accentMaterial(0x943f31, 0.58, 0.06),
    );
    tray.position.y = -0.22;
    group.add(tray);

    for (let i = 0; i < 9; i += 1) {
      const chip = new THREE.Mesh(
        new THREE.ConeGeometry(0.38, 0.14, 3),
        accentMaterial(0xf4bd46, 0.86, 0.02),
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
      accentMaterial(0xc73b2d, 0.58, 0.02),
    );
    salsa.position.set(0.63, 0.08, 0.2);
    group.add(salsa);

    group.position.set(x, y, z);
    group.rotation.x = -0.12;
    registerDynamic(group, { floatSpeed: 0.25, floatAmplitude: 0.05, spinSpeed: 0.0009 });
    return group;
  }

  function addFilmReel(x, y, z) {
    const group = new THREE.Group();
    const outer = new THREE.Mesh(
      new THREE.CylinderGeometry(0.82, 0.82, 0.16, 32),
      accentMaterial(0x2c3648, 0.38, 0.4),
    );
    outer.rotation.x = Math.PI / 2;
    group.add(outer);

    const inner = new THREE.Mesh(
      new THREE.CylinderGeometry(0.28, 0.28, 0.2, 24),
      accentMaterial(0x10151f, 0.46, 0.16),
    );
    inner.rotation.x = Math.PI / 2;
    group.add(inner);

    for (let i = 0; i < 6; i += 1) {
      const spoke = new THREE.Mesh(
        new THREE.CylinderGeometry(0.09, 0.09, 0.48, 16),
        accentMaterial(colors.cool, 0.3, 0.14, colors.cool, 0.08),
      );
      const angle = (Math.PI * 2 * i) / 6;
      spoke.position.set(Math.cos(angle) * 0.43, Math.sin(angle) * 0.43, 0);
      spoke.rotation.z = angle;
      group.add(spoke);
    }

    group.position.set(x, y, z);
    group.rotation.z = 0.4;
    registerDynamic(group, { floatSpeed: 0.44, floatAmplitude: 0.09, spinSpeed: 0.004 });
    return group;
  }

  function addTicket(x, y, z) {
    const group = new THREE.Group();
    const ticket = new THREE.Mesh(
      new THREE.BoxGeometry(1.55, 0.95, 0.1),
      accentMaterial(colors.accent, 0.36, 0.12),
    );
    group.add(ticket);

    const strip = new THREE.Mesh(
      new THREE.BoxGeometry(1.35, 0.18, 0.11),
      accentMaterial(0x0c1120, 0.42, 0.08),
    );
    strip.position.y = 0.12;
    group.add(strip);

    group.position.set(x, y, z);
    group.rotation.z = 0.28;
    registerDynamic(group, { floatSpeed: 0.52, floatAmplitude: 0.14, spinSpeed: -0.002 });
    return group;
  }

  function addFilmRibbon() {
    const ribbon = new THREE.Group();
    for (let i = 0; i < 8; i += 1) {
      const frame = new THREE.Mesh(
        new THREE.BoxGeometry(1.4, 0.62, 0.08),
        accentMaterial(0x11151f, 0.5, 0.24),
      );
      frame.position.set(-4.9 + i * 1.4, -2.15 + Math.sin(i * 0.65) * 0.16, -0.65 - i * 0.04);
      frame.rotation.z = Math.sin(i * 0.7) * 0.1;
      ribbon.add(frame);

      const perforationLeft = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 0.48, 0.1),
        accentMaterial(colors.secondary, 0.28, 0.04),
      );
      perforationLeft.position.set(frame.position.x - 0.58, frame.position.y, frame.position.z + 0.01);
      ribbon.add(perforationLeft);

      const perforationRight = perforationLeft.clone();
      perforationRight.position.x = frame.position.x + 0.58;
      ribbon.add(perforationRight);
    }
    ribbon.position.z = 1.2;
    root.add(ribbon);
    registerDynamic(ribbon, { floatSpeed: 0.16, floatAmplitude: 0.05, spinSpeed: 0.0005 });
  }

  function addParticles() {
    const count = scenePreset.particleCount;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3);
    const scales = new Float32Array(count);

    for (let i = 0; i < count; i += 1) {
      positions[i * 3] = (Math.random() - 0.5) * 14;
      positions[i * 3 + 1] = -2 + Math.random() * 8.5;
      positions[i * 3 + 2] = -4 + Math.random() * 6;
      scales[i] = 0.7 + Math.random() * 1.1;
    }

    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("scale", new THREE.BufferAttribute(scales, 1));

    const material = new THREE.PointsMaterial({
      color: 0xf4f7ff,
      size: isMobile ? 0.04 : 0.05,
      transparent: true,
      opacity: sceneMode === "player-focus" ? 0.32 : 0.52,
      depthWrite: false,
    });

    const points = new THREE.Points(geometry, material);
    scene.add(points);
    return points;
  }

  addStageScreen();
  addProjectorBeam(-2.9, 3.6, colors.cool, -0.26);
  addProjectorBeam(2.6, 3.1, colors.accent, 0.32);

  const popcornBucket = addPopcornBucket(isMobile ? -2.35 : -2.9, isMobile ? -1.52 : -1.12, 0.35);
  const sodaCup = addSodaCup(isMobile ? 2.3 : 2.95, isMobile ? -1.28 : -1.02, 0.72);
  const clapper = addClapper(0.1, isMobile ? 0.1 : 0.38, -0.3);
  const nachos = addNachos(-0.1, isMobile ? -1.95 : -1.6, 1.42);
  const filmReel = addFilmReel(isMobile ? -1.2 : -1.9, isMobile ? 1.8 : 2.15, 0.48);
  const ticket = addTicket(isMobile ? 1.6 : 2.25, isMobile ? 2.05 : 2.3, -0.2);

  root.add(popcornBucket);
  root.add(sodaCup);
  root.add(clapper);
  root.add(nachos);
  root.add(filmReel);
  root.add(ticket);
  addFilmRibbon();

  if (sceneMode === "premiere") {
    popcornBucket.position.set(isMobile ? -2.8 : -3.8, isMobile ? -1.45 : -1.05, 0.8);
    sodaCup.position.set(isMobile ? 2.75 : 3.8, isMobile ? -1.18 : -0.9, 0.95);
    clapper.position.set(0.15, isMobile ? 0.4 : 0.72, 0.15);
    clapper.scale.setScalar(1.15);
    filmReel.position.set(isMobile ? -0.4 : -1.1, isMobile ? 2.45 : 2.9, 0.2);
    ticket.position.set(isMobile ? 1.95 : 2.95, isMobile ? 2.2 : 2.8, -0.35);
  } else if (sceneMode === "member-cockpit") {
    popcornBucket.position.set(isMobile ? -1.95 : -2.6, isMobile ? -1.45 : -1.02, 0.7);
    sodaCup.position.set(isMobile ? 2.1 : 2.8, isMobile ? -1.18 : -0.95, 0.92);
    nachos.position.set(-0.55, isMobile ? -2.2 : -1.82, 1.6);
    ticket.position.set(isMobile ? 1.2 : 1.75, isMobile ? 1.92 : 2.15, -0.08);
  } else if (sceneMode === "player-focus") {
    popcornBucket.position.set(isMobile ? -3.1 : -4.4, isMobile ? -1.92 : -1.34, 1.1);
    sodaCup.position.set(isMobile ? 3.05 : 4.45, isMobile ? -1.62 : -1.18, 1.28);
    clapper.position.set(0.1, isMobile ? 1.1 : 1.55, -1.35);
    clapper.scale.setScalar(0.84);
    nachos.position.set(-0.25, isMobile ? -2.5 : -2.05, 2.3);
    filmReel.position.set(isMobile ? -3.1 : -4.1, isMobile ? 1.7 : 2.1, 0.1);
    ticket.position.set(isMobile ? 3.2 : 4.15, isMobile ? 1.86 : 2.35, -0.1);
  }

  if (isMobile) {
    root.scale.setScalar(scenePreset.rootScale * 1.08);
  } else {
    root.scale.setScalar(scenePreset.rootScale);
  }

  const floatingRings = [];
  for (let i = 0; i < scenePreset.ringCount; i += 1) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.12 + Math.random() * 0.12, 0.012, 10, 24),
      accentMaterial(i % 2 === 0 ? colors.accent : colors.secondary, 0.22, 0.38, colors.secondary, 0.08),
    );
    ring.position.set(
      (Math.random() - 0.5) * (isMobile ? 6.2 : 7.8),
      0.35 + Math.random() * 3.6,
      -2.2 + Math.random() * 1.8,
    );
    ring.userData.floatSpeed = 0.24 + Math.random() * 0.35;
    ring.userData.floatAmplitude = 0.08 + Math.random() * 0.08;
    ring.userData.spinSpeed = 0.004 + Math.random() * 0.004;
    ring.userData.baseY = ring.position.y;
    floatingRings.push(ring);
    scene.add(ring);
  }

  const particleField = addParticles();

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
  let scrollProgress = 0;

  window.addEventListener("pointermove", (event) => {
    pointerX = event.clientX / window.innerWidth - 0.5;
    pointerY = event.clientY / window.innerHeight - 0.5;
  });

  const syncScrollProgress = () => {
    const maxScroll = Math.max(document.body.scrollHeight - window.innerHeight, 1);
    scrollProgress = Math.min(window.scrollY / maxScroll, 1);
  };

  syncScrollProgress();
  window.addEventListener("scroll", syncScrollProgress, { passive: true });

  const clock = new THREE.Clock();

  function animate() {
    const elapsed = clock.getElapsedTime();
    const motionFactor = (reduceMotion ? 0.32 : 1) * scenePreset.motionScale;

    root.rotation.y = (Math.sin(elapsed * 0.24) * 0.12 + pointerX * (isMobile ? 0.08 : 0.22)) * motionFactor;
    root.rotation.x = (Math.cos(elapsed * 0.18) * 0.03 + pointerY * (isMobile ? 0.05 : 0.12)) * motionFactor;
    root.position.y = Math.sin(elapsed * 0.42) * 0.08 * motionFactor - scrollProgress * scenePreset.scrollLift;
    root.position.x = pointerX * (isMobile ? 0.12 : 0.24);

    dynamicMeshes.forEach((mesh, index) => {
      mesh.position.y = mesh.userData.baseY + Math.sin(elapsed * mesh.userData.floatSpeed + index * 0.6) * mesh.userData.floatAmplitude * motionFactor;
      mesh.rotation.y += mesh.userData.spinSpeed * motionFactor;
    });

    floatingRings.forEach((ring, index) => {
      ring.rotation.x += (0.003 + index * 0.0002) * motionFactor;
      ring.rotation.y += ring.userData.spinSpeed * motionFactor;
      ring.position.y = ring.userData.baseY + Math.sin(elapsed * ring.userData.floatSpeed + index) * ring.userData.floatAmplitude * motionFactor;
    });

    if (particleField) {
      particleField.rotation.z = Math.sin(elapsed * 0.08) * 0.08 * motionFactor;
      particleField.position.y = Math.sin(elapsed * 0.12) * 0.12 * motionFactor;
    }

    keyLight.position.x = -5.2 + Math.sin(elapsed * 0.35) * 0.6 * motionFactor;
    fillLight.position.x = 5.1 + Math.cos(elapsed * 0.28) * 0.4 * motionFactor;
    projectorLight.position.x = -2.8 + pointerX * 0.8;

    camera.position.x += ((pointerX * scenePreset.pointerParallax) - camera.position.x) * 0.05;
    camera.position.y += ((scenePreset.cameraY + pointerY * (sceneMode === "player-focus" ? 0.2 : 0.36) - scrollProgress * 0.18) - camera.position.y) * 0.05;
    camera.lookAt(0, (sceneMode === "player-focus" ? 0.42 : 0.7) - scrollProgress * 0.18, 0.4);

    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }

  animate();
}
