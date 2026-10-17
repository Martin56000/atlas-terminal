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

  const TICKER_FNS = ["QUOTE", "FA", "RISK", "NEWS"];
  const COMMANDS = ["MKTS", "EQS", "ECO", "RISK", "NEWS", "QUOTE", "FA", "HELP", "LANG FR", "LANG EN"];

  // lower-case, accents and punctuation removed: "L'Oréal" -> "loreal", "Hermès" -> "hermes"
  function norm(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9^=.\- ]/g, "");
  }
  const base = t => t.toUpperCase().replace(/^\^/, "").split(/[.=]/)[0];

  // universe: array of strings (tickers) or objects {ticker, name, aliases, segment}
  function asItems(universe) {
    return universe.map(u => (typeof u === "string" ? { ticker: u, name: "", aliases: [] } : u));
  }

  function scoreItem(u, q) {
    const nq = norm(q), uq = q.toUpperCase(), tk = u.ticker.toUpperCase();
    if (!nq) return 0;
    const names = [u.name].concat(u.aliases || []).map(norm).filter(Boolean);
    if (tk === uq) return 100;
    if (base(tk) === uq.replace(/^\^/, "")) return 95;
    if (names.some(n => n === nq || n.replace(/ /g, "") === nq.replace(/ /g, ""))) return 90;
    if (tk.startsWith(uq) || base(tk).startsWith(uq.replace(/^\^/, ""))) return 80;
    if (names.some(n => n.startsWith(nq) || n.replace(/ /g, "").startsWith(nq.replace(/ /g, "")))) return 70;
    if (names.some(n => n.split(" ").some(w => w.startsWith(nq)))) return 60;
    if (nq.length >= 3 && (tk.includes(uq) || names.some(n => n.includes(nq)))) return 30;
    return 0;
  }

  // Ranked suggestions for the command bar.
  function suggest(input, universe, limit) {
    limit = limit || 8;
    const raw = String(input || "");
    const parts = raw.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return [];
    const items = asItems(universe);
    // "<ticker> <partial function>" -> functions for that ticker
    if (parts.length >= 1 && (parts.length === 2 || /\s$/.test(raw))) {
      const t = resolveTicker(parts[0], items);
      if (t) {
        const fn = (parts[1] || "").toUpperCase();
        return TICKER_FNS.filter(f => f.startsWith(fn)).map(f => ({ kind: "fn", value: `${t} ${f}`, ticker: t, fn: f }));
      }
    }
    const q = parts.join(" ");
    const uq = q.toUpperCase();
    const cmds = COMMANDS.filter(c => c.startsWith(uq) && c !== uq).map(c => ({ kind: "cmd", value: c, score: 85 }));
    const tickers = items.map(u => ({ kind: "ticker", value: u.ticker, ticker: u.ticker, name: u.name, item: u, score: scoreItem(u, q) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score
        || (a.item.segment === "large" ? 0 : 1) - (b.item.segment === "large" ? 0 : 1)
        || a.ticker.length - b.ticker.length || a.ticker.localeCompare(b.ticker));
    return cmds.concat(tickers).sort((a, b) => b.score - a.score).slice(0, limit);
  }

  // Exact ticker, exact base ticker when unique (TTE -> TTE.PA), or exact company name / alias.
  function resolveTicker(word, universe) {
    const items = asItems(universe);
    const w = String(word || "").toUpperCase();
    const exact = items.find(u => u.ticker.toUpperCase() === w);
    if (exact) return exact.ticker;
    const byBase = items.filter(u => base(u.ticker) === w.replace(/^\^/, ""));
    if (byBase.length === 1) return byBase[0].ticker;
    const n = norm(word).replace(/ /g, "");
    const byName = items.filter(u => [u.name].concat(u.aliases || []).some(x => norm(x).replace(/ /g, "") === n));
    return byName.length === 1 ? byName[0].ticker : null;
  }

  function parseCommand(input, universe) {
    const parts = String(input || "").trim().toUpperCase().split(/\s+/).filter(Boolean);
    if (!parts.length) return { type: "none" };
    const [a, b] = parts;
    if (a === "HELP" && !b) return { type: "help" };
    if (a === "LANG") {
      if (b === "FR" || b === "EN") return { type: "lang", lang: b.toLowerCase() };
      return { type: "error", key: "cmd.bad_lang" };
    }
    if (TABS.includes(a) && !b) return { type: "tab", tab: a };
    // 1) the whole text (minus a trailing function) as ticker or full name: "total energies fa", "air liquide"
    const last = parts[parts.length - 1];
    const hasFn = parts.length > 1 && TICKER_FNS.includes(last);
    const words = String(input).trim().split(/\s+/).slice(0, hasFn ? -1 : undefined).join(" ");
    let ticker = resolveTicker(words, universe), fn = hasFn ? last : undefined;
    // 2) first word as ticker, second as function: "AAPL FA", "AAPL XYZ" (-> unknown function)
    if (!ticker && resolveTicker(a, universe)) { ticker = resolveTicker(a, universe); fn = b; }
    // 3) a single clear match ("tot" -> TotalEnergies); ambiguous input ("sa") is never guessed
    if (!ticker) {
      const best = suggest(words, universe, 10).filter(s => s.kind === "ticker").slice(0, 2);
      if (best.length && best[0].score >= 70 && !(best[1] && best[1].score === best[0].score)) ticker = best[0].ticker;
      if (!ticker) return { type: "error", key: "cmd.unknown", arg: parts.join(" ") };
    }
    if (!fn) return { type: "ticker", ticker, tab: "QUOTE" };
    if (TICKER_FNS.includes(fn)) return { type: "ticker", ticker, tab: fn };
    return { type: "error", key: "cmd.unknown_fn", arg: fn };
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

  const api = { TABS, safeName, sma, pearson, correlationMatrix, parseCommand, suggest, resolveTicker, norm, isOpen, sessionsClosedSince, parisMinutes };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AtlasCalc = api;
})(this);
