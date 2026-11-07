// Marcar una foto del expediente: flechas, círculos, rectángulos, texto, lápiz.
//
// Traído de clinube (lib/AnotadorFoto.js, lib/anotacion.mjs). Las marcas se
// guardan en COORDENADAS DE LA IMAGEN, no de la pantalla: no se mueven al
// cambiar el tamaño de la ventana y al guardar se dibujan sobre la foto a su
// resolución completa. El grosor es una fracción del lado mayor de la foto,
// para que un trazo «medio» se vea igual en una foto de móvil que en una de
// cámara.
//
// Se guarda como PNG y como documento NUEVO: la foto original queda intacta.

"use strict";

(function () {
  var lienzo = document.getElementById("lienzo");
  if (!lienzo) return;
  var ctx = lienzo.getContext("2d");
  var foto = new Image();
  var marcas = [];
  var actual = null;
  var herramienta = "lapiz";
  var colorEl = document.getElementById("color");
  var grosorEl = document.getElementById("grosor");

  function grosor() {
    return Math.max(2, parseFloat(grosorEl.value) * Math.max(lienzo.width, lienzo.height));
  }

  function aImagen(evento) {
    var r = lienzo.getBoundingClientRect();
    return {
      x: (evento.clientX - r.left) * (lienzo.width / r.width),
      y: (evento.clientY - r.top) * (lienzo.height / r.height),
    };
  }

  function dibujarMarca(m) {
    ctx.save();
    ctx.strokeStyle = m.color;
    ctx.fillStyle = m.color;
    ctx.lineWidth = m.grosor;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (m.tipo === "lapiz") {
      ctx.beginPath();
      m.puntos.forEach(function (p, i) { if (i) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y); });
      ctx.stroke();
    } else if (m.tipo === "rectangulo") {
      ctx.strokeRect(m.a.x, m.a.y, m.b.x - m.a.x, m.b.y - m.a.y);
    } else if (m.tipo === "circulo") {
      ctx.beginPath();
      ctx.ellipse((m.a.x + m.b.x) / 2, (m.a.y + m.b.y) / 2,
                  Math.abs(m.b.x - m.a.x) / 2 || 1, Math.abs(m.b.y - m.a.y) / 2 || 1, 0, 0, 2 * Math.PI);
      ctx.stroke();
    } else if (m.tipo === "flecha") {
      var angulo = Math.atan2(m.b.y - m.a.y, m.b.x - m.a.x);
      var punta = m.grosor * 4;
      ctx.beginPath();
      ctx.moveTo(m.a.x, m.a.y);
      ctx.lineTo(m.b.x, m.b.y);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(m.b.x, m.b.y);
      ctx.lineTo(m.b.x - punta * Math.cos(angulo - 0.45), m.b.y - punta * Math.sin(angulo - 0.45));
      ctx.lineTo(m.b.x - punta * Math.cos(angulo + 0.45), m.b.y - punta * Math.sin(angulo + 0.45));
      ctx.closePath();
      ctx.fill();
    } else if (m.tipo === "texto") {
      var tam = m.grosor * 6;
      ctx.font = "bold " + tam + "px sans-serif";
      ctx.lineWidth = Math.max(2, tam / 8);
      ctx.strokeStyle = "#ffffff";
      ctx.strokeText(m.texto, m.a.x, m.a.y);   // borde blanco: se lee sobre cualquier fondo
      ctx.fillText(m.texto, m.a.x, m.a.y);
    }
    ctx.restore();
  }

  function redibujar() {
    ctx.clearRect(0, 0, lienzo.width, lienzo.height);
    ctx.drawImage(foto, 0, 0);
    marcas.forEach(dibujarMarca);
    if (actual) dibujarMarca(actual);
  }

  foto.onload = function () {
    lienzo.width = foto.naturalWidth;
    lienzo.height = foto.naturalHeight;
    redibujar();
  };
  foto.src = lienzo.getAttribute("data-imagen");

  document.querySelectorAll("[data-herramienta]").forEach(function (b) {
    b.addEventListener("click", function () {
      herramienta = b.getAttribute("data-herramienta");
      document.querySelectorAll("[data-herramienta]").forEach(function (x) { x.classList.toggle("active", x === b); });
    });
  });

  lienzo.addEventListener("pointerdown", function (e) {
    var p = aImagen(e);
    var base = { tipo: herramienta, color: colorEl.value, grosor: grosor() };
    if (herramienta === "texto") {
      var texto = window.prompt("Texto de la marca:");
      if (texto) { base.a = p; base.texto = texto; marcas.push(base); redibujar(); }
      return;
    }
    lienzo.setPointerCapture(e.pointerId);
    actual = herramienta === "lapiz" ? Object.assign(base, { puntos: [p] }) : Object.assign(base, { a: p, b: p });
  });
  lienzo.addEventListener("pointermove", function (e) {
    if (!actual) return;
    var p = aImagen(e);
    if (actual.tipo === "lapiz") actual.puntos.push(p); else actual.b = p;
    redibujar();
  });
  function soltar() {
    if (actual) { marcas.push(actual); actual = null; redibujar(); }
  }
  lienzo.addEventListener("pointerup", soltar);
  lienzo.addEventListener("pointercancel", soltar);

  document.getElementById("deshacer").addEventListener("click", function () { marcas.pop(); redibujar(); });
  document.getElementById("limpiar").addEventListener("click", function () {
    if (marcas.length && window.confirm("¿Quitar todas las marcas?")) { marcas = []; redibujar(); }
  });

  document.getElementById("guardar-marcas").addEventListener("submit", function (e) {
    e.preventDefault();
    if (!marcas.length) { window.alert("Todavía no hay ninguna marca."); return; }
    var form = e.target;
    var boton = document.getElementById("boton-guardar");
    boton.disabled = true;
    lienzo.toBlob(function (blob) {
      var datos = new FormData(form);
      datos.append("imagen", blob, "marcada.png");
      fetch(window.location.href, { method: "POST", body: datos, credentials: "same-origin" })
        .then(function (r) { window.location.href = r.url; })
        .catch(function () { boton.disabled = false; window.alert("No se pudo guardar. Revise la conexión."); });
    }, "image/png");
  });
})();
