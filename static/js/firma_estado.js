// FirmaEC firma fuera del navegador y devuelve el PDF al servidor, no a esta
// pestaña: no hay evento que escuchar. Se consulta el estado hasta que llegue.
// La URL llega en `data-url` del propio <script>: la CSP de producción no deja
// scripts en línea.
(function () {
  "use strict";
  var url = document.currentScript && document.currentScript.getAttribute("data-url");
  if (!url) return;
  var intentos = 0;
  var timer = setInterval(function () {
    intentos++;
    if (intentos > 60) { clearInterval(timer); return; }   // ~5 min
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && (d.firmada || d.estado === "fallida")) {
          clearInterval(timer);
          window.location.reload();
        }
      })
      .catch(function () { /* reintenta en el siguiente ciclo */ });
  }, 5000);
})();
