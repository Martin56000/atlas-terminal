// Run with: node --test tests/js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const C = require("../../site/js/calc.js");

const SITE = path.join(__dirname, "..", "..", "site");
const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("sma: hand example", () => {
  // 3-day average of 1,2,3,4,5 -> -, -, 2, 3, 4
  assert.deepEqual(C.sma([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
});

test("pearson: perfect, inverse, undefined", () => {
  close(C.pearson([1, 2, 3], [2, 4, 6]), 1);
  close(C.pearson([1, 2, 3], [3, 2, 1]), -1);
  assert.equal(C.pearson([1, 1, 1], [1, 2, 3]), null); // zero variance: never invented
});

test("correlation matrix uses dates common to all tickers", () => {
  const series = {
    A: { dates: ["d1", "d2", "d3", "d4"], r: [0.01, -0.02, 0.03, 0.5] },
    B: { dates: ["d1", "d2", "d3"], r: [0.02, -0.04, 0.06] },
    C: { dates: ["d1", "d2", "d3", "d4"], r: [-0.01, 0.02, -0.03, 0.1] },
  };
  const m = C.correlationMatrix(series, ["A", "B", "C", "MISSING"]);
  assert.deepEqual(m.tickers, ["A", "B", "C"]);
  assert.equal(m.n, 3);              // d4 dropped because B has no d4
  close(m.matrix[0][1], 1);          // A and B proportional on d1..d3
  close(m.matrix[0][2], -1);
});

test("command parser", () => {
  const U = ["AAPL", "MC.PA", "^VIX"];
  assert.deepEqual(C.parseCommand("aapl", U), { type: "ticker", ticker: "AAPL", tab: "QUOTE" });
  assert.deepEqual(C.parseCommand("AAPL FA", U), { type: "ticker", ticker: "AAPL", tab: "FA" });
  assert.deepEqual(C.parseCommand("mc.pa risk", U), { type: "ticker", ticker: "MC.PA", tab: "RISK" });
  assert.deepEqual(C.parseCommand("ECO", U), { type: "tab", tab: "ECO" });
  assert.deepEqual(C.parseCommand("eqs", U), { type: "tab", tab: "EQS" });
  assert.equal(C.parseCommand("AAPL EQS", U).type, "error");
  assert.deepEqual(C.parseCommand("lang en", U), { type: "lang", lang: "en" });
  assert.equal(C.parseCommand("TSLAA", U).type, "error");
  assert.equal(C.parseCommand("AAPL XYZ", U).type, "error");
});

test("market sessions: open / stale helpers", () => {
  const ses = [["2026-10-16T13:30:00+00:00", "2026-10-16T20:00:00+00:00"], ["2026-10-19T13:30:00+00:00", "2026-10-19T20:00:00+00:00"]];
  assert.equal(C.isOpen(ses, new Date("2026-10-16T15:00:00Z")), true);
  assert.equal(C.isOpen(ses, new Date("2026-10-17T15:00:00Z")), false);
  assert.equal(C.sessionsClosedSince(ses, "2026-10-16T10:00:00Z", new Date("2026-10-20T00:00:00Z")), 2);
});

test("safeName matches the Python rule", () => {
  assert.equal(C.safeName("^GDAXI"), "_GDAXI");
  assert.equal(C.safeName("EURUSD=X"), "EURUSD_X");
  assert.equal(C.safeName("NOVO-B.CO"), "NOVO-B.CO");
});

test("translations: FR and EN have the same keys and cover every key used", () => {
  const fr = JSON.parse(fs.readFileSync(path.join(SITE, "i18n", "fr.json"), "utf8"));
  const en = JSON.parse(fs.readFileSync(path.join(SITE, "i18n", "en.json"), "utf8"));
  assert.deepEqual(Object.keys(fr).sort(), Object.keys(en).sort());
  for (const k of Object.keys(fr)) assert.ok(fr[k] && en[k], `empty translation for ${k}`);
  const app = fs.readFileSync(path.join(SITE, "js", "app.js"), "utf8") + fs.readFileSync(path.join(SITE, "js", "calc.js"), "utf8");
  const html = fs.readFileSync(path.join(SITE, "index.html"), "utf8");
  const used = new Set();
  for (const m of app.matchAll(/\bt\("([a-z0-9_.]+)"/g)) used.add(m[1]);
  for (const m of app.matchAll(/"((?:fa|sent|cmd|help)\.[a-z0-9_]+)"/g)) used.add(m[1]);
  for (const m of html.matchAll(/data-i18n(?:-placeholder|-title)?="([^"]+)"/g)) used.add(m[1]);
  C.TABS.forEach(x => used.add("tab." + x));                                                // t("tab." + tab)
  ["FR", "DE", "NL", "CH", "GB", "DK", "ES", "IT", "US"].forEach(x => used.add("country." + x)); // t("country." + c)
  ["large", "smid", "us"].forEach(x => used.add("seg." + x));                              // t("seg." + segment)
  ["index", "etf", "fx", "commodity", "stock"].forEach(x => used.add("kind." + x));        // t("kind." + kind)
  ["positive", "neutral", "negative"].forEach(x => used.add("sent." + x));                 // t("sent." + label)
  ["US", "EU"].forEach(x => used.add("region." + x));                                      // t("region." + r)
  const missing = [...used].filter(k => !k.endsWith(".") && !(k in fr)); // "tab." etc. = dynamic prefixes, checked above
  assert.deepEqual(missing, [], "missing translation keys: " + missing.join(", "));
});

// ---------------- search helper
const UNI = [
  { ticker: "TTE.PA", name: "TotalEnergies", aliases: ["Total", "Total Energies"], segment: "large" },
  { ticker: "MC.PA", name: "LVMH", aliases: [], segment: "large" },
  { ticker: "AIR.PA", name: "Airbus", aliases: [], segment: "large" },
  { ticker: "AI.PA", name: "Air Liquide", aliases: [], segment: "large" },
  { ticker: "RMS.PA", name: "Hermès", aliases: [], segment: "large" },
  { ticker: "OR.PA", name: "L'Oréal", aliases: [], segment: "large" },
  { ticker: "SAN.PA", name: "Sanofi", aliases: [], segment: "large" },
  { ticker: "SAN.MC", name: "Banco Santander", aliases: ["Santander"], segment: "large" },
  { ticker: "GOOGL", name: "Alphabet", aliases: ["Google"], segment: "large" },
  { ticker: "^FCHI", name: "CAC 40", aliases: ["CAC"], segment: "large" },
  { ticker: "VCT.PA", name: "Vicat", aliases: [], segment: "smid" },
];

test("suggest: names, tickers, accents, aliases", () => {
  assert.equal(C.suggest("total", UNI)[0].value, "TTE.PA");
  assert.equal(C.suggest("TTE", UNI)[0].value, "TTE.PA");
  assert.equal(C.suggest("tte", UNI)[0].value, "TTE.PA");
  assert.equal(C.suggest("hermes", UNI)[0].value, "RMS.PA");      // accent-insensitive
  assert.equal(C.suggest("loreal", UNI)[0].value, "OR.PA");       // apostrophe and accent ignored
  assert.equal(C.suggest("google", UNI)[0].value, "GOOGL");       // alias
  assert.equal(C.suggest("cac", UNI)[0].value, "^FCHI");
  const air = C.suggest("air", UNI).map(s => s.value);
  assert.ok(air.includes("AIR.PA") && air.includes("AI.PA"));
  assert.deepEqual(C.suggest("zzzz", UNI), []);
});

test("suggest: functions after a ticker, commands", () => {
  assert.deepEqual(C.suggest("TTE.PA ", UNI).map(s => s.value), ["TTE.PA QUOTE", "TTE.PA FA", "TTE.PA RISK", "TTE.PA NEWS"]);
  assert.deepEqual(C.suggest("total f", UNI).map(s => s.value), ["TTE.PA FA"]); // exact name/alias works too
  assert.deepEqual(C.suggest("TTE.PA f", UNI).map(s => s.value), ["TTE.PA FA"]);
  assert.ok(C.suggest("EC", UNI).some(s => s.kind === "cmd" && s.value === "ECO"));
});

test("parseCommand accepts names and unambiguous base tickers, refuses ambiguity", () => {
  assert.deepEqual(C.parseCommand("total", UNI), { type: "ticker", ticker: "TTE.PA", tab: "QUOTE" });
  assert.deepEqual(C.parseCommand("TTE", UNI), { type: "ticker", ticker: "TTE.PA", tab: "QUOTE" });
  assert.deepEqual(C.parseCommand("total energies fa", UNI), { type: "ticker", ticker: "TTE.PA", tab: "FA" });
  assert.deepEqual(C.parseCommand("lvmh risk", UNI), { type: "ticker", ticker: "MC.PA", tab: "RISK" });
  assert.equal(C.parseCommand("air", UNI).ticker, "AIR.PA");       // AIR is Airbus's own ticker
  assert.equal(C.parseCommand("sa", UNI).type, "error");           // Sanofi or Santander: never guessed
  assert.equal(C.parseCommand("SAN", UNI).type, "error");          // SAN.PA or SAN.MC
});
