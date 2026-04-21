/* StreamVerse cinematic background v3
 * Real parallax depth + lightweight physics (fall, drift, launch arcs).
 * Mobile-first simplification and reduced-motion safe behavior.
 */
(function () {
  'use strict';

  const canvas = document.getElementById('cinema-bg');
  if (!canvas) return;

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reducedMotion) {
    canvas.style.display = 'none';
    return;
  }

  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  const isMobile = window.matchMedia('(max-width: 760px)').matches;
  const isTablet = window.matchMedia('(min-width: 761px) and (max-width: 1080px)').matches;
  const hasFinePointer = window.matchMedia('(pointer:fine)').matches;

  const DPR = Math.min(window.devicePixelRatio || 1, 2);
  const SIZE = {
    width: 0,
    height: 0,
  };

  const LIMITS = {
    mobile: { props: 14, particles: 26, neon: 2, launchEveryMs: 3800 },
    tablet: { props: 22, particles: 44, neon: 3, launchEveryMs: 2900 },
    desktop: { props: 30, particles: 72, neon: 4, launchEveryMs: 2100 },
  };

  const PROFILE = isMobile ? LIMITS.mobile : isTablet ? LIMITS.tablet : LIMITS.desktop;

  const PROPS = ['popcorn', 'nachos', 'ticket', 'cup'];
  const NEON = [
    'rgba(248, 68, 122, 0.56)',
    'rgba(58, 152, 255, 0.56)',
    'rgba(248, 68, 122, 0.36)',
    'rgba(58, 152, 255, 0.36)',
  ];

  let mouseX = 0;
  let mouseY = 0;
  let targetMouseX = 0;
  let targetMouseY = 0;
  let rafId = null;
  let lastTs = performance.now();
  let lastLaunchAt = 0;
  let inView = !document.hidden;

  const props = [];
  const particles = [];
  const neonBands = [];

  function random(min, max) {
    return min + Math.random() * (max - min);
  }

  function pick(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
  }

  function resize() {
    SIZE.width = window.innerWidth;
    SIZE.height = window.innerHeight;
    canvas.width = Math.floor(SIZE.width * DPR);
    canvas.height = Math.floor(SIZE.height * DPR);
    canvas.style.width = SIZE.width + 'px';
    canvas.style.height = SIZE.height + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }

  function seedNeon() {
    neonBands.length = 0;
    for (let i = 0; i < PROFILE.neon; i += 1) {
      neonBands.push({
        x: random(-SIZE.width * 0.2, SIZE.width * 1.2),
        y: random(0, SIZE.height),
        radius: random(180, 420),
        color: pick(NEON),
        driftX: random(-0.08, 0.08),
        driftY: random(-0.03, 0.03),
        depth: random(0.15, 0.42),
      });
    }
  }

  function spawnProp(kind) {
    const depth = random(0.18, 1.0);
    const isLaunch = kind === 'launch';
    const base = {
      type: pick(PROPS),
      depth,
      size: random(18, 62) * (0.58 + depth * 0.72),
      x: random(-80, SIZE.width + 80),
      y: random(-120, SIZE.height + 120),
      vx: random(-0.32, 0.32) * (0.6 + depth),
      vy: random(0.08, 0.44) * (0.5 + depth),
      ax: 0,
      ay: random(0.0035, 0.0115),
      rotation: random(-0.6, 0.6),
      vr: random(-0.005, 0.005),
      alpha: random(0.2, 0.7) * (0.5 + depth * 0.45),
      driftWave: random(0, Math.PI * 2),
      driftAmp: random(0.02, 0.28) * (1.2 - depth * 0.45),
      mode: isLaunch ? 'launch' : Math.random() > 0.3 ? 'fall' : 'drift',
    };

    if (isLaunch) {
      base.x = random(-40, SIZE.width + 40);
      base.y = SIZE.height + random(20, 90);
      base.vx = random(-1.1, 1.1) * (0.6 + depth * 0.8);
      base.vy = random(-2.5, -1.4);
      base.ay = random(0.012, 0.02);
      base.alpha = random(0.34, 0.72);
    }

    return base;
  }

  function spawnParticle(kind) {
    const depth = random(0.1, 1);
    return {
      kind: kind || (Math.random() > 0.8 ? 'flare' : 'dust'),
      depth,
      x: random(-30, SIZE.width + 30),
      y: random(-40, SIZE.height + 40),
      vx: random(-0.18, 0.18) * (0.5 + depth),
      vy: random(0.02, 0.24) * (0.3 + depth),
      ay: random(0.0015, 0.0048),
      radius: random(0.8, 3.6) * (0.5 + depth * 0.8),
      alpha: random(0.12, 0.6),
      pulse: random(0.3, 1.4),
      phase: random(0, Math.PI * 2),
      hue: Math.random() > 0.5 ? 345 : 215,
    };
  }

  function resetPools() {
    props.length = 0;
    particles.length = 0;
    for (let i = 0; i < PROFILE.props; i += 1) props.push(spawnProp('normal'));
    for (let i = 0; i < PROFILE.particles; i += 1) particles.push(spawnParticle());
    seedNeon();
  }

  function drawProp(item) {
    ctx.save();
    ctx.translate(item.x, item.y);
    ctx.rotate(item.rotation);
    ctx.globalAlpha = Math.max(0.06, item.alpha);

    const s = item.size;
    if (item.type === 'popcorn') {
      ctx.fillStyle = 'rgba(245, 223, 157, 0.7)';
      ctx.beginPath();
      ctx.arc(-s * 0.2, -s * 0.05, s * 0.26, 0, Math.PI * 2);
      ctx.arc(s * 0.08, -s * 0.1, s * 0.24, 0, Math.PI * 2);
      ctx.arc(0, s * 0.1, s * 0.22, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(224, 56, 92, 0.6)';
      ctx.fillRect(-s * 0.24, s * 0.12, s * 0.48, s * 0.25);
    } else if (item.type === 'nachos') {
      ctx.fillStyle = 'rgba(255, 178, 76, 0.7)';
      ctx.beginPath();
      ctx.moveTo(-s * 0.33, s * 0.22);
      ctx.lineTo(0, -s * 0.32);
      ctx.lineTo(s * 0.33, s * 0.22);
      ctx.closePath();
      ctx.fill();
      ctx.fillStyle = 'rgba(247, 92, 72, 0.35)';
      ctx.fillRect(-s * 0.07, -s * 0.02, s * 0.14, s * 0.11);
    } else if (item.type === 'ticket') {
      ctx.fillStyle = 'rgba(75, 108, 204, 0.65)';
      ctx.beginPath();
      ctx.roundRect(-s * 0.36, -s * 0.2, s * 0.72, s * 0.4, 8);
      ctx.fill();
      ctx.fillStyle = 'rgba(180, 208, 255, 0.7)';
      ctx.fillRect(-s * 0.16, -s * 0.02, s * 0.32, s * 0.06);
    } else {
      ctx.fillStyle = 'rgba(185, 202, 226, 0.55)';
      ctx.beginPath();
      ctx.roundRect(-s * 0.18, -s * 0.34, s * 0.36, s * 0.6, 12);
      ctx.fill();
      ctx.fillStyle = 'rgba(229, 64, 97, 0.72)';
      ctx.fillRect(-s * 0.03, -s * 0.44, s * 0.06, s * 0.22);
    }
    ctx.restore();
  }

  function drawParticle(p, t) {
    const pulse = 0.75 + Math.sin(t * p.pulse + p.phase) * 0.25;
    const radius = p.radius * pulse;
    const grad = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, radius * 3.8);
    const color = p.hue === 345 ? `248, 66, 115` : `61, 162, 255`;
    grad.addColorStop(0, `rgba(${color}, ${p.alpha})`);
    grad.addColorStop(1, `rgba(${color}, 0)`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(p.x, p.y, radius * 3.8, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawNeonGlow(band) {
    const grad = ctx.createRadialGradient(band.x, band.y, 0, band.x, band.y, band.radius);
    grad.addColorStop(0, band.color);
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(band.x, band.y, band.radius, 0, Math.PI * 2);
    ctx.fill();
  }

  function updateEntities(dt, ts) {
    const slowParallaxX = mouseX * 22;
    const slowParallaxY = mouseY * 12;

    for (let i = 0; i < neonBands.length; i += 1) {
      const n = neonBands[i];
      n.x += n.driftX * dt;
      n.y += n.driftY * dt;
      if (n.x < -n.radius) n.x = SIZE.width + n.radius;
      if (n.x > SIZE.width + n.radius) n.x = -n.radius;
      if (n.y < -n.radius) n.y = SIZE.height + n.radius;
      if (n.y > SIZE.height + n.radius) n.y = -n.radius;

      const px = n.x + slowParallaxX * n.depth;
      const py = n.y + slowParallaxY * n.depth;
      drawNeonGlow({ x: px, y: py, radius: n.radius, color: n.color });
    }

    for (let i = props.length - 1; i >= 0; i -= 1) {
      const item = props[i];
      item.vx += item.ax * dt;
      item.vy += item.ay * dt;
      item.driftWave += 0.01 * dt;
      item.x += (item.vx + Math.sin(item.driftWave) * item.driftAmp) * dt;
      item.y += item.vy * dt;
      item.rotation += item.vr * dt;

      // Soft damping for launches (ease out)
      if (item.mode === 'launch') {
        item.vx *= 0.992;
        item.vr *= 0.996;
        if (item.vy > 1.2) item.mode = 'fall';
      }

      const px = item.x + slowParallaxX * item.depth * 0.26;
      const py = item.y + slowParallaxY * item.depth * 0.18;
      drawProp({ ...item, x: px, y: py });

      if (item.y > SIZE.height + 120 || item.x < -140 || item.x > SIZE.width + 140) {
        props[i] = spawnProp('normal');
      }
    }

    for (let i = particles.length - 1; i >= 0; i -= 1) {
      const p = particles[i];
      p.vy += p.ay * dt;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.alpha *= 0.9994;
      if (p.kind === 'flare') p.alpha *= 0.9984;

      const px = p.x + slowParallaxX * p.depth * 0.1;
      const py = p.y + slowParallaxY * p.depth * 0.07;
      drawParticle({ ...p, x: px, y: py }, ts * 0.001);

      if (p.y > SIZE.height + 40 || p.x < -60 || p.x > SIZE.width + 60 || p.alpha < 0.03) {
        particles[i] = spawnParticle();
      }
    }

    if (ts - lastLaunchAt > PROFILE.launchEveryMs) {
      lastLaunchAt = ts;
      if (props.length) {
        const replaceIndex = Math.floor(Math.random() * props.length);
        props[replaceIndex] = spawnProp('launch');
      }
    }
  }

  function frame(ts) {
    if (!inView) return;
    const dt = Math.min(2.5, (ts - lastTs) / 16.67);
    lastTs = ts;

    mouseX += (targetMouseX - mouseX) * 0.06;
    mouseY += (targetMouseY - mouseY) * 0.06;

    ctx.clearRect(0, 0, SIZE.width, SIZE.height);
    updateEntities(dt, ts);
    rafId = requestAnimationFrame(frame);
  }

  function start() {
    if (rafId) cancelAnimationFrame(rafId);
    lastTs = performance.now();
    rafId = requestAnimationFrame(frame);
  }

  function stop() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
  }

  function onPointerMove(event) {
    if (!hasFinePointer || isMobile) return;
    const x = event.clientX / Math.max(1, SIZE.width);
    const y = event.clientY / Math.max(1, SIZE.height);
    targetMouseX = (x - 0.5) * 2;
    targetMouseY = (y - 0.5) * 2;
  }

  resize();
  resetPools();
  start();

  window.addEventListener('resize', function () {
    resize();
    resetPools();
  }, { passive: true });

  window.addEventListener('mousemove', onPointerMove, { passive: true });
  window.addEventListener('pointermove', onPointerMove, { passive: true });

  document.addEventListener('visibilitychange', function () {
    inView = !document.hidden;
    if (inView) start();
    else stop();
  });
})();
