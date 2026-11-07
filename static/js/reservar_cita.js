// Reservar una cita desde ventanilla. Las URL llegan en `data-*` del propio
// <script> (la CSP de producción no deja scripts en línea).
//
// Las opciones se construyen con el DOM, no con `innerHTML`: el nombre de un
// profesional o la etiqueta de un turno son texto, y como HTML un nombre con
// «<» se volvía marcado dentro de la pantalla de otra persona.
(function () {
  "use strict";
  var datos = document.currentScript ? document.currentScript.dataset : {};
  var $ = function (id) { return document.getElementById(id); };

  function opciones(select, lista) {
    select.textContent = "";
    lista.forEach(function (par) {
      var o = document.createElement("option");
      o.value = par[0];
      o.textContent = par[1];
      select.appendChild(o);
    });
  }

  $("btnBuscar").addEventListener("click", function () {
    var cedula = $("cedula").value.trim();
    if (!cedula) return;
    fetch(datos.urlPersona + "?cedula=" + encodeURIComponent(cedula), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var info = $("paciente");
        if (data.encontrado) {
          $("expediente").value = data.expediente_id;
          info.className = "form-text text-success";
          info.textContent = data.nombre + " (" + data.vinculo + ")";
        } else {
          $("expediente").value = "";
          info.className = "form-text text-danger";
          info.textContent = "No encontrado. Registre a la persona primero.";
        }
      });
  });

  $("servicio").addEventListener("change", function (e) {
    var sel = $("profesional");
    opciones(sel, [["", "Cargando…"]]);
    fetch(datos.urlProfesionales + "?servicio=" + encodeURIComponent(e.target.value), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        opciones(sel, [["", "— Seleccione —"]].concat(
          data.profesionales.map(function (p) { return [p.id, p.nombre]; })
        ));
      });
  });

  function cargarTurnos() {
    var prof = $("profesional").value;
    var serv = $("servicio").value;
    var fecha = $("fecha").value;
    var sel = $("fecha_hora");
    if (!(prof && serv && fecha)) return;
    opciones(sel, [["", "Consultando…"]]);
    var q = "?profesional=" + encodeURIComponent(prof) + "&servicio=" + encodeURIComponent(serv) +
      "&fecha=" + encodeURIComponent(fecha);
    fetch(datos.urlDisponibilidad + q, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.turnos || !data.turnos.length) {
          opciones(sel, [["", "Sin turnos disponibles"]]);
          return;
        }
        // La hora la dice el servidor. `toLocaleString` la sacaba de la zona
        // horaria DEL EQUIPO: en uno mal configurado el desplegable ofrecía
        // «02:00 p. m.» para el turno de las 09:00.
        opciones(sel, [["", "— Seleccione turno —"]].concat(
          data.turnos.map(function (t, i) { return [t, (data.etiquetas && data.etiquetas[i]) || t]; })
        ));
      });
  }
  ["profesional", "fecha"].forEach(function (id) { $(id).addEventListener("change", cargarTurnos); });
})();
