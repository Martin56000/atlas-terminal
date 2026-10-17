/* Atlas Terminal front-end. Reads only the JSON files produced by the update job
   (data/*.json). It never computes or displays a number that is not in those files,
   except values derived on screen from them (moving averages, correlations, spreads). */
(function () {
  "use strict";
  const C = window.AtlasCalc;

  // ------------------------------------------------------------------ settings
  const LS = {
    get(k, d) { try { const v = localStorage.getItem("atlas." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("atlas." + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const S = {
    lang: LS.get("lang", "fr"), numfmt: LS.get("numfmt", "fr"), tz: LS.get("tz", "Europe/Paris"),
    auto: LS.get("auto", true), watchlist: LS.get("watchlist", null),
    tab: "MKTS", ticker: "AAPL", range: LS.get("range", "1Y"), newsTicker: "ALL", faTicker: null,
  };
  const FKEYS = { MKTS: "F1", QUOTE: "F2", FA: "F3", RISK: "F4", NEWS: "F5", ECO: "F6" };
  const CORE = ["meta.json", "quotes.json", "risk.json", "macro.json", "news.json", "validation.json"];

  let I18N = {};
  const D = {};          // dataset name -> {ok, env} | {ok:false, error}
  const FILES = {};      // per-ticker files (history/, fundamentals/)
  let charts = [];
  let UNI = {};          // ticker -> universe info (from meta.json)

  // ------------------------------------------------------------------ utils
  const $ = sel => document.querySelector(sel);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = u => (/^https?:\/\//i.test(u || "") ? u : "#");
  function t(key, vars) {
    let s = I18N[key];
    if (s === undefined) { console.warn("missing i18n key", key); s = key; }
    if (vars) for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
    return s;
  }
  const locale = () => (S.numfmt === "fr" ? "fr-FR" : "en-US");
  const dlocale = () => (S.lang === "fr" ? "fr-FR" : "en-US");
  const isNum = v => typeof v === "number" && isFinite(v);
  function num(v, d = 2) {
    if (!isNum(v)) return "—";
    return new Intl.NumberFormat(locale(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  }
  function signed(v, d = 2) { return isNum(v) ? (v > 0 ? "+" : "") + num(v, d) : "—"; }
  function pct(v, d = 2, sign = true) {
    if (!isNum(v)) return "—";
    const s = (sign && v > 0 ? "+" : "") + num(v * 100, d);
    return S.numfmt === "fr" ? s + " %" : s + "%";
  }
  const pctPts = (v, d = 2) => (isNum(v) ? pct(v / 100, d, false) : "—"); // value already in %
  function compact(v) {
    if (!isNum(v)) return "—";
    const a = Math.abs(v);
    if (a >= 1e12) return num(v / 1e12, 2) + " " + t("unit.tn");
    if (a >= 1e9) return num(v / 1e9, 2) + " " + t("unit.bn");
    if (a >= 1e6) return num(v / 1e6, 1) + " " + t("unit.mn");
    if (a >= 1e3) return num(v / 1e3, 1) + " k";
    return num(v, 0);
  }
  const cls = v => (!isNum(v) ? "flat" : v > 0 ? "up" : v < 0 ? "down" : "flat");
  const tzLabel = () => (S.tz === "Europe/Paris" ? "Paris" : "NY");
  function fmtDT(iso) {
    if (!iso) return "—";
    return new Intl.DateTimeFormat(dlocale(), { timeZone: S.tz, day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) + " " + tzLabel();
  }
  function fmtDate(ymd, opts) {
    if (!ymd) return "—";
    const d = new Date(ymd.length === 7 ? ymd + "-01T12:00:00Z" : ymd.slice(0, 10) + "T12:00:00Z");
    return new Intl.DateTimeFormat(dlocale(), Object.assign({ timeZone: "UTC", day: "2-digit", month: "2-digit", year: "2-digit" }, opts || {})).format(d);
  }

  // ------------------------------------------------------------------ data access
  async function getJSON(path) {
    const r = await fetch("data/" + path + "?v=" + Math.floor(Date.now() / 60000), { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status + " (" + path + ")");
    return r.json();
  }
  async function load(name, store) {
    store = store || D;
    try { store[name] = { ok: true, env: await getJSON(name) }; }
    catch (e) { store[name] = { ok: false, error: e.message }; }
    return store[name];
  }
  // normalised view of an envelope dataset
  function ds(name, store) {
    const x = (store || D)[name];
    if (!x) return { ok: false, error: t("loading") };
    if (!x.ok) return { ok: false, error: x.error };
    const m = x.env._meta || {};
    if (m.status !== "ok" || x.env.data == null) return { ok: false, error: m.error || "no data", meta: m };
    return { ok: true, data: x.env.data, meta: m };
  }
  const meta = () => (D["meta.json"] && D["meta.json"].ok ? D["meta.json"].env : null);
  function watchlist() {
    const m = meta();
    const all = m ? m.watchlist_universe : [];
    const wl = S.watchlist || (m ? m.default_watchlist : []);
    return wl.filter(tk => all.includes(tk));
  }

  // ------------------------------------------------------------------ staleness
  const sessionsOf = ex => { const m = meta(); return m && m.sessions ? m.sessions[ex] : null; };
  const DAY_END = 18 * 60 + 30;
  function quoteStale(tk, fetchedAt) {
    const info = UNI[tk]; if (!info || !fetchedAt) return false;
    const now = new Date();
    if (!C.isOpen(sessionsOf(info.exchange), now) || C.parisMinutes(now).minutes > DAY_END) return false;
    return now - Date.parse(fetchedAt) > 30 * 60000;
  }
  function newsStale(fetchedAt) {
    if (!fetchedAt) return false;
    const now = new Date(), pm = C.parisMinutes(now);
    if (pm.weekday === "Sat" || pm.weekday === "Sun" || pm.minutes < 9 * 60 || pm.minutes > DAY_END) return false;
    return now - Date.parse(fetchedAt) > 2 * 3600000;
  }
  function dailyStale(fetchedAt) {
    const ses = sessionsOf("XNYS");
    return !!(ses && fetchedAt && C.sessionsClosedSince(ses, fetchedAt, new Date()) >= 2);
  }

  // ------------------------------------------------------------------ building blocks
  function panel(o) {
    const stale = o.stale ? `<span class="stale" title="${esc(t("stale.tip"))}">${t("stale")}</span>` : "";
    const upd = o.updated === undefined ? (o.meta && o.meta.fetched_at) : o.updated;
    return `<section class="panel ${o.cls || "span-12"}" ${o.id ? `id="${o.id}"` : ""}>
      <div class="ph"><span class="ph-title">${o.title}</span><span class="ph-tools">${stale}${o.tools || ""}</span></div>
      <div class="pb">${o.body}</div>
      <div class="pf"><span class="src">${t("panel.source")}: ${esc(o.source || (o.meta && o.meta.source) || "—")}</span>
      <span>${t("panel.updated")}: ${fmtDT(upd)}</span>${o.foot ? `<span>${o.foot}</span>` : ""}</div></section>`;
  }
  function unavailable(error, lastSuccess) {
    const e = String(error || "");
    return `<div class="unavail"><b>${t("unavailable")}</b><span class="err" title="${esc(e)}">${esc(e.length > 320 ? e.slice(0, 320) + "…" : e)}</span><br>
      <span class="note">${t("last_success")}: ${lastSuccess ? fmtDT(lastSuccess) : t("never")}</span></div>`;
  }
  const dsUnavailable = x => unavailable(x.error, x.meta && x.meta.last_success);
  const delayed = () => `<span class="delayed">${t("delayed")}</span>`;

  function destroyCharts() { charts.forEach(c => { try { c.destroy(); } catch (e) { /* */ } }); charts = []; }

  // ------------------------------------------------------------------ chrome: tabs, clocks
  function renderTabs() {
    $("#tabs").innerHTML = C.TABS.map(tab =>
      `<button class="tab ${S.tab === tab ? "active" : ""}" data-tab="${tab}"><span class="fk">${FKEYS[tab]}</span>${tab}<span class="note"> ${t("tab." + tab)}</span></button>`).join("");
  }
  function renderClocks() {
    const now = new Date();
    const f = tz => new Intl.DateTimeFormat(dlocale(), { timeZone: tz, hour: "2-digit", minute: "2-digit" }).format(now);
    const st = (ex, label) => {
      const ses = sessionsOf(ex);
      if (!ses) return "";
      const open = C.isOpen(ses, now);
      return `<span class="mkt ${open ? "open" : "closed"}" title="${esc(label)}">${esc(label)} ${open ? t("mkt.open") : t("mkt.closed")}</span>`;
    };
    $("#clocks").innerHTML = `<span>PAR <b>${f("Europe/Paris")}</b>${st("XPAR", "EURONEXT")}</span><span>NY <b>${f("America/New_York")}</b>${st("XNYS", "NYSE")}</span>`;
  }
  function applyStaticI18n() {
    document.documentElement.lang = S.lang;
    document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
    document.querySelectorAll("[data-i18n-title]").forEach(el => { el.title = t(el.dataset.i18nTitle); el.setAttribute("aria-label", t(el.dataset.i18nTitle)); });
  }

  // ------------------------------------------------------------------ MKTS
  function quotesEnv() { return D["quotes.json"] && D["quotes.json"].ok ? D["quotes.json"].env : null; }
  function quoteRows(tickers, opts) {
    opts = opts || {};
    const q = quotesEnv();
    return tickers.map(tk => {
      const info = UNI[tk] || { name: tk };
      const x = q && q.data ? q.data[tk] : null;
      const nameCell = opts.noName ? "" : `<td class="nm">${esc(info.name)}</td>`;
      if (!x || x.status !== "ok") {
        const err = x ? x.error : (q ? t("err.no_quote") : (D["quotes.json"] ? D["quotes.json"].error : t("loading")));
        // the region-wide error is already shown once above the table; only show ticker-specific errors here
        const regionErr = q && UNI[tk] && (q._meta.regions || {})[UNI[tk].region];
        const own = !(regionErr && regionErr.status === "error" && regionErr.error === err);
        return `<tr class="click" data-goto="${esc(tk)}"><td class="tk">${esc(tk)}</td>${nameCell}<td class="na" colspan="${opts.cols || 4}" title="${esc(err)}">${t("unavailable")}${own ? " — " + esc(err) : ""}</td></tr>`;
      }
      const stale = quoteStale(tk, x.fetched_at) ? ` <span class="stale">${t("stale")}</span>` : "";
      return `<tr class="click" data-goto="${esc(tk)}"><td class="tk">${esc(tk)}</td>${nameCell}
        <td>${num(x.last, x.last < 10 ? 4 : 2)} <span class="note">${esc(x.currency || "")}</span>${stale}</td>
        <td class="${cls(x.change)}">${signed(x.change, x.last < 10 ? 4 : 2)}</td><td class="${cls(x.pct)}">${pct(x.pct)}</td>
        <td class="note">${fmtDate(x.date)}</td></tr>`;
    }).join("");
  }
  function quotesPanel(title, tickers, regions, cls) {
    const q = quotesEnv();
    const regs = q ? regions.map(r => (q._meta.regions || {})[r]).filter(Boolean) : [];
    const upd = regs.length ? regs.map(r => r.fetched_at).sort().pop() : null;
    const regErr = regs.filter(r => r.status === "error").map(r => r.error);
    const stale = tickers.some(tk => q && q.data[tk] && quoteStale(tk, q.data[tk].fetched_at));
    const head = `<tr><th>${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th><th>${t("col.last")}</th><th>${t("col.chg")}</th><th>${t("col.pct")}</th><th>${t("col.date")}</th></tr>`;
    return panel({ title: `${title} ${delayed()}`, cls, stale, updated: upd, source: "Yahoo Finance (yfinance)",
      body: (regErr.length ? `<div class="unavail"><b>${t("unavailable")}</b><span class="err">${esc(regErr.join(" | "))}</span></div>` : "") + `<table class="t">${head}${quoteRows(tickers)}</table>` });
  }
  function macroStrip() {
    const x = ds("macro.json");
    if (!x.ok) return panel({ title: t("mkts.macro"), body: dsUnavailable(x), meta: x.meta, source: "FRED + ECB" });
    const m = x.data, errs = (x.meta.errors || {});
    const latest = id => (m[id] ? m[id].latest : null);
    const cell = (label, val, date, id) => `<div class="cell"><div class="k">${label}</div>
      <div class="v">${val}</div><div class="d">${date ? fmtDate(date) : (errs[id] ? `<span class="down">${esc(t("unavailable"))}</span>` : "—")}</div></div>`;
    // 2s10s on the last date where both series have an observation
    let spread = null, spreadDate = null;
    if (m.DGS10 && m.DGS2) {
      const two = new Map(m.DGS2.dates.map((d, i) => [d, m.DGS2.values[i]]));
      for (let i = m.DGS10.dates.length - 1; i >= 0; i--) {
        const d = m.DGS10.dates[i];
        if (two.has(d)) { spread = (m.DGS10.values[i] - two.get(d)) * 100; spreadDate = d; break; }
      }
    }
    const cpi = m.CPIAUCSL && m.CPIAUCSL.yoy ? m.CPIAUCSL.yoy.latest : null;
    const body = `<div class="strip">
      ${cell(t("macro.dff"), latest("DFF") ? pctPts(latest("DFF").value) : "—", latest("DFF") && latest("DFF").date, "DFF")}
      ${cell(t("macro.us10y"), latest("DGS10") ? pctPts(latest("DGS10").value) : "—", latest("DGS10") && latest("DGS10").date, "DGS10")}
      ${cell(t("macro.2s10s"), isNum(spread) ? `<span class="${cls(spread)}">${signed(spread, 0)} ${t("unit.bp")}</span>` : "—", spreadDate, "DGS2")}
      ${cell(t("macro.cpi"), cpi ? pctPts(cpi.value, 1) : "—", cpi && cpi.date, "CPIAUCSL")}
      ${cell(t("macro.ecb"), latest("ECBDFR") ? pctPts(latest("ECBDFR").value) : "—", latest("ECBDFR") && latest("ECBDFR").date, "ECBDFR")}
      ${cell(t("macro.hicp"), latest("HICP_EA") ? pctPts(latest("HICP_EA").value, 1) : "—", latest("HICP_EA") && latest("HICP_EA").date, "HICP_EA")}
    </div>`;
    return panel({ title: t("mkts.macro"), body, meta: x.meta, stale: dailyStale(x.meta.fetched_at),
      foot: Object.keys(errs).length ? `<span class="down">${t("macro.partial")}: ${esc(Object.keys(errs).join(", "))}</span>` : "" });
  }
  function renderMKTS() {
    const m = meta();
    if (!m) return firstRunNotice();
    const wl = watchlist();
    const groups = [["US", t("region.US")], ["EU", t("region.EU")]].map(([r, label]) => {
      const tks = wl.filter(tk => UNI[tk] && UNI[tk].region === r);
      return tks.length ? `<tr class="grp"><td colspan="6">${label}</td></tr>${quoteRows(tks)}` : "";
    }).join("");
    const q = quotesEnv();
    const head = `<tr><th>${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th><th>${t("col.last")}</th><th>${t("col.chg")}</th><th>${t("col.pct")}</th><th>${t("col.date")}</th></tr>`;
    const regs = q ? Object.values(q._meta.regions || {}) : [];
    return macroStrip() +
      quotesPanel(t("mkts.us"), ["SPY", "QQQ", "DIA", "IWM", "^VIX"], ["US"], "span-4") +
      quotesPanel(t("mkts.eu"), m.universe.filter(u => u.kind === "index" && u.region === "EU").map(u => u.ticker), ["EU"], "span-4") +
      quotesPanel(t("mkts.fx"), ["EURUSD=X", "BZ=F", "GC=F"], ["US", "EU"], "span-4") +
      panel({ title: `${t("mkts.watchlist")} ${delayed()}`, tools: `<button class="btn" data-action="edit-wl">${t("wl.edit")}</button>`,
        updated: regs.length ? regs.map(r => r.fetched_at).sort().pop() : null, source: "Yahoo Finance (yfinance)",
        stale: wl.some(tk => q && q.data[tk] && quoteStale(tk, q.data[tk].fetched_at)),
        body: wl.length ? `<table class="t">${head}${groups}</table>` : `<div class="note">${t("wl.empty")}</div>` });
  }
  function firstRunNotice() {
    const x = D["meta.json"];
    return panel({ title: "ATLAS TERMINAL", body: unavailable(x && x.error, null) + `<p class="note">${t("first_run")}</p>`, updated: null, source: "—" });
  }

  // ------------------------------------------------------------------ charts
  const PAL = { amber: "#C97A0A", blue: "#3D9BE9", pink: "#D45FA0", green: "#409A6A", price: "#FFA028" };
  const toTs = d => Date.parse((d.length === 7 ? d + "-01" : d) + "T00:00:00Z") / 1000;
  function axis(fmt, size) {
    return { stroke: "#8d877b", grid: { stroke: "#1c1c1c", width: 1 }, ticks: { stroke: "#2a2a2a", width: 1 },
      font: "11px IBM Plex Mono, monospace", size: size || 64, values: fmt ? (u, vals) => vals.map(fmt) : undefined };
  }
  function xAxis() {
    return { stroke: "#8d877b", grid: { stroke: "#1c1c1c", width: 1 }, ticks: { stroke: "#2a2a2a", width: 1 }, font: "11px IBM Plex Mono, monospace" };
  }
  function makeChart(el, series, data, o) {
    o = o || {};
    const width = Math.max(260, el.clientWidth);
    const opts = {
      width, height: o.height || 260,
      tzDate: ts => uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC"),
      cursor: { sync: o.sync ? { key: o.sync } : undefined, drag: { x: true, y: false }, points: { size: 7 } },
      scales: Object.assign({ x: { time: true } }, o.scales || {}),
      axes: [xAxis(), axis(o.yfmt, o.ysize)].concat(o.extraAxes || []),
      series: [{ label: t("col.date"), value: (u, v) => (v == null ? "—" : fmtDate(new Date(v * 1000).toISOString().slice(0, 10))) }].concat(series),
      legend: { live: true },
    };
    if (o.hideLegend) opts.legend = { show: false };
    const c = new uPlot(opts, data, el);
    charts.push(c);
    return c;
  }
  const line = (label, color, fmt, extra) => Object.assign({ label, stroke: color, width: 2, spanGaps: true, points: { show: false }, value: (u, v) => (v == null ? "—" : fmt(v)) }, extra || {});

  // ------------------------------------------------------------------ QUOTE
  async function historyOf(tk) {
    const name = "history/" + C.safeName(tk) + ".json";
    if (!FILES[name]) await load(name, FILES);
    return ds(name, FILES);
  }
  function tickerSelect(current, list, action) {
    return `<select data-action="${action}">${list.map(tk => `<option value="${esc(tk)}" ${tk === current ? "selected" : ""}>${esc(tk)} — ${esc((UNI[tk] || {}).name || "")}</option>`).join("")}</select>`;
  }
  async function renderQUOTE() {
    const m = meta(); if (!m) return firstRunNotice();
    const tk = S.ticker, info = UNI[tk] || { name: tk };
    const h = await historyOf(tk);
    const q = quotesEnv(), x = q && q.data[tk];
    const ranges = ["1M", "6M", "1Y", "5Y"].map(r => `<button class="btn ${S.range === r ? "on" : ""}" data-range="${r}">${r}</button>`).join("");
    const tools = tickerSelect(tk, m.universe.map(u => u.ticker), "quote-ticker") + ranges;
    let head = "";
    if (x && x.status === "ok") {
      head = `<div class="qhead"><span class="px">${num(x.last, x.last < 10 ? 4 : 2)} <span class="note">${esc(x.currency || "")}</span></span>
        <span class="ch ${cls(x.change)}">${signed(x.change, x.last < 10 ? 4 : 2)} (${pct(x.pct)})</span>${delayed()}
        <span class="kv">${t("quote.asof")} <b>${fmtDate(x.date)}</b></span>
        ${quoteStale(tk, x.fetched_at) ? `<span class="stale">${t("stale")}</span>` : ""}`;
    } else {
      head = `<div class="qhead"><span class="unavail">${t("unavailable")} — ${esc(x ? x.error : t("err.no_quote"))}</span>`;
    }
    let body;
    if (!h.ok) {
      body = head + "</div>" + dsUnavailable(h);
    } else {
      const d = h.data;
      const lastDate = new Date(d.dates[d.dates.length - 1] + "T00:00:00Z");
      const yAgo = new Date(lastDate); yAgo.setUTCFullYear(yAgo.getUTCFullYear() - 1);
      const y0 = yAgo.toISOString().slice(0, 10);
      let hi = null, lo = null;
      d.dates.forEach((dt, i) => { if (dt > y0) { if (isNum(d.high[i]) && (hi === null || d.high[i] > hi)) hi = d.high[i]; if (isNum(d.low[i]) && (lo === null || d.low[i] < lo)) lo = d.low[i]; } });
      head += `<span class="kv">${t("quote.hi52")} <b>${num(hi)}</b></span><span class="kv">${t("quote.lo52")} <b>${num(lo)}</b></span>
        <span class="kv">${t("quote.exchange")} <b>${esc(info.exchange || "")}</b></span></div>`;
      body = head + `<div class="chart" id="pxChart"></div><div class="chart" id="volChart"></div>
        <div class="note">${t("quote.chart_note")}</div>`;
    }
    const html = panel({ title: `${esc(tk)} — ${esc(info.name)}`, tools, body, meta: h.meta, source: "Yahoo Finance (yfinance)",
      stale: h.ok && dailyStale(h.meta.fetched_at) });
    return { html, after: () => h.ok && drawQuoteCharts(h.data) };
  }
  function drawQuoteCharts(d) {
    const ma50 = C.sma(d.close, 50), ma200 = C.sma(d.close, 200);
    const months = { "1M": 1, "6M": 6, "1Y": 12, "5Y": 60 }[S.range] || 12;
    const last = new Date(d.dates[d.dates.length - 1] + "T00:00:00Z");
    last.setUTCMonth(last.getUTCMonth() - months);
    const cut = last.toISOString().slice(0, 10);
    let i0 = d.dates.findIndex(x => x >= cut); if (i0 < 0) i0 = 0;
    const xs = d.dates.slice(i0).map(toTs);
    const dec = d.close[d.close.length - 1] < 10 ? 4 : 2;
    const f = v => num(v, dec);
    makeChart($("#pxChart"), [
      line(t("quote.close"), PAL.price, f),
      line(t("quote.ma50"), PAL.blue, f, { width: 1.5 }),
      line(t("quote.ma200"), PAL.pink, f, { width: 1.5 }),
    ], [xs, d.close.slice(i0), ma50.slice(i0), ma200.slice(i0)], { height: 300, sync: "q", yfmt: v => num(v, dec) });
    const vol = d.volume.slice(i0);
    if (vol.some(v => v)) {
      makeChart($("#volChart"), [{ label: t("quote.volume"), stroke: PAL.amber, fill: "rgba(201,122,10,0.55)", width: 0,
        paths: uPlot.paths.bars({ size: [0.7, 8], gap: 2 }), points: { show: false }, value: (u, v) => compact(v) }],
        [xs, vol], { height: 150, sync: "q", yfmt: compact, scales: { y: { range: (u, mn, mx) => [0, mx] } } });
    } else {
      $("#volChart").innerHTML = `<div class="note">${t("quote.no_volume")}</div>`;
    }
  }

  // ------------------------------------------------------------------ FA
  async function renderFA() {
    const m = meta(); if (!m) return firstRunNotice();
    const list = m.watchlist_universe;
    const tk = list.includes(S.ticker) ? S.ticker : (S.faTicker || "AAPL");
    const name = "fundamentals/" + C.safeName(tk) + ".json";
    if (!FILES[name]) await load(name, FILES);
    const x = ds(name, FILES);
    const tools = tickerSelect(tk, list, "fa-ticker");
    const src = "SEC EDGAR (data.sec.gov)";
    if (!x.ok) return panel({ title: `FA — ${esc(tk)}`, tools, body: dsUnavailable(x), meta: x.meta, source: src });
    const f = x.data;
    if (f.kind === "na") {
      return panel({ title: `FA — ${esc(tk)}`, tools, meta: x.meta, source: src,
        body: `<div class="unavail"><b>${t(f.reason === "etf" ? "fa.na_etf" : "fa.na_nosource")}</b></div>` });
    }
    const quarterly = f.kind === "quarterly_us_gaap";
    const rows = f.rows || [];
    const maxRev = Math.max(...rows.map(r => Math.abs(r.revenue || r.net_income || 0)));
    const scale = maxRev >= 1e9 ? 1e9 : 1e6, unitLbl = scale === 1e9 ? t("unit.bn") : t("unit.mn");
    const money = (r, k) => (isNum(r[k]) ? num(r[k] / scale, 2) + (r.derived.includes(k) ? "*" : "") : "—");
    const colHead = rows.map(r => `<th title="${esc(r.start)} → ${esc(r.end)}">${fmtDate(r.end)}</th>`).join("");
    const tr = (label, fn) => `<tr><td class="l">${label}</td>${rows.map(r => `<td>${fn(r)}</td>`).join("")}</tr>`;
    const table = rows.length ? `<table class="t"><tr><th>${t(quarterly ? "fa.quarter_end" : "fa.year_end")}</th>${colHead}</tr>
      ${tr(`${t("fa.revenue")} (${unitLbl} ${esc(f.unit || "")})`, r => money(r, "revenue"))}
      ${tr(`${t("fa.net_income")} (${unitLbl} ${esc(f.unit || "")})`, r => money(r, "net_income"))}
      ${tr(`${t("fa.eps")} (${esc(f.eps_unit || "")})`, r => (isNum(r.eps_diluted) ? num(r.eps_diluted, 2) + (r.derived.includes("eps_diluted") ? "*" : "") : "—"))}
      ${tr(t("fa.gross_margin"), r => (isNum(r.gross_margin) ? pct(r.gross_margin, 1, false) : (f.tags.gross_profit ? "—" : "n/a")))}
      ${tr(t("fa.net_margin"), r => `<span class="${cls(r.net_margin)}">${pct(r.net_margin, 1, false)}</span>`)}
    </table>` : `<div class="unavail">${t("fa.no_rows")}</div>`;
    const tags = Object.entries(f.tags || {}).map(([k, v]) => `${esc(k)}: <b>${esc(v || "—")}</b>`).join(" · ");
    const notes = `<p class="note">${quarterly ? t("fa.q4_note") : t("fa.ifrs_note")}<br>${t("fa.tags")}: ${tags}<br>
      ${esc(f.entity || "")} · CIK ${esc(f.cik)} · ${t("fa.fye")} ${esc(f.fiscal_year_end || "—")}${f.sec_ticker !== tk ? ` · ADR ${esc(f.sec_ticker)}` : ""}</p>`;
    const filings = (f.filings || []).map(fl => `<tr><td class="tk">${esc(fl.form)}</td><td>${fmtDate(fl.filed)}</td>
      <td>${fmtDate(fl.report_date)}</td><td class="l note">${esc(fl.items || "")}</td><td class="l"><a href="${esc(safeUrl(fl.url))}" target="_blank" rel="noopener">${t("open")} ↗</a></td></tr>`).join("");
    return panel({ title: `FA — ${esc(tk)} ${quarterly ? t("fa.last8q") : t("fa.last4y")}`, tools, cls: "span-8", body: table + notes, meta: x.meta, source: src,
        stale: dailyStale(x.meta.fetched_at) }) +
      panel({ title: t("fa.filings"), cls: "span-4", meta: x.meta, source: src,
        body: filings ? `<table class="t"><tr><th>${t("fa.form")}</th><th>${t("fa.filed")}</th><th>${t("fa.period")}</th><th class="l">${t("fa.items")}</th><th></th></tr>${filings}</table>` : `<div class="note">—</div>` });
  }

  // ------------------------------------------------------------------ RISK
  function heatColor(v) {
    if (!isNum(v)) return "#222";
    const mix = (a, b, k) => a.map((x, i) => Math.round(x + (b[i] - x) * k));
    const mid = [58, 58, 58], neg = [61, 155, 233], pos = [201, 122, 10];
    const c = v >= 0 ? mix(mid, pos, Math.min(1, v)) : mix(mid, neg, Math.min(1, -v));
    return `rgb(${c.join(",")})`;
  }
  function renderRISK() {
    const m = meta(); if (!m) return firstRunNotice();
    const x = ds("risk.json");
    if (!x.ok) return panel({ title: t("risk.title"), body: dsUnavailable(x), meta: x.meta, source: t("risk.source") });
    const wl = watchlist(), R = x.data;
    const rows = wl.map(tk => {
      const r = R.metrics[tk];
      if (!r || r.status !== "ok") return `<tr class="click" data-goto="${esc(tk)}"><td class="tk">${esc(tk)}</td><td class="nm">${esc((UNI[tk] || {}).name)}</td><td class="na" colspan="8">${t("unavailable")} — ${esc(r ? r.error : "—")}</td></tr>`;
      return `<tr class="click" data-goto="${esc(tk)}"><td class="tk">${esc(tk)}</td><td class="nm">${esc((UNI[tk] || {}).name)}</td>
        <td>${pct(r.ann_vol, 1, false)}</td><td class="${cls(r.ann_return)}">${pct(r.ann_return, 1)}</td>
        <td class="${cls(r.sharpe)}" title="${esc(r.sharpe_note || "")}">${num(r.sharpe, 2)}</td><td>${num(r.beta, 2)} <span class="note">${esc(r.benchmark)}</span></td>
        <td class="down">${pct(r.max_drawdown, 1)}</td><td>${pct(r.rf, 2, false)} <span class="note">${esc(r.rf_series || "")}</span></td>
        <td class="note">${fmtDate(r.start)} → ${fmtDate(r.end)}</td><td>${r.n_returns}</td></tr>`;
    }).join("");
    const table = `<table class="t"><tr><th>${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th><th>${t("risk.vol")}</th><th>${t("risk.ret")}</th>
      <th>${t("risk.sharpe")}</th><th>${t("risk.beta")}</th><th>${t("risk.mdd")}</th><th>${t("risk.rf")}</th><th>${t("risk.window")}</th><th>${t("risk.n")}</th></tr>${rows}</table>
      <p class="note">${t("risk.defs")}</p>`;
    const cm = C.correlationMatrix(R.returns, wl);
    const short = tk => esc(tk.replace(/\..*$/, ""));
    const heat = cm.tickers.length >= 2 ? `<div style="overflow-x:auto"><table class="heat"><tr><th></th>${cm.tickers.map(tk => `<th class="rot"><span>${short(tk)}</span></th>`).join("")}</tr>
      ${cm.tickers.map((a, i) => `<tr><th style="text-align:right">${short(a)}</th>${cm.matrix[i].map((v, j) =>
        `<td style="background:${heatColor(v)}" title="${esc(a)} / ${esc(cm.tickers[j])}: ${num(v, 2)}">${isNum(v) ? num(v, 2).replace(/^0([.,])/, "$1").replace(/^-0([.,])/, "-$1") : "—"}</td>`).join("")}</tr>`).join("")}
      </table></div><div class="legend-bar">−1 <i></i> +1 · ${t("risk.common_days", { n: cm.n })}</div>` : `<div class="note">${t("risk.need2")}</div>`;
    return panel({ title: t("risk.title"), body: table, meta: x.meta, source: t("risk.source"), stale: dailyStale(x.meta.fetched_at) }) +
      panel({ title: t("risk.corr"), cls: "span-8", body: heat, meta: x.meta, source: t("risk.source") }) +
      validationPanel();
  }
  function validationPanel() {
    const v = ds("validation.json");
    if (!v.ok) return panel({ title: t("val.title"), cls: "span-4", body: dsUnavailable(v), meta: v.meta, source: "yfinance" });
    const rows = v.data.checks.map(c => `<tr><td class="tk">${esc(c.ticker)}</td><td class="note">${fmtDate(c.date)}</td>
      <td>${num(c.site_last_close)}<br><span class="note">${num(c.manual_last_close)}</span></td><td class="${c.price_match ? "up" : "down"}">${c.price_match ? "OK" : "KO"}</td>
      <td>${pct(c.site_vol_1y, 2, false)}<br><span class="note">${pct(c.manual_vol_1y, 2, false)}</span></td><td class="${c.vol_match ? "up" : "down"}">${c.vol_match ? "OK" : "KO"}</td></tr>`).join("");
    return panel({ title: t("val.title"), cls: "span-4", meta: v.meta, source: v.meta.source,
      body: `<table class="t"><tr><th>${t("col.ticker")}</th><th>${t("col.date")}</th><th>${t("val.price")}</th><th></th><th>${t("val.vol")}</th><th></th></tr>${rows}</table>
        <p class="note">${t("val.note")}</p><b class="${v.data.all_passed ? "ok-badge" : "ko-badge"}">${v.data.all_passed ? t("val.pass") : t("val.fail")}</b>` });
  }

  // ------------------------------------------------------------------ NEWS
  function newsList(items, lang) {
    if (!items || !items.length) return `<div class="note">${t("news.none")}</div>`;
    return items.map(h => {
      const sent = h.sentiment
        ? `<span class="sent ${esc(h.sentiment)}">${t("sent." + h.sentiment)} ${num(h.confidence * 100, 0)} %</span>`
        : `<span class="sent">${lang === "fr" ? t("sent.na_fr") : t("sent.na")}</span>`;
      return `<div class="news-item"><span class="when">${fmtDT(h.published)}<span class="src">${esc(h.publisher || "—")}<span class="feed">${esc(h.feed)}</span></span></span>
        <a href="${esc(safeUrl(h.link))}" target="_blank" rel="noopener">${esc(h.title)}</a>${sent}</div>`;
    }).join("");
  }
  function renderNEWS() {
    const m = meta(); if (!m) return firstRunNotice();
    const x = ds("news.json");
    const wl = watchlist();
    const tools = `<select data-action="news-ticker"><option value="ALL">${t("news.all")}</option>${wl.map(tk => `<option value="${esc(tk)}" ${S.newsTicker === tk ? "selected" : ""}>${esc(tk)}</option>`).join("")}</select>`;
    if (!x.ok) return panel({ title: t("news.title"), tools, body: dsUnavailable(x), meta: x.meta, source: "Yahoo Finance + Google News RSS" });
    const list = S.newsTicker === "ALL" ? wl : [S.newsTicker];
    const body = list.map(tk => {
      const n = x.data[tk];
      if (!n) return `<div class="news-tk">${esc(tk)}</div><div class="note">—</div>`;
      if (n.status !== "ok") return `<div class="news-tk">${esc(tk)}</div>${unavailable((n.errors || []).join(" | "), x.meta.last_success)}`;
      const a = n.avg;
      const avg = a ? `<span class="avg">${t("news.avg")}: <b class="${cls(a.score)}">${signed(a.score, 2)}</b> (${a.positive}+ / ${a.neutral}= / ${a.negative}− ${t("news.on_n", { n: a.n })})</span>` : `<span class="avg">${t("news.avg")}: —</span>`;
      return `<div class="news-tk">${esc(tk)} <span class="note">${esc((UNI[tk] || {}).name)}</span>${avg}</div>
        ${newsList(n.en, "en")}${n.fr ? `<div class="note" style="margin-top:6px">${t("news.fr_section")}</div>${newsList(n.fr, "fr")}` : ""}
        ${n.errors && n.errors.length ? `<div class="note">${t("news.partial")}: ${esc(n.errors.join(" | "))}</div>` : ""}`;
    }).join("");
    const sentErr = x.meta.sentiment_error ? `<div class="unavail">${t("news.sent_error")}: <span class="err">${esc(x.meta.sentiment_error)}</span></div>` : "";
    return panel({ title: t("news.title"), tools, body: sentErr + body + `<p class="note">${t("news.method")}</p>`, meta: x.meta, stale: newsStale(x.meta.fetched_at) });
  }

  // ------------------------------------------------------------------ ECO
  async function renderECO() {
    const x = ds("macro.json");
    const fx = await historyOf("EURUSD=X");
    if (!x.ok) return { html: panel({ title: t("eco.title"), body: dsUnavailable(x), meta: x.meta, source: "FRED + ECB" }) };
    const m = x.data, errs = x.meta.errors || {};
    const st = dailyStale(x.meta.fetched_at);
    const missing = ids => ids.filter(id => !m[id]).map(id => `${id}: ${errs[id] || t("unavailable")}`);
    const chartPanel = (id, title, ids, cls, src) => {
      const miss = missing(ids);
      return panel({ title, cls, meta: x.meta, source: src || "FRED", stale: st,
        body: `<div class="chart" id="${id}"></div>` + (miss.length ? `<div class="unavail"><b>${t("unavailable")}</b><span class="err">${esc(miss.join(" | "))}</span></div>` : "") });
    };
    const lastPt = id => (m[id] ? m[id].latest : null);
    const curve = [["3M", "DGS3MO"], ["2Y", "DGS2"], ["10Y", "DGS10"]].map(([k, id]) => ({ k, p: lastPt(id) }));
    const html =
      chartPanel("ecoRates", t("eco.rates"), ["DFF", "DGS3MO", "DGS2", "DGS10"], "span-8") +
      panel({ title: t("eco.curve"), cls: "span-4", meta: x.meta, source: "FRED (DGS3MO, DGS2, DGS10)", stale: st, body: curveSVG(curve) }) +
      chartPanel("ecoInfl", t("eco.inflation"), ["CPIAUCSL", "HICP_EA"], "span-6", "FRED (CPIAUCSL) + ECB (HICP)") +
      chartPanel("ecoUnemp", t("eco.unemp"), ["UNRATE"], "span-6") +
      chartPanel("ecoEcb", t("eco.ecb"), ["ECBDFR"], "span-6", "FRED (ECBDFR)") +
      panel({ title: t("eco.eurusd") + " " + delayed(), cls: "span-6", meta: fx.meta, source: "Yahoo Finance (EURUSD=X)",
        body: fx.ok ? `<div class="chart" id="ecoFx"></div>` : dsUnavailable(fx) });
    const after = () => {
      const tbl = id => [m[id].dates.map(toTs), m[id].values];
      const p2 = v => pctPts(v, 2);
      const avail = ids => ids.filter(id => m[id]);
      const rateIds = avail(["DFF", "DGS3MO", "DGS2", "DGS10"]);
      const colors = { DFF: PAL.amber, DGS3MO: PAL.blue, DGS2: PAL.pink, DGS10: PAL.green };
      const labels = { DFF: t("macro.dff"), DGS3MO: "UST 3M", DGS2: "UST 2Y", DGS10: "UST 10Y" };
      if (rateIds.length) makeChart($("#ecoRates"), rateIds.map(id => line(labels[id], colors[id], p2)), uPlot.join(rateIds.map(tbl)), { yfmt: v => num(v, 1) });
      const inf = [];
      if (m.CPIAUCSL && m.CPIAUCSL.yoy) inf.push(["US CPI YoY", PAL.amber, [m.CPIAUCSL.yoy.dates.map(toTs), m.CPIAUCSL.yoy.values]]);
      if (m.HICP_EA) inf.push(["Euro area HICP", PAL.blue, tbl("HICP_EA")]);
      if (inf.length) makeChart($("#ecoInfl"), inf.map(([l, c]) => line(l, c, v => pctPts(v, 1))), uPlot.join(inf.map(z => z[2])), { yfmt: v => num(v, 1) });
      if (m.UNRATE) makeChart($("#ecoUnemp"), [line(t("eco.unemp_s"), PAL.amber, v => pctPts(v, 1))], tbl("UNRATE"), { yfmt: v => num(v, 1) });
      if (m.ECBDFR) makeChart($("#ecoEcb"), [line(t("macro.ecb"), PAL.blue, p2)], tbl("ECBDFR"), { yfmt: v => num(v, 1) });
      if (fx.ok) makeChart($("#ecoFx"), [line("EUR/USD", PAL.price, v => num(v, 4))], [fx.data.dates.map(toTs), fx.data.close], { yfmt: v => num(v, 2) });
    };
    return { html, after };
  }
  function curveSVG(pts) {
    const ok = pts.filter(p => p.p);
    if (ok.length < 2) return unavailable(t("eco.curve_missing"), null);
    const W = 360, H = 200, padL = 40, padR = 20, padT = 24, padB = 40;
    const vals = ok.map(p => p.p.value), lo = Math.min(0, ...vals), hi = Math.max(...vals) * 1.15;
    const x = i => padL + (i * (W - padL - padR)) / (pts.length - 1);
    const y = v => padT + (H - padT - padB) * (1 - (v - lo) / (hi - lo || 1));
    const path = pts.map((p, i) => (p.p ? `${i === 0 || !pts[i - 1].p ? "M" : "L"}${x(i)},${y(p.p.value)}` : "")).join(" ");
    const marks = pts.map((p, i) => (p.p ? `<circle cx="${x(i)}" cy="${y(p.p.value)}" r="5" fill="#FFA028" stroke="#07080a" stroke-width="2"><title>${p.k}: ${pctPts(p.p.value)} (${fmtDate(p.p.date)})</title></circle>
      <text x="${x(i)}" y="${y(p.p.value) - 10}" text-anchor="middle">${pctPts(p.p.value)}</text>` : "") +
      `<text class="lbl" x="${x(i)}" y="${H - padB + 18}" text-anchor="middle">${p.k}</text>`).join("");
    const dates = [...new Set(ok.map(p => p.p.date))].map(d => fmtDate(d)).join(", ");
    return `<svg class="curve" viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(t("eco.curve"))}">
      <line class="ax" x1="${padL}" x2="${W - padR}" y1="${y(0)}" y2="${y(0)}"/>
      <path d="${path}" fill="none" stroke="#C97A0A" stroke-width="2"/>${marks}</svg>
      <div class="note">${t("eco.curve_note", { dates })}</div>`;
  }

  // ------------------------------------------------------------------ HELP
  function renderHELP() {
    const cmds = [["AAPL", "help.quote"], ["AAPL FA", "help.fa"], ["MC.PA RISK", "help.risk"], ["NVDA NEWS", "help.news"],
      ["MKTS", "help.mkts"], ["ECO", "help.eco"], ["LANG FR / LANG EN", "help.lang"], ["HELP", "help.help"]];
    return panel({ title: "HELP", updated: null, source: "Atlas Terminal",
      body: `<div class="help-list">${cmds.map(([c, k]) => `<code>${c}</code> — ${t(k)}`).join("<br>")}</div><p class="note">${t("help.more")}</p>` });
  }

  // ------------------------------------------------------------------ render loop
  let renderSeq = 0;
  async function render() {
    const seq = ++renderSeq;
    renderTabs(); renderClocks();
    const fn = { MKTS: renderMKTS, QUOTE: renderQUOTE, FA: renderFA, RISK: renderRISK, NEWS: renderNEWS, ECO: renderECO, HELP: renderHELP }[S.tab];
    let out = await fn();
    if (seq !== renderSeq) return;            // a newer render started meanwhile
    if (typeof out === "string") out = { html: out };
    destroyCharts();
    $("#main").innerHTML = out.html;
    if (out.after) out.after();
    const hash = "#" + S.tab + (["QUOTE", "FA"].includes(S.tab) ? "/" + encodeURIComponent(S.ticker) : "");
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }
  function go(tab, ticker) {
    if (ticker) S.ticker = ticker;
    S.tab = tab;
    $("#cmdMsg").textContent = "";
    render();
  }

  // ------------------------------------------------------------------ command bar
  function onCommand(e) {
    e.preventDefault();
    const input = $("#cmd");
    const m = meta();
    const res = C.parseCommand(input.value, m ? m.universe.map(u => u.ticker) : []);
    if (res.type === "none") return;
    if (res.type === "error") { $("#cmdMsg").textContent = t(res.key, { arg: res.arg || "" }); return; }
    input.value = "";
    if (res.type === "lang") return setLang(res.lang);
    if (res.type === "help") return go("HELP");
    if (res.type === "tab") return go(res.tab);
    if (res.type === "ticker") {
      if (res.tab === "NEWS") S.newsTicker = watchlist().includes(res.ticker) ? res.ticker : "ALL";
      return go(res.tab, res.ticker);
    }
  }

  // ------------------------------------------------------------------ settings & watchlist dialogs
  async function setLang(lang) {
    S.lang = lang; LS.set("lang", lang);
    await loadI18n();
    applyStaticI18n(); renderSettings(); render();
  }
  function seg(key, options) {
    return `<span class="seg">${options.map(([v, label]) => `<button data-set="${key}" data-val="${esc(JSON.stringify(v))}" class="${S[key] === v ? "on" : ""}">${label}</button>`).join("")}</span>`;
  }
  function renderSettings() {
    $("#settingsBody").innerHTML = `
      <div class="setting"><span>${t("settings.lang")}</span>${seg("lang", [["fr", "Français"], ["en", "English"]])}</div>
      <div class="setting"><span>${t("settings.numfmt")}</span>${seg("numfmt", [["fr", "1 234,56"], ["us", "1,234.56"]])}</div>
      <div class="setting"><span>${t("settings.tz")}</span>${seg("tz", [["Europe/Paris", "Paris"], ["America/New_York", "New York"]])}</div>
      <div class="setting"><span>${t("settings.auto")}</span>${seg("auto", [[true, t("on")], [false, t("off")]])}</div>
      <div class="setting"><span>${t("settings.reset_wl")}</span><button class="btn" data-action="reset-wl">${t("settings.reset")}</button></div>
      <p class="note">${t("settings.note")}</p>`;
  }
  function renderWlEditor() {
    const m = meta(); if (!m) return;
    const wl = watchlist();
    const byRegion = r => m.watchlist_universe.filter(tk => UNI[tk].region === r);
    const box = tk => `<label><input type="checkbox" data-wl="${esc(tk)}" ${wl.includes(tk) ? "checked" : ""}>${esc(tk)} <span>${esc(UNI[tk].name)}</span></label>`;
    $("#wlBody").innerHTML = ["US", "EU"].map(r => `<div class="wl-h">${t("region." + r)}</div><div class="wl-grid">${byRegion(r).map(box).join("")}</div>`).join("") +
      `<p class="note">${t("wl.note")}</p>`;
  }
  function openDialog(id) { $(id).hidden = false; }
  function closeDialogs() { document.querySelectorAll(".overlay").forEach(o => { o.hidden = true; }); }

  // ------------------------------------------------------------------ events
  function bind() {
    $("#cmdForm").addEventListener("submit", onCommand);
    $("#gearBtn").addEventListener("click", () => { renderSettings(); openDialog("#settings"); });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") closeDialogs();
      if (e.key === "/" && document.activeElement !== $("#cmd")) { e.preventDefault(); $("#cmd").focus(); }
    });
    document.addEventListener("click", async e => {
      const el = e.target.closest("[data-tab],[data-goto],[data-range],[data-action],[data-set],[data-close]");
      if (!el) { if (e.target.classList.contains("overlay")) closeDialogs(); return; }
      if (el.dataset.close !== undefined) return closeDialogs();
      if (el.dataset.tab) return go(el.dataset.tab);
      if (el.dataset.goto) return go("QUOTE", el.dataset.goto);
      if (el.dataset.range) { S.range = el.dataset.range; LS.set("range", S.range); return render(); }
      if (el.dataset.set) {
        const key = el.dataset.set, val = JSON.parse(el.dataset.val);
        if (key === "lang") return setLang(val);
        S[key] = val; LS.set(key, val);
        renderSettings(); applyStaticI18n(); return render();
      }
      const a = el.dataset.action;
      if (a === "edit-wl") { renderWlEditor(); openDialog("#wlEditor"); }
      if (a === "reset-wl") { S.watchlist = null; LS.set("watchlist", null); closeDialogs(); render(); }
    });
    document.addEventListener("change", e => {
      const el = e.target;
      if (el.dataset.action === "quote-ticker") go("QUOTE", el.value);
      if (el.dataset.action === "fa-ticker") go("FA", el.value);
      if (el.dataset.action === "news-ticker") { S.newsTicker = el.value; render(); }
      if (el.dataset.wl) {
        const set = new Set(watchlist());
        if (el.checked) set.add(el.dataset.wl); else set.delete(el.dataset.wl);
        const m = meta();
        S.watchlist = m.watchlist_universe.filter(tk => set.has(tk));
        LS.set("watchlist", S.watchlist);
        render();
      }
    });
    let rz;
    window.addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => { if (charts.length) render(); }, 250); });
  }

  // ------------------------------------------------------------------ boot & auto refresh
  async function loadI18n() {
    try { I18N = await (await fetch("i18n/" + S.lang + ".json", { cache: "no-store" })).json(); }
    catch (e) { I18N = {}; }
  }
  async function loadCore() {
    await Promise.all(CORE.map(n => load(n)));
    const m = meta();
    UNI = {};
    if (m) m.universe.forEach(u => { UNI[u.ticker] = u; });
  }
  function signature() {
    return CORE.map(n => {
      const x = D[n]; if (!x || !x.ok) return n + ":x";
      const mm = x.env._meta || {};
      return n + ":" + (mm.fetched_at || x.env.generated_at || "") + JSON.stringify(mm.regions || "");
    }).join("|");
  }
  async function refresh() {
    if (!S.auto) return;
    const before = signature();
    await loadCore();
    if (signature() !== before) {
      Object.keys(FILES).forEach(k => delete FILES[k]);
      render();
    }
  }
  function routeFromHash() {
    const [tab, tk] = decodeURIComponent(location.hash.slice(1)).split("/");
    if (C.TABS.includes(tab) || tab === "HELP") S.tab = tab;
    if (tk) S.ticker = tk;
  }
  async function boot() {
    routeFromHash();
    await loadI18n();
    applyStaticI18n();
    bind();
    await loadCore();
    render();
    setInterval(refresh, 60000);
    setInterval(renderClocks, 30000);
  }
  boot();
})();
