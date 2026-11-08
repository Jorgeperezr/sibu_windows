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
    return;
  }
  // <button data-pedir="Motivo del rechazo:" data-pedir-campo="motivo">:
  // pregunta y lo escribe en el campo oculto. Cancelar no envía: antes se
  // enviaba el rechazo con el motivo vacío.
  var pregunta = boton && boton.getAttribute("data-pedir");
  if (pregunta) {
    var respuesta = window.prompt(pregunta);
    if (respuesta === null) {
      evento.preventDefault();
      return;
    }
    var campo = form.elements[boton.getAttribute("data-pedir-campo")];
    if (campo) campo.value = respuesta;
  }
}, true);

// <select data-enviar-al-cambiar>: un filtro que se aplica al elegir.
document.addEventListener("change", function (evento) {
  var campo = evento.target;
  if (campo.hasAttribute && campo.hasAttribute("data-enviar-al-cambiar") && campo.form) {
    if (campo.form.requestSubmit) campo.form.requestSubmit();
    else campo.form.submit();
  }
});

// <input data-copiar-a="prof" data-copiar-valor="7">: al elegirlo, copia su
// valor a otro campo (el profesional del turno elegido).
document.addEventListener("change", function (evento) {
  var campo = evento.target;
  var destino = campo.getAttribute && campo.getAttribute("data-copiar-a");
  if (destino && document.getElementById(destino)) {
    document.getElementById(destino).value = campo.getAttribute("data-copiar-valor");
  }
});

document.addEventListener("click", function (evento) {
  var enlace = evento.target.closest("a[data-confirmar]");
  if (enlace && !window.confirm(enlace.getAttribute("data-confirmar"))) {
    evento.preventDefault();
  }
}, true);

// <button data-alternar-clave="id_password">: enseña u oculta la clave mientras
// se escribe (con un PIN es fácil equivocarse sin verlo). Al enviar el
// formulario se vuelve a ocultar: si alguien la deja a la vista y se levanta,
// no queda así en la pantalla siguiente. Traído de clinube.
document.addEventListener("click", function (evento) {
  var boton = evento.target.closest("[data-alternar-clave]");
  if (!boton) return;
  var campo = document.getElementById(boton.getAttribute("data-alternar-clave"));
  if (!campo) return;
  var ver = campo.type === "password";
  campo.type = ver ? "text" : "password";
  boton.setAttribute("aria-pressed", ver ? "true" : "false");
  boton.textContent = ver ? "Ocultar" : "Ver";
});
document.addEventListener("submit", function (evento) {
  Array.prototype.forEach.call(
    evento.target.querySelectorAll("[data-alternar-clave]"),
    function (boton) {
      var campo = document.getElementById(boton.getAttribute("data-alternar-clave"));
      if (campo) campo.type = "password";
    }
  );
}, true);

// <button data-imprimir>: la ventana de impresión del navegador, que también
// guarda como PDF. En la portable de Windows no hay WeasyPrint.
document.addEventListener("click", function (evento) {
  if (evento.target.closest("[data-imprimir]")) window.print();
});
