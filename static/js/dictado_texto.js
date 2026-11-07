/*
 * Dictado por voz: lo que se hace con el TEXTO, sin tocar el DOM.
 * ────────────────────────────────────────────────────────────────────
 * Adaptado del dictado de clinube. El profesional dice la palabra clave
 * del campo y luego su contenido:
 *
 *     «Enfermedad actual… dolor abdominal de tres días»
 *     «Plan… hidratación oral coma control en una semana»
 *
 * La palabra clave solo cuenta si ABRE una frase (el reconocedor entrega
 * el dictado por frases, tras cada pausa): «el plan de la semana…» a mitad
 * de frase se queda en el campo en que estaba.
 *
 * A diferencia de clinube, las secciones no están escritas aquí: cada
 * formulario declara sus campos con `data-dictado-campo` y sus palabras
 * clave con `data-dictado-claves`, porque Medicina, Odontología y
 * Psicopedagogía no anotan lo mismo.
 *
 * Se carga como script clásico (la CSP de producción no deja scripts en
 * línea y el almacenamiento con manifiesto no reescribe `import`), y en
 * Node como módulo CommonJS para probarlo con `node --test`.
 */
(function (raiz) {
  "use strict";

  /** Minúsculas y sin tildes, para comparar lo que dice el reconocedor. */
  function normalizar(texto) {
    return (texto || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
  }

  /*
   * Puntuación dictada. Solo las fórmulas explícitas: «punto» a secas no,
   * porque es palabra corriente («punto de contacto», «punto doloroso»).
   * El orden importa: «punto y coma» antes que «coma».
   */
  var PUNTUACION = [
    [/\s*\bpunto y aparte\b\s*/gi, ".\n"],
    [/\s*\bnueva l[ií]nea\b\s*/gi, "\n"],
    [/\s*\bpunto y coma\b\s*/gi, "; "],
    [/\s*\bpunto y seguido\b\s*/gi, ". "],
    [/\s*\bpunto final\b\s*/gi, ". "],
    [/\s*\bdos puntos\b\s*/gi, ": "],
    [/\s*\bcoma\b\s*/gi, ", "],
    [/\s*\babr(?:e|ir) par[eé]ntesis\b\s*/gi, " ("],
    [/\s*\bcierr(?:a|e|ar) par[eé]ntesis\b/gi, ")"],
  ];

  function aplicarPuntuacion(texto) {
    var t = texto || "";
    PUNTUACION.forEach(function (par) { t = t.replace(par[0], par[1]); });
    return t.replace(/[ \t]+/g, " ").replace(/ +\n/g, "\n").replace(/ ([,;:.)])/g, "$1").trim()
      // Mayúscula tras un punto dictado. Solo con espacio o salto detrás:
      // «www.unl.edu.ec» se queda como está.
      .replace(/(\.\s+|\n\s*)(\p{Ll})/gu, function (_, antes, letra) { return antes + letra.toUpperCase(); });
  }

  /*
   * Piezas dentales en notación FDI. El reconocedor entrega «pieza 4 6» o
   * «pieza cuatro seis». Solo se juntan dos cifras de 1 a 8 detrás de una
   * palabra que nombra un diente (o de otra pieza en una lista), para no
   * tocar «2 3 veces al día».
   */
  var CIFRA = { uno: "1", dos: "2", tres: "3", cuatro: "4", cinco: "5", seis: "6", siete: "7", ocho: "8" };
  var DIGITO = "([1-8]|uno|dos|tres|cuatro|cinco|seis|siete|ocho)";
  var PIEZA = new RegExp(
    "\\b(piezas?|dientes?|molar(?:es)?|premolar(?:es)?|caninos?|incisivos?|[1-8]{2}(?:,| y| e))\\s+" +
      DIGITO + "\\s+" + DIGITO + "\\b",
    "giu"
  );

  function unirPiezas(texto) {
    var anterior;
    var t = texto;
    do {
      anterior = t;
      t = t.replace(PIEZA, function (_, nombre, a, b) {
        return nombre + " " + (CIFRA[a.toLowerCase()] || a) + (CIFRA[b.toLowerCase()] || b);
      });
    } while (t !== anterior);
    return t;
  }

  function capitalizar(t) {
    return t ? t.charAt(0).toUpperCase() + t.slice(1) : t;
  }

  /** Todo lo que se hace al texto dictado de un campo. */
  function pulir(texto) {
    return capitalizar(unirPiezas(aplicarPuntuacion(texto)));
  }

  /**
   * Añade una frase final. Chrome en Android entrega cada frase final
   * REPITIENDO la anterior («dolor», luego «dolor abdominal»): si la nueva
   * empieza por la última, la sustituye; si es idéntica, se ignora.
   */
  function agregarFrase(lista, frase) {
    var nueva = (frase || "").trim();
    if (!nueva) return lista;
    var ultima = lista[lista.length - 1];
    if (ultima) {
      var a = normalizar(ultima);
      var b = normalizar(nueva);
      if (a === b) return lista;
      if (b.indexOf(a + " ") === 0) return lista.slice(0, -1).concat([nueva]);
    }
    return lista.concat([nueva]);
  }

  /**
   * ¿La frase empieza por la palabra clave de una sección? Devuelve
   * { seccion, resto } o null. Se prueban primero las claves más largas:
   * «plan de tratamiento» antes que «plan».
   */
  function detectarSeccion(frase, secciones) {
    var limpia = normalizar(frase).replace(/^[\s,.:;-]+/, "");
    var candidatas = [];
    secciones.forEach(function (s) {
      s.claves.forEach(function (c) { candidatas.push({ seccion: s.clave, clave: normalizar(c) }); });
    });
    candidatas.sort(function (x, y) { return y.clave.length - x.clave.length; });
    for (var i = 0; i < candidatas.length; i++) {
      var n = candidatas[i].clave;
      if (!n) continue;
      if (limpia === n || [" ", ":", ","].some(function (sep) { return limpia.indexOf(n + sep) === 0; })) {
        // Se corta sobre la frase ORIGINAL para conservar mayúsculas y
        // tildes del contenido: se cuentan las palabras de la clave.
        var palabras = n.split(" ").length;
        var resto = frase.trim().replace(/^[\s,.:;-]+/, "").split(/\s+/).slice(palabras).join(" ")
          .replace(/^(dos puntos\s*)/i, "").replace(/^[\s,.:;-]+/, "");
        return { seccion: candidatas[i].seccion, resto: resto };
      }
    }
    return null;
  }

  /**
   * Reparte las frases entre las secciones. Si la primera no nombra
   * ninguna, se empieza en `inicial` (por omisión, la primera sección).
   * Devuelve { clave: texto } solo de las secciones con contenido.
   */
  function organizarDictado(frases, secciones, inicial) {
    var partes = {};
    secciones.forEach(function (s) { partes[s.clave] = []; });
    var actual = inicial || (secciones[0] && secciones[0].clave);
    frases.forEach(function (bruta) {
      var frase = (bruta || "").trim();
      if (!frase) return;
      var d = detectarSeccion(frase, secciones);
      if (d) {
        actual = d.seccion;
        if (d.resto) partes[actual].push(d.resto);
      } else if (actual in partes) {
        partes[actual].push(frase);
      }
    });
    var salida = {};
    Object.keys(partes).forEach(function (k) {
      var texto = pulir(partes[k].join(" "));
      if (texto) salida[k] = texto;
    });
    return salida;
  }

  /**
   * Lo dictado se AÑADE a lo que ya hay en el campo, nunca lo sustituye:
   * dictar dos veces no borra la primera. En un campo de una línea los
   * saltos se vuelven espacios, que un <input> los descartaría en silencio.
   */
  function combinar(existente, nuevo, unaLinea) {
    var n = unaLinea ? nuevo.replace(/\s*\n\s*/g, " ") : nuevo;
    var e = (existente || "").replace(/\s+$/, "");
    if (!e) return n;
    return e + (unaLinea ? " " : "\n") + n;
  }

  var api = {
    normalizar: normalizar,
    aplicarPuntuacion: aplicarPuntuacion,
    unirPiezas: unirPiezas,
    pulir: pulir,
    agregarFrase: agregarFrase,
    detectarSeccion: detectarSeccion,
    organizarDictado: organizarDictado,
    combinar: combinar,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else raiz.SibuDictadoTexto = api;
})(this);
