/* Pure helpers shared by the site and the Node tests. No DOM, no data. */
(function (root) {
  "use strict";
  const TABS = ["MKTS", "QUOTE", "FA", "RISK", "NEWS", "ECO", "EQS"];

  function safeName(t) { return t.replace(/[^A-Za-z0-9.\-]/g, "_"); }

  // Simple moving average; null until `n` values are available.
  function sma(values, n) {
    const out = new Array(values.length).fill(null);
    let sum = 0;
    for (let i = 0; i < values.length; i++) {
      sum += values[i];
      if (i >= n) sum -= values[i - n];
      if (i >= n - 1) out[i] = sum / n;
    }
    return out;
  }

  // Pearson correlation of two equal-length arrays.
  function pearson(a, b) {
    const n = a.length;
    if (n < 2) return null;
    let ma = 0, mb = 0;
    for (let i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    let cov = 0, va = 0, vb = 0;
    for (let i = 0; i < n; i++) {
      const da = a[i] - ma, db = b[i] - mb;
      cov += da * db; va += da * da; vb += db * db;
    }
    if (va === 0 || vb === 0) return null;
    return cov / Math.sqrt(va * vb);
  }

  // series: {ticker: {dates: [...], r: [...]}} -> correlation matrix on dates common to ALL tickers
  function correlationMatrix(series, tickers) {
    const avail = tickers.filter(t => series[t] && series[t].dates.length);
    if (!avail.length) return { tickers: [], matrix: [], n: 0 };
    let common = new Set(series[avail[0]].dates);
    for (const t of avail.slice(1)) {
      const s = new Set(series[t].dates);
      common = new Set([...common].filter(d => s.has(d)));
    }
    const dates = [...common].sort();
    const aligned = {};
    for (const t of avail) {
      const m = new Map(series[t].dates.map((d, i) => [d, series[t].r[i]]));
      aligned[t] = dates.map(d => m.get(d));
    }
    const matrix = avail.map(a => avail.map(b => (a === b ? 1 : pearson(aligned[a], aligned[b]))));
    return { tickers: avail, matrix, n: dates.length };
  }

  function parseCommand(input, universe) {
    const parts = String(input || "").trim().toUpperCase().split(/\s+/).filter(Boolean);
    if (!parts.length) return { type: "none" };
    const [a, b] = parts;
    if (a === "HELP") return { type: "help" };
    if (a === "LANG") {
      if (b === "FR" || b === "EN") return { type: "lang", lang: b.toLowerCase() };
      return { type: "error", key: "cmd.bad_lang" };
    }
    if (TABS.includes(a) && !b) return { type: "tab", tab: a };
    const ticker = universe.find(t => t.toUpperCase() === a);
    if (!ticker) return { type: "error", key: "cmd.unknown", arg: parts.join(" ") };
    if (!b) return { type: "ticker", ticker, tab: "QUOTE" };
    if (TABS.includes(b) && !["MKTS", "ECO", "EQS"].includes(b)) return { type: "ticker", ticker, tab: b };
    return { type: "error", key: "cmd.unknown_fn", arg: b };
  }

  // sessions: [[openISO, closeISO], ...]
  function isOpen(sessions, now) {
    const t = now.getTime();
    return (sessions || []).some(([o, c]) => Date.parse(o) <= t && t <= Date.parse(c));
  }

  // number of sessions that CLOSED strictly after `since` and before `now`
  function sessionsClosedSince(sessions, since, now) {
    const s = Date.parse(since), n = now.getTime();
    return (sessions || []).filter(([, c]) => { const ct = Date.parse(c); return ct > s && ct <= n; }).length;
  }

  function parisMinutes(now) {
    const parts = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/Paris", hour: "2-digit", minute: "2-digit", hourCycle: "h23", weekday: "short" }).formatToParts(now);
    const get = k => parts.find(p => p.type === k).value;
    return { minutes: Number(get("hour")) * 60 + Number(get("minute")), weekday: get("weekday") };
  }

  const api = { TABS, safeName, sma, pearson, correlationMatrix, parseCommand, isOpen, sessionsClosedSince, parisMinutes };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AtlasCalc = api;
})(this);
