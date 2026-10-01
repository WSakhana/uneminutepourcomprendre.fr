// Confort de navigation, ajouté par JavaScript : défilement lent vers les ancres, bouton « Remonter en haut » et barre de progression de lecture des articles.
(function () {
  var root = document.documentElement;
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var cancel = null;

  function ease(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  // Défilement animé : plus la distance est grande, plus il dure (entre 0,9 et 1,8 s). Toute action de l'utilisateur l'interrompt.
  function scrollToY(y, done) {
    if (cancel) cancel();
    var start = window.pageYOffset;
    var distance = y - start;
    if (reduced || Math.abs(distance) < 2) {
      window.scrollTo(0, y);
      if (done) done();
      return;
    }
    var duration = Math.min(1800, Math.max(900, Math.abs(distance) * 0.7));
    var begin = null;
    var frame;
    var events = ["wheel", "touchstart", "keydown", "mousedown"];

    function stop() {
      cancelAnimationFrame(frame);
      events.forEach(function (name) { window.removeEventListener(name, stop); });
      root.style.scrollBehavior = "";
      cancel = null;
    }

    function step(now) {
      if (begin === null) begin = now;
      var t = Math.min(1, (now - begin) / duration);
      window.scrollTo(0, start + distance * ease(t));
      if (t < 1) {
        frame = requestAnimationFrame(step);
      } else {
        stop();
        if (done) done();
      }
    }

    root.style.scrollBehavior = "auto"; // le défilement CSS « smooth » rendrait chaque pas de l'animation lui-même animé
    events.forEach(function (name) { window.addEventListener(name, stop, { passive: true }); });
    cancel = stop;
    frame = requestAnimationFrame(step);
  }

  // Liens vers une ancre de la page courante (#univers ou /#univers depuis l'accueil).
  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    var link = event.target.closest && event.target.closest("a[href]");
    if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
    var url;
    try { url = new URL(link.href, location.href); } catch (e) { return; }
    if (url.origin !== location.origin || url.pathname !== location.pathname || url.search !== location.search || !url.hash) return;
    var id = decodeURIComponent(url.hash.slice(1));
    var target = id ? document.getElementById(id) : null;
    if (!target) return;
    event.preventDefault();
    var margin = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
    var y = Math.max(0, target.getBoundingClientRect().top + window.pageYOffset - margin);
    scrollToY(y, function () {
      if (location.hash !== url.hash) history.pushState(null, "", url.hash);
      if (!target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
    });
  });

  // Bouton « Remonter en haut » : apparaît après un écran de défilement.
  var top = document.createElement("button");
  top.type = "button";
  top.className = "to-top";
  top.setAttribute("aria-label", "Remonter en haut de la page");
  top.title = "Remonter en haut";
  top.innerHTML = '<svg class="icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24"><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  top.addEventListener("click", function () {
    scrollToY(0, function () {
      if (location.hash) history.replaceState(null, "", location.pathname + location.search);
      var skip = document.querySelector(".skip-link");
      if (skip) skip.focus({ preventScroll: true });
    });
  });
  document.body.appendChild(top);

  // Barre de progression de lecture, sur les pages d'articles uniquement.
  var article = document.querySelector("article.article, .article-header");
  var bar = null;
  if (article) {
    bar = document.createElement("div");
    bar.className = "read-progress";
    bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);
  }

  var ticking = false;
  function update() {
    ticking = false;
    var y = window.pageYOffset;
    top.classList.toggle("is-visible", y > Math.max(500, window.innerHeight * 0.6));
    if (bar) {
      var max = root.scrollHeight - window.innerHeight;
      bar.style.transform = "scaleX(" + (max > 0 ? Math.min(1, y / max) : 0) + ")";
    }
  }
  window.addEventListener("scroll", function () {
    if (!ticking) { ticking = true; requestAnimationFrame(update); }
  }, { passive: true });
  window.addEventListener("resize", update);
  update();
})();
