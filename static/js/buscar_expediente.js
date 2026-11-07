// Sugerencias del buscador de expedientes, desde los datos académicos. Solo
// sugiere: no rellena el expediente ni resuelve nada. La URL llega en
// `data-url` del propio <script> (la CSP de producción no deja scripts en línea).
(function () {
  "use strict";
  var URL_SUGERENCIAS = document.currentScript && document.currentScript.getAttribute("data-url");
  if (!URL_SUGERENCIAS) return;

  function conectar(idCampo, idLista, formato) {
    var campo = document.getElementById(idCampo);
    var lista = document.getElementById(idLista);
    if (!campo || !lista) return;

    var temporizador = null;
    campo.addEventListener("input", function () {
      // Se espera a que deje de teclear: una consulta por pulsación
      // convertiría el buscador en un martillo contra la base.
      clearTimeout(temporizador);
      var texto = campo.value.trim();
      if (texto.length < 3) { lista.textContent = ""; return; }
      temporizador = setTimeout(function () {
        fetch(URL_SUGERENCIAS + "?q=" + encodeURIComponent(texto), { credentials: "same-origin" })
          .then(function (r) { return r.ok ? r.json() : { resultados: [] }; })
          .then(function (datos) {
            lista.textContent = "";
            (datos.resultados || []).forEach(function (p) {
              var opcion = document.createElement("option");
              opcion.value = formato(p).valor;
              opcion.label = formato(p).etiqueta;
              lista.appendChild(opcion);
            });
          })
          .catch(function () { lista.textContent = ""; });
      }, 250);
    });
  }

  conectar("cedula", "sugerencias-cedula", function (p) {
    return { valor: p.cedula, etiqueta: p.nombre_completo + (p.carrera ? " — " + p.carrera : "") };
  });
  conectar("nombre", "sugerencias-nombre", function (p) {
    return { valor: p.nombre_completo, etiqueta: p.cedula + (p.carrera ? " — " + p.carrera : "") };
  });
})();
