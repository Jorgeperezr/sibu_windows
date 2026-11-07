// JS común de SIBU. Va en un archivo, no en la plantilla: el CSP de
// producción (`script-src 'self'`) bloquea todo <script> en línea y todo
// onclick="..."/onsubmit="...". Con ellos en línea, en el servidor las
// confirmaciones no salían y la acción se ejecutaba sin preguntar.

"use strict";

// <form data-confirmar="¿Cerrar la atención?"> o <button data-confirmar="...">
document.addEventListener("submit", function (evento) {
  var form = evento.target;
  var boton = evento.submitter;
  var texto = (boton && boton.getAttribute("data-confirmar")) || form.getAttribute("data-confirmar");
  if (texto && !window.confirm(texto)) {
    evento.preventDefault();
  }
}, true);

document.addEventListener("click", function (evento) {
  var enlace = evento.target.closest("a[data-confirmar]");
  if (enlace && !window.confirm(enlace.getAttribute("data-confirmar"))) {
    evento.preventDefault();
  }
}, true);
