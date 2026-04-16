(function () {
  const shells = document.querySelectorAll('[data-rail-shell]');
  if (!shells.length) return;

  shells.forEach((shell) => {
    const viewport = shell.querySelector('[data-rail-viewport]');
    const prevButton = shell.querySelector('[data-rail-prev]');
    const nextButton = shell.querySelector('[data-rail-next]');

    if (!viewport || !prevButton || !nextButton) return;

    const updateButtons = () => {
      const maxScrollLeft = Math.max(0, viewport.scrollWidth - viewport.clientWidth);
      const canGoLeft = viewport.scrollLeft > 8;
      const canGoRight = viewport.scrollLeft < maxScrollLeft - 8;

      prevButton.disabled = !canGoLeft;
      nextButton.disabled = !canGoRight;
      shell.dataset.canLeft = canGoLeft ? '1' : '0';
      shell.dataset.canRight = canGoRight ? '1' : '0';
    };

    const scrollStep = () => Math.max(220, Math.round(viewport.clientWidth * 0.86));

    prevButton.addEventListener('click', () => {
      viewport.scrollBy({ left: -scrollStep(), behavior: 'smooth' });
    });

    nextButton.addEventListener('click', () => {
      viewport.scrollBy({ left: scrollStep(), behavior: 'smooth' });
    });

    viewport.addEventListener('scroll', updateButtons, { passive: true });
    window.addEventListener('resize', updateButtons);
    window.setTimeout(updateButtons, 80);
    updateButtons();
  });
})();
