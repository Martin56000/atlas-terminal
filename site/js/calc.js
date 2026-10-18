/* Pure helpers shared by the site and the Node tests. No DOM, no data. */
(function (root) {
  "use strict";
  const TABS = ["LP", "MKTS", "WEI", "MOST", "IMAP", "QUOTE", "GIP", "HP", "COMP", "DES", "FA", "DVD", "HDS", "RISK", "NEWS", "ECO", "FXC", "GLCO", "EQS", "COMPS", "DEALS", "STATUS"];

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

  const TICKER_FNS = ["QUOTE", "GIP", "HP", "COMP", "DES", "FA", "DVD", "HDS", "RISK", "NEWS", "COMPS", "DEALS"];
  const COMMANDS = ["LP", "MKTS", "WEI", "MOST", "IMAP", "FXC", "GLCO", "EQS", "COMPS", "DEALS", "ECO", "STATUS", "RISK", "NEWS", "QUOTE", "DES", "FA", "HELP", "LANG FR", "LANG EN"];

  // ---- terminal-style syntax: "MC FP Equity DES <GO>", "SX5E Index GP", "EURUSD Curncy", function mnemonics
  const EXCH = { FP: ".PA", GY: ".DE", GR: ".DE", NA: ".AS", SW: ".SW", SE: ".SW", VX: ".SW", LN: ".L", DC: ".CO",
    SM: ".MC", SQ: ".MC", IM: ".MI", BB: ".BR", SS: ".ST", NO: ".OL", FH: ".HE", PL: ".LS", AV: ".VI", ID: ".IR", PW: ".WA",
    GA: ".AT", CP: ".PR", US: "", UN: "", UW: "", UQ: "" };
  const SUFFIX_CODE = { ".PA": "FP", ".DE": "GY", ".AS": "NA", ".SW": "SW", ".L": "LN", ".CO": "DC", ".MC": "SM", ".MI": "IM",
    ".BR": "BB", ".ST": "SS", ".OL": "NO", ".HE": "FH", ".LS": "PL", ".VI": "AV", ".IR": "ID", ".WA": "PW", ".AT": "GA", ".PR": "CP" };
  const INDEX_CODES = { SX5E: "^STOXX50E", CAC: "^FCHI", DAX: "^GDAXI", UKX: "^FTSE", AEX: "^AEX", SMI: "^SSMI", IBEX: "^IBEX",
    FTSEMIB: "FTSEMIB.MI", SXXP: "^STOXX", SBF120: "^SBF120", MDAX: "^MDAXI", SDAX: "^SDAXI", MCX: "^FTMC", SPX: "^GSPC",
    INDU: "^DJI", CCMP: "^IXIC", RTY: "^RUT", NKY: "^N225", HSI: "^HSI", SHCOMP: "000001.SS", AS51: "^AXJO", KOSPI: "^KS11", VIX: "^VIX" };
  const CMDTY_CODES = { CO1: "BZ=F", BRENT: "BZ=F", GC1: "GC=F", XAU: "GC=F", CL1: "CL=F", NG1: "NG=F", TTF1: "TTF=F", SI1: "SI=F",
    PL1: "PL=F", HG1: "HG=F", W1: "ZW=F", KC1: "KC=F", CC1: "CC=F" };
  const SECTORS = ["EQUITY", "INDEX", "CURNCY", "COMDTY", "CMDTY"];
  // mnemonics of the classic terminal -> our screens (+ section of the company page)
  const FN_ALIASES = { GP: ["QUOTE"], ANR: ["DES", "targets"], EE: ["DES", "consensus"], ERN: ["DES", "surprises"], RV: ["COMPS"],
    MA: ["DEALS"], CN: ["NEWS"], N: ["NEWS"], TOP: ["NEWS"], BETA: ["RISK"], FXIP: ["FXC"], DDM: ["DVD"],
    RELS: ["COMP"], GPC: ["COMP"] };
  const TAB_ALIASES = { MON: "MKTS", BTMM: "ECO", FX: "FXC", WB: "ECO", CMDTY: "GLCO", BMAP: "IMAP", WEIF: "WEI", MOV: "MOST" };
  const STANDALONE = ["LP", "MKTS", "WEI", "MOST", "IMAP", "FXC", "GLCO", "EQS", "COMPS", "DEALS", "ECO", "STATUS", "NEWS", "RISK"];

  function bbgCode(ticker, item) {
    for (const [code, tk] of Object.entries(INDEX_CODES)) if (tk === ticker) return code + " Index";
    if (/^EUR[A-Z]{3}=X$/.test(ticker)) return ticker.slice(0, 6) + " Curncy";
    for (const [code, tk] of Object.entries(CMDTY_CODES)) if (tk === ticker) return code + " Comdty";
    const m = ticker.match(/^(.*?)(\.[A-Z]{1,2})$/);
    if (m && SUFFIX_CODE[m[2]]) return m[1].replace(/-/g, "") + " " + SUFFIX_CODE[m[2]] + " Equity";
    if (item && item.kind === "index") return ticker + " Index";
    return ticker + " US Equity";
  }

  // "MC FP [Equity]" / "SX5E Index" / "EURUSD Curncy" / "CO1 Comdty" at the start of the input -> {ticker, used}
  function resolveSecurity(parts, universe) {
    const items = asItems(universe);
    const has = tk => items.some(u => u.ticker === tk);
    const [a, b, c] = parts;
    if (!a) return null;
    const sectorAt = i => SECTORS.includes(parts[i]);
    if (INDEX_CODES[a] && has(INDEX_CODES[a])) return { ticker: INDEX_CODES[a], used: b === "INDEX" ? 2 : 1 };
    if (CMDTY_CODES[a] && has(CMDTY_CODES[a])) return { ticker: CMDTY_CODES[a], used: sectorAt(1) ? 2 : 1 };
    if (/^EUR[A-Z]{3}$/.test(a) && has(a + "=X")) return { ticker: a + "=X", used: b === "CURNCY" ? 2 : 1 };
    if (b && b in EXCH) {
      const suffix = EXCH[b];
      const match = items.find(u => {
        const m = u.ticker.match(/^(.*?)(\.[A-Z]{1,2})?$/);
        const base = (m[1] || "").replace(/-/g, "").toUpperCase(), sfx = m[2] || "";
        return base === a.replace(/-/g, "") && (suffix === "" ? sfx === "" : sfx === suffix);
      });
      if (match) return { ticker: match.ticker, used: c && SECTORS.includes(c) ? 3 : 2 };
    }
    return null;
  }

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
    input = String(input || "").replace(/<\s*GO\s*>/gi, " ").replace(/\s+GO\s*$/i, " ").trim();
    let parts = input.toUpperCase().split(/\s+/).filter(Boolean);
    if (!parts.length) return { type: "none" };
    if (/^\d{1,2}$/.test(parts[0]) && parts.length === 1) return { type: "menu", n: Number(parts[0]) };
    if (parts.length === 1 && TAB_ALIASES[parts[0]]) return { type: "tab", tab: TAB_ALIASES[parts[0]] };
    // function alone ("GP", "ANR", "HP", "DVD") -> on the current security
    if (parts.length === 1 && TICKER_FNS.includes(parts[0]) && !STANDALONE.includes(parts[0])) return { type: "fn", tab: parts[0] };
    // function mnemonic alone ("GP", "ANR") -> on the current security
    if (parts.length === 1 && FN_ALIASES[parts[0]] && !STANDALONE.includes(parts[0])) {
      const [tab, section] = FN_ALIASES[parts[0]];
      return Object.assign({ type: "fn", tab }, section ? { section } : {});
    }
    // terminal syntax for the security
    const sec = resolveSecurity(parts, universe);
    if (sec) {
      const rest = parts.slice(sec.used);
      if (!rest.length) return { type: "ticker", ticker: sec.ticker, tab: "QUOTE" };
      const f = rest[0];
      if (FN_ALIASES[f]) return Object.assign({ type: "ticker", ticker: sec.ticker, tab: FN_ALIASES[f][0] }, FN_ALIASES[f][1] ? { section: FN_ALIASES[f][1] } : {});
      if (TICKER_FNS.includes(f)) return { type: "ticker", ticker: sec.ticker, tab: f };
      return { type: "error", key: "cmd.unknown_fn", arg: f };
    }
    // "AAPL GP" / "lvmh anr": map mnemonics in second position
    if (parts.length >= 2 && FN_ALIASES[parts[parts.length - 1]]) {
      const [tab, section] = FN_ALIASES[parts[parts.length - 1]];
      const r = parseCommand(parts.slice(0, -1).join(" ") + " " + tab, universe);
      if (r.type === "ticker") return Object.assign(r, section ? { section } : {});
    }
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

  function median(vals) {
    const v = vals.filter(x => typeof x === "number" && isFinite(x)).sort((a, b) => a - b);
    if (!v.length) return null;
    const m = Math.floor(v.length / 2);
    return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }

  // same as pipeline/metrics.py: last window+1 prices (nulls dropped) -> `window` log returns
  function windowReturns(dates, prices, window) {
    const pts = dates.map((d, i) => [d, prices[i]]).filter(p => typeof p[1] === "number" && p[1] > 0).slice(-(window + 1));
    const out = { dates: [], r: [] };
    for (let i = 1; i < pts.length; i++) { out.dates.push(pts[i][0]); out.r.push(Math.log(pts[i][1] / pts[i - 1][1])); }
    return out;
  }
  // a machine translation must not contain a number that is not in the original
  function numbersSubset(src, dst) {
    const count = s => (String(s || "").match(/\d+/g) || []).reduce((m, x) => (m[x] = (m[x] || 0) + 1, m), {});
    const a = count(src), b = count(dst);
    return Object.keys(b).every(k => (a[k] || 0) >= b[k]);
  }
  const api = { windowReturns, numbersSubset, bbgCode, resolveSecurity, FN_ALIASES, median, TABS, safeName, sma, pearson, correlationMatrix, parseCommand, suggest, resolveTicker, norm, isOpen, sessionsClosedSince, parisMinutes };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.AtlasCalc = api;
})(this);
