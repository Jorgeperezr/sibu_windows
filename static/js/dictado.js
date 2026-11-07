/*
 * Botón de dictado de un formulario clínico (Web Speech API del navegador).
 * ────────────────────────────────────────────────────────────────────
 * Lo que se le dice al usuario en pantalla y conviene saber: el navegador
 * NO transcribe en el equipo. Chrome y Edge envían el audio a Google o
 * Microsoft; Safari, a Apple. Firefox no lo soporta. Y solo funciona en un
 * «contexto seguro»: https o el propio equipo (localhost). En la versión
 * portable compartida por WiFi, los compañeros entran por http://192.168…
 * y ahí el navegador lo niega: se avisa en lugar de fallar en silencio.
 *
 * El texto NO se guarda solo: al detener se AÑADE a los campos y el
 * profesional lo revisa antes de pulsar Guardar. Mientras se escucha, el
 * formulario no se envía: lo dictado aún no está en los campos.
 *
 * El panel lo pinta `{% dictado %}` (apps/core/templatetags/dictado.py),
 * que se niega en los servicios confidenciales.
 */
(function () {
  "use strict";
  var T = window.SibuDictadoTexto;
  if (!T) return;

  var ERRORES = {
    "not-allowed": "El navegador no tiene permiso para usar el micrófono. Actívalo en el candado de la barra de direcciones.",
    "service-not-allowed": "El navegador no permite dictar en esta dirección: hace falta https o abrir SIBU en el propio equipo (localhost).",
    "audio-capture": "No se encontró ningún micrófono.",
    network: "No hay conexión con el servicio de voz del navegador. El dictado necesita internet.",
    "language-not-supported": "El navegador no reconoce el español en este equipo.",
  };

  function reconocedor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function idioma() {
    var nav = (navigator.language || "").toLowerCase();
    return nav.indexOf("es") === 0 ? navigator.language : "es-EC";
  }

  function iniciarPanel(panel) {
    var form = panel.closest("form");
    if (!form) return;
    var campos = Array.prototype.filter.call(
      form.querySelectorAll("[data-dictado-campo]"),
      function (c) { return !c.disabled && !c.readOnly; }
    );
    if (!campos.length) return; // atención cerrada: nada que dictar
    var secciones = campos.map(function (c) {
      return {
        clave: c.name,
        titulo: c.getAttribute("data-dictado-titulo") || c.name,
        claves: (c.getAttribute("data-dictado-claves") || "").split("|").filter(Boolean),
        campo: c,
      };
    });

    var boton = panel.querySelector("[data-dictado-boton]");
    var estado = panel.querySelector("[data-dictado-estado]");
    var vista = panel.querySelector("[data-dictado-vista]");
    var mensaje = panel.querySelector("[data-dictado-mensaje]");
    panel.hidden = false;

    function avisar(texto) {
      mensaje.textContent = texto || "";
      mensaje.classList.toggle("d-none", !texto);
    }

    var Clase = reconocedor();
    if (!Clase) {
      boton.disabled = true;
      avisar("Este navegador no permite dictar. Usa Chrome, Edge o Safari.");
      return;
    }
    if (window.isSecureContext === false) {
      boton.disabled = true;
      avisar(ERRORES["service-not-allowed"]);
      return;
    }

    var rec = null;
    var activo = false;     // el usuario quiere seguir dictando
    var escuchando = false;
    var frases = [];
    var parcial = "";
    var reintentos = 0;

    function titulo(clave) {
      for (var i = 0; i < secciones.length; i++) if (secciones[i].clave === clave) return secciones[i].titulo;
      return clave;
    }

    function pintar() {
      boton.textContent = escuchando ? "Detener dictado" : "Dictar";
      boton.classList.toggle("btn-danger", escuchando);
      boton.classList.toggle("btn-outline-secondary", !escuchando);
      boton.setAttribute("aria-pressed", escuchando ? "true" : "false");
      vista.classList.toggle("d-none", !escuchando);
      if (!escuchando) { estado.textContent = ""; return; }
      var todas = parcial ? frases.concat([parcial]) : frases;
      var actual = secciones[0].clave;
      todas.forEach(function (f) {
        var d = T.detectarSeccion(f, secciones);
        if (d) actual = d.seccion;
      });
      estado.textContent = secciones.length > 1 ? "Escribiendo en: " + titulo(actual) : "Escuchando…";
      var organizado = T.organizarDictado(todas, secciones);
      vista.textContent = "";
      secciones.forEach(function (s) {
        var linea = document.createElement("div");
        var fuerte = document.createElement("strong");
        fuerte.textContent = s.titulo + ": ";
        linea.appendChild(fuerte);
        linea.appendChild(document.createTextNode(organizado[s.clave] || "—"));
        if (!organizado[s.clave]) linea.className = "text-muted";
        vista.appendChild(linea);
      });
    }

    function entregar() {
      if (!frases.length) return;
      var organizado = T.organizarDictado(frases, secciones);
      secciones.forEach(function (s) {
        var nuevo = organizado[s.clave];
        if (!nuevo) return;
        var unaLinea = s.campo.tagName !== "TEXTAREA";
        var valor = T.combinar(s.campo.value, nuevo, unaLinea);
        var max = parseInt(s.campo.getAttribute("maxlength"), 10);
        if (max && valor.length > max) {
          avisar("«" + s.titulo + "» no admite más de " + max + " caracteres: revisa el final del texto.");
          valor = valor.slice(0, max);
        }
        s.campo.value = valor;
        s.campo.dispatchEvent(new Event("input", { bubbles: true }));
      });
      frases = [];
    }

    function terminar() {
      activo = false;
      escuchando = false;
      parcial = "";
      entregar();
      pintar();
    }

    // Chrome corta tras unos segundos de silencio aunque se le pida
    // continuo, y Safari a veces al minuto. Si el usuario no pulsó
    // Detener, se vuelve a arrancar; arrancar dentro del mismo `onend`
    // falla a menudo en Safari, así que se espera y se reintenta.
    function rearrancar() {
      setTimeout(function () {
        if (!activo) { terminar(); return; }
        try {
          rec.start();
          reintentos = 0;
        } catch (e) {
          if (++reintentos < 4) rearrancar();
          else {
            avisar("El navegador cortó el dictado. Lo dictado hasta ahora se añadió a los campos.");
            terminar();
          }
        }
      }, 250 * (reintentos + 1));
    }

    function empezar() {
      avisar("");
      rec = new Clase();
      rec.lang = idioma();
      rec.continuous = true;
      rec.interimResults = true;
      rec.onresult = function (e) {
        var interino = "";
        for (var i = e.resultIndex; i < e.results.length; i++) {
          var t = e.results[i][0].transcript;
          if (e.results[i].isFinal) frases = T.agregarFrase(frases, t);
          else interino += t;
        }
        parcial = interino.trim();
        pintar();
      };
      rec.onerror = function (e) {
        // «no-speech» es un silencio largo: no es un error para el usuario.
        if (e.error === "no-speech" || e.error === "aborted") return;
        activo = false;
        avisar(ERRORES[e.error] || "El dictado se detuvo (" + e.error + ").");
      };
      rec.onend = function () {
        if (activo) rearrancar();
        else terminar();
      };
      frases = [];
      parcial = "";
      activo = true;
      try {
        rec.start();
        escuchando = true;
      } catch (e) {
        activo = false;
        avisar("No se pudo iniciar el dictado.");
      }
      pintar();
    }

    function detener() {
      activo = false;
      // `stop` y no `abort`: deja llegar la última frase antes de `onend`,
      // que es donde se escribe en los campos.
      if (rec) rec.stop();
    }

    boton.addEventListener("click", function () {
      if (escuchando) detener();
      else empezar();
    });

    form.addEventListener("submit", function (e) {
      if (!escuchando) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      avisar("Detén el dictado antes de guardar: lo dictado todavía no está en los campos.");
    }, true);
  }

  function iniciar() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-dictado]"), iniciarPanel);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
