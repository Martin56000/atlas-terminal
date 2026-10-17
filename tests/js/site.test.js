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
  ["MKTS", "QUOTE", "FA", "RISK", "NEWS", "ECO"].forEach(x => used.add("tab." + x));        // t("tab." + tab)
  ["positive", "neutral", "negative"].forEach(x => used.add("sent." + x));                 // t("sent." + label)
  ["US", "EU"].forEach(x => used.add("region." + x));                                      // t("region." + r)
  const missing = [...used].filter(k => !k.endsWith(".") && !(k in fr)); // "tab." etc. = dynamic prefixes, checked above
  assert.deepEqual(missing, [], "missing translation keys: " + missing.join(", "));
});
