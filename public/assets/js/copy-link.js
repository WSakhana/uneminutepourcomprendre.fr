// Boutons « Copier le lien » (sources externes et titres de section) : le bouton est caché dans le HTML et n'apparaît que si le JavaScript tourne.
(function () {
  var buttons = document.querySelectorAll(".copy-btn");
  if (!buttons.length) return;

  var status = document.getElementById("copy-status");

  // Lien d'une source (data-copy) ou lien d'une section de cette page (data-copy-anchor), sur l'adresse canonique du site.
  function textFor(btn) {
    var anchor = btn.getAttribute("data-copy-anchor");
    if (!anchor) return btn.getAttribute("data-copy");
    var canonical = document.querySelector('link[rel="canonical"]');
    var base = canonical ? canonical.href : location.origin + location.pathname;
    return base.split("#")[0] + "#" + anchor;
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(field);
      ok ? resolve() : reject(new Error("copy failed"));
    });
  }

  buttons.forEach(function (btn) {
    btn.hidden = false;
    var timer;
    btn.addEventListener("click", function () {
      copyText(textFor(btn)).then(function () {
        btn.classList.add("is-copied");
        var original = btn.getAttribute("data-title") || btn.title;
        btn.setAttribute("data-title", original);
        btn.title = "Lien copié";
        if (status) status.textContent = "Lien copié dans le presse-papiers.";
        clearTimeout(timer);
        timer = setTimeout(function () {
          btn.classList.remove("is-copied");
          btn.title = btn.getAttribute("data-title");
          if (status) status.textContent = "";
        }, 2200);
      }, function () {
        if (status) status.textContent = "Copie impossible : sélectionnez le lien manuellement.";
      });
    });
  });
})();
