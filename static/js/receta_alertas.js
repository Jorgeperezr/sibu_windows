// Al recetar, si el medicamento elegido choca con una alerta del expediente
// (`data-choque`, escrito por el servidor), se pregunta antes de enviarlo.
// Confirmar pone `acepto_alerta=1`; sin él, el servidor no lo añade.
(function () {
  "use strict";
  document.addEventListener("submit", function (evento) {
    var select = evento.target.querySelector && evento.target.querySelector("select[data-alerta-receta]");
    if (!select) return;
    var opcion = select.options[select.selectedIndex];
    var choque = opcion && opcion.getAttribute("data-choque");
    var acepto = evento.target.elements.acepto_alerta;
    if (!choque || !acepto) return;
    if (window.confirm("Atención: " + choque + "\n\n¿Recetarlo de todos modos?")) {
      acepto.value = "1";
    } else {
      evento.preventDefault();
    }
  }, true);
})();
