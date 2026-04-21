/* StreamVerse cinematic effects v3
 * Countdown, narrative scroll contexts, reveal helpers, top scroll indicator.
 */
(function () {
  'use strict';

  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function initCountdown() {
    const overlay = document.getElementById('cinema-countdown');
    if (!overlay) return;

    const numberEl = document.getElementById('countdown-number');
    const skipBtn = document.getElementById('countdown-skip');
    const titleEl = document.getElementById('countdown-title');
    const ringFill = overlay.querySelector('.countdown-ring-fill');
    const player = document.getElementById('stream-player');
    const resumeBtn = document.getElementById('resume-btn');

    let total = Number(overlay.dataset.countdownTotal || 10);
    if (!Number.isFinite(total) || total < 1) total = 10;

    let current = total;
    let timer = null;
    const radius = 44;
    const circumference = 2 * Math.PI * radius;

    const titles = [
      'Ajustando proyector...',
      'Encendiendo luces de sala...',
      'Preparando sonido envolvente...',
      'Verificando foco de pantalla...',
      'Sincronizando ambiente...',
      'Calibrando contraste...',
      'Acomodando butacas...',
      'Cargando cinta...',
      'Todo listo...',
      'Comienza la funcion',
    ];

    if (ringFill) {
      ringFill.style.strokeDasharray = String(circumference);
      ringFill.style.strokeDashoffset = '0';
    }
    if (numberEl) numberEl.textContent = String(total);

    function updateRing(value) {
      if (!ringFill) return;
      const frac = Math.max(0, Math.min(1, value / total));
      ringFill.style.strokeDashoffset = String(circumference * (1 - frac));
    }

    function dismissAndPlay() {
      overlay.classList.add('sv-countdown--hiding');
      window.setTimeout(function () {
        overlay.style.display = 'none';
        if (resumeBtn) {
          resumeBtn.click();
          return;
        }
        if (player && typeof player.play === 'function') {
          player.play().catch(function () {});
        }
      }, 650);
    }

    function tick() {
      current -= 1;
      if (numberEl) numberEl.textContent = String(Math.max(current, 0));
      const titleIndex = Math.min(titles.length - 1, total - Math.max(current, 1));
      if (titleEl) titleEl.textContent = titles[titleIndex];
      updateRing(Math.max(current, 0));

      if (current <= 0) {
        clearInterval(timer);
        dismissAndPlay();
      }
    }

    if (skipBtn) {
      window.setTimeout(function () {
        skipBtn.classList.add('is-visible');
      }, 1100);
      skipBtn.addEventListener('click', function () {
        clearInterval(timer);
        dismissAndPlay();
      });
    }

    window.setTimeout(function () {
      timer = window.setInterval(tick, 1000);
    }, 450);
  }

  function initStaggerReveal() {
    if (reduceMotion) return;
    const targets = document.querySelectorAll('.reveal-stagger');
    if (!targets.length) return;

    const observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        const children = entry.target.children;
        for (let i = 0; i < children.length; i += 1) {
          children[i].style.transitionDelay = i * 60 + 'ms';
          children[i].classList.add('is-visible');
        }
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.08 });

    targets.forEach(function (el) {
      observer.observe(el);
    });
  }

  function initShimmer() {
    if (reduceMotion) return;
    const buttons = document.querySelectorAll('.btn-primary');
    buttons.forEach(function (button) {
      button.addEventListener('mouseenter', function (event) {
        const rect = button.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        button.style.setProperty('--shimmer-x', x.toFixed(1) + '%');
        button.style.setProperty('--shimmer-y', y.toFixed(1) + '%');
        button.classList.add('is-shimmering');
      });
      button.addEventListener('mouseleave', function () {
        button.classList.remove('is-shimmering');
      });
    });
  }

  function initScrollProgress() {
    const bar = document.getElementById('sv-scroll-bar');
    if (!bar) return;
    let pending = false;

    function draw() {
      pending = false;
      const root = document.documentElement;
      const max = Math.max(1, root.scrollHeight - root.clientHeight);
      const pct = Math.max(0, Math.min(100, (root.scrollTop / max) * 100));
      bar.style.width = pct.toFixed(2) + '%';
    }

    function onScroll() {
      if (pending) return;
      pending = true;
      requestAnimationFrame(draw);
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    draw();
  }

  function initNarrativeContext() {
    const markers = Array.from(document.querySelectorAll('[data-cinema-context-step]'));
    if (!markers.length) return;
    const body = document.body;
    let ticking = false;

    function resolveContext() {
      ticking = false;
      const anchor = window.innerHeight * 0.35;
      let selected = markers[0];
      let minDist = Infinity;

      for (let i = 0; i < markers.length; i += 1) {
        const rect = markers[i].getBoundingClientRect();
        const dist = Math.abs(rect.top - anchor);
        if (dist < minDist) {
          minDist = dist;
          selected = markers[i];
        }
      }

      const context = selected.getAttribute('data-cinema-context-step') || 'lobby';
      body.setAttribute('data-cinema-context', context);
    }

    function onScrollOrResize() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(resolveContext);
    }

    window.addEventListener('scroll', onScrollOrResize, { passive: true });
    window.addEventListener('resize', onScrollOrResize, { passive: true });
    resolveContext();
  }

  function initTitleReveal() {
    if (reduceMotion) return;
    const targets = document.querySelectorAll('.sv-title-reveal');
    if (!targets.length) return;

    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const text = el.textContent || '';
        el.textContent = '';
        for (let i = 0; i < text.length; i += 1) {
          const span = document.createElement('span');
          span.textContent = text[i] === ' ' ? '\u00A0' : text[i];
          span.style.display = 'inline-block';
          span.style.opacity = '0';
          span.style.transform = 'translateY(10px)';
          span.style.transition = 'opacity 320ms ease, transform 320ms cubic-bezier(0.22,1,0.36,1)';
          span.style.transitionDelay = i * 24 + 'ms';
          el.appendChild(span);
          requestAnimationFrame(function () {
            span.style.opacity = '1';
            span.style.transform = 'translateY(0)';
          });
        }
        io.unobserve(el);
      });
    }, { threshold: 0.2 });

    targets.forEach(function (el) {
      io.observe(el);
    });
  }

  initCountdown();
  initStaggerReveal();
  initShimmer();
  initScrollProgress();
  initNarrativeContext();
  initTitleReveal();
})();
