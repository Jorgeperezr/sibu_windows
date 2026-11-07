// Se ejecuta desde pytest (test_dictado.py) con `node --test`.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const T = require(path.join(__dirname, "..", "..", "..", "..", "static", "js", "dictado_texto.js"));

const MEDICINA = [
  { clave: "motivo_consulta", claves: ["motivo de consulta", "motivo"] },
  { clave: "enfermedad_actual", claves: ["enfermedad actual", "anamnesis"] },
  { clave: "plan_tratamiento", claves: ["plan", "tratamiento", "plan de tratamiento"] },
  { clave: "indicaciones", claves: ["indicaciones", "recomendaciones"] },
];

test("la puntuación dictada se escribe", () => {
  assert.equal(
    T.aplicarPuntuacion("dolor abdominal coma fiebre punto y seguido sin vómito punto y aparte control"),
    "dolor abdominal, fiebre. Sin vómito.\nControl"
  );
  assert.equal(T.aplicarPuntuacion("toma dos puntos paracetamol"), "toma: paracetamol");
  assert.equal(T.aplicarPuntuacion("reposo abre paréntesis dos días cierra paréntesis"), "reposo (dos días)");
});

test("«punto» a secas es una palabra, no un signo", () => {
  assert.equal(T.aplicarPuntuacion("punto doloroso en fosa ilíaca"), "punto doloroso en fosa ilíaca");
});

test("las piezas dentales salen en FDI y las cantidades no se tocan", () => {
  assert.equal(T.unirPiezas("caries en la pieza cuatro seis"), "caries en la pieza 46");
  assert.equal(T.unirPiezas("piezas 4 6 y 4 7"), "piezas 46 y 47");
  assert.equal(T.unirPiezas("cepillarse 2 3 veces al día"), "cepillarse 2 3 veces al día");
});

test("la clave solo cambia de campo si abre la frase", () => {
  const r = T.organizarDictado(
    [
      "dolor abdominal de tres días",
      "enfermedad actual inicia con dolor periumbilical",
      "el plan de la semana era viajar",
      "plan de tratamiento hidratación oral",
      "indicaciones dieta blanda",
    ],
    MEDICINA
  );
  assert.equal(r.motivo_consulta, "Dolor abdominal de tres días");
  assert.equal(r.enfermedad_actual, "Inicia con dolor periumbilical el plan de la semana era viajar");
  assert.equal(r.plan_tratamiento, "Hidratación oral", "la clave más larga gana: no queda «de tratamiento»");
  assert.equal(r.indicaciones, "Dieta blanda");
});

test("las secciones sin contenido no aparecen", () => {
  const r = T.organizarDictado(["indicaciones reposo"], MEDICINA);
  assert.deepEqual(Object.keys(r), ["indicaciones"]);
});

test("una frase repetida por el reconocedor no se duplica", () => {
  let l = T.agregarFrase([], "dolor");
  l = T.agregarFrase(l, "dolor abdominal");
  l = T.agregarFrase(l, "Dolor abdominal");
  assert.deepEqual(l, ["dolor abdominal"]);
});

test("lo dictado se añade, no sustituye, y en una línea no hay saltos", () => {
  assert.equal(T.combinar("Fiebre", "Tos", false), "Fiebre\nTos");
  assert.equal(T.combinar("Fiebre", "Tos.\nSeca", true), "Fiebre Tos. Seca");
  assert.equal(T.combinar("", "Tos", false), "Tos");
});
