// El modal de una pieza del odontograma recibe la pieza y su estado del botón
// que lo abrió. En archivo y no en la plantilla: la CSP de producción no deja
// scripts en línea, y sin esto el modal envía la pieza vacía.
(function () {
  "use strict";
  var modal = document.getElementById("modalPieza");
  if (!modal) return;
  modal.addEventListener("show.bs.modal", function (event) {
    var btn = event.relatedTarget;
    if (!btn) return;
    var pieza = btn.getAttribute("data-pieza");
    var estado = btn.getAttribute("data-estado");
    document.getElementById("modalPiezaId").value = pieza;
    document.getElementById("modalPiezaTitulo").textContent = pieza;
    if (estado) document.getElementById("modalEstado").value = estado;
  });
})();
