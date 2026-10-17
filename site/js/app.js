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
    auto: LS.get("auto", true), watchlist: LS.get("watchlist", null), translate: LS.get("translate", true),
    tab: "MKTS", ticker: "AAPL", range: LS.get("range", "1Y"), newsTicker: "ALL", faTicker: null,
    eqs: Object.assign({ region: "EU", segment: "ALL", country: "ALL", sort: "pct", dir: -1 }, LS.get("eqs", {})),
    comps: { sector: null, region: LS.get("compsRegion", "ALL") }, deals: { ticker: "ALL" },
    hp: LS.get("hp", "D"), most: { region: LS.get("mostRegion", "ALL") },
  };
  // tab groups, coloured like the function-key families of a terminal keyboard
  const TAB_GROUP = { LP: "g-home", MKTS: "g-mkt", WEI: "g-mkt", MOST: "g-mkt", FXC: "g-mkt", ECO: "g-mkt", EQS: "g-mkt",
    QUOTE: "g-sec", GIP: "g-sec", HP: "g-sec", DES: "g-sec", FA: "g-sec", DVD: "g-sec", RISK: "g-sec", NEWS: "g-sec", COMPS: "g-sec", DEALS: "g-sec", STATUS: "g-sys" };
  const TICKER_TABS = ["QUOTE", "GIP", "HP", "DES", "FA", "DVD", "COMPS"];
  const CORE = ["meta.json", "quotes.json", "risk.json", "macro.json", "news.json", "validation.json", "companies.json", "deals.json", "perf.json", "intraday.json", "status.json"];

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
  const fmtTime = ts => new Intl.DateTimeFormat(dlocale(), { timeZone: S.tz, hour: "2-digit", minute: "2-digit" }).format(new Date(ts * 1000)) + " " + tzLabel();
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
      `<button class="tab ${TAB_GROUP[tab] || ""} ${S.tab === tab ? "active" : ""}" data-tab="${tab}" title="${esc(t("tab." + tab))}">${tab}<span class="note"> ${t("tab." + tab)}</span></button>`).join("");
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
      return `<tr class="click" data-goto="${esc(tk)}"><td class="tk" title="${esc(info.name)}">${esc(tk)}</td>${nameCell}
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
    // compact panels: no name column (the name is in the ticker's tooltip)
    const head = `<tr><th>${t("col.ticker")}</th><th>${t("col.last")}</th><th>${t("col.chg")}</th><th>${t("col.pct")}</th><th>${t("col.date")}</th></tr>`;
    return panel({ title: `${title} ${delayed()}`, cls, stale, updated: upd, source: "Yahoo Finance (yfinance)",
      body: (regErr.length ? `<div class="unavail"><b>${t("unavailable")}</b><span class="err">${esc(regErr.join(" | "))}</span></div>` : "") + `<table class="t">${head}${quoteRows(tickers, { noName: true })}</table>` });
  }
  function macroStrip() {
    const x = ds("macro.json");
    if (!x.ok) return panel({ title: t("mkts.macro"), body: dsUnavailable(x), meta: x.meta, source: "FRED / US Treasury / NY Fed / BLS / ECB" });
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
      quotesPanel(t("mkts.fx"), ["EURUSD=X", "EURGBP=X", "EURCHF=X", "BZ=F", "GC=F"], ["US", "EU"], "span-4") +
      panel({ title: `${t("mkts.watchlist")} ${delayed()}`, tools: `<button class="btn" data-action="edit-wl">${t("wl.edit")}</button>`,
        updated: regs.length ? regs.map(r => r.fetched_at).sort().pop() : null, source: "Yahoo Finance (yfinance)",
        stale: wl.some(tk => q && q.data[tk] && quoteStale(tk, q.data[tk].fetched_at)),
        body: wl.length ? `<table class="t">${head}${groups}</table>` : `<div class="note">${t("wl.empty")}</div>` }) +
      earningsPanel();
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
      tzDate: ts => uPlot.tzDate(new Date(ts * 1e3), o.xtime ? S.tz : "Etc/UTC"),
      cursor: { sync: o.sync ? { key: o.sync } : undefined, drag: { x: true, y: false }, points: { size: 7 } },
      scales: Object.assign({ x: { time: true } }, o.scales || {}),
      axes: [xAxis(), axis(o.yfmt, o.ysize)].concat(o.extraAxes || []),
      series: [{ label: o.xtime ? t("gip.time") : t("col.date"), value: (u, v) => (v == null ? "—" : o.xtime ? fmtTime(v) : fmtDate(new Date(v * 1000).toISOString().slice(0, 10))) }].concat(series),
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
    const html = panel({ title: `<span class="sec">${esc(C.bbgCode(tk, info))}</span> ${esc(info.name)} <span class="note">${esc(tk)}</span>`, tools, body, meta: h.meta, source: "Yahoo Finance (yfinance)",
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
    const html = await renderFAsec();
    return (UNI[tk] && UNI[tk].region === "EU" && UNI[tk].kind === "stock") ? html + await esefPanel(tk) : html;
  }
  async function renderFAsec() {
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
        body: `<div class="unavail"><b>${t(f.reason === "etf" ? "fa.na_etf" : f.reason === "no_recent_sec_data" ? "fa.na_stale" : "fa.na_nosource")}</b>
          ${f.last_period ? `<span class="note">${t("fa.last_period")}: ${fmtDate(f.last_period)}</span>` : ""}</div>` });
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
    const notes = `<p class="note">${quarterly ? t("fa.q4_note") : t(f.kind === "annual_usgaap_20f" ? "fa.usgaap20f_note" : "fa.ifrs_note")}<br>${t("fa.tags")}: ${tags}<br>
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
    const table = `<table class="t"><tr><th>${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th>${th("vol", t("risk.vol"))}${th("ret", t("risk.ret"))}
      ${th("sharpe", t("risk.sharpe"))}${th("beta", t("risk.beta"))}${th("mdd", t("risk.mdd"))}${th("rf", t("risk.rf"))}<th>${t("risk.window")}</th><th>${t("risk.n")}</th></tr>${rows}</table>
      <p class="note">${t("risk.defs")}</p>`;
    const cm = C.correlationMatrix(R.returns, wl);
    const short = tk => esc(tk.replace(/\..*$/, ""));
    const heat = cm.tickers.length >= 2 ? `<div style="overflow-x:auto"><table class="heat"><tr><th></th>${cm.tickers.map(tk => `<th class="rot"><span>${short(tk)}</span></th>`).join("")}</tr>
      ${cm.tickers.map((a, i) => `<tr><th style="text-align:right">${short(a)}</th>${cm.matrix[i].map((v, j) =>
        `<td style="background:${heatColor(v)}" title="${esc(a)} / ${esc(cm.tickers[j])}: ${num(v, 2)}">${isNum(v) ? num(v, 2).replace(/^0([.,])/, "$1").replace(/^-0([.,])/, "-$1") : "—"}</td>`).join("")}</tr>`).join("")}
      </table></div><div class="legend-bar">−1 <i></i> +1 · ${t("risk.common_days", { n: cm.n })}</div>` : `<div class="note">${t("risk.need2")}</div>`;
    return panel({ title: t("risk.title"), body: table, meta: x.meta, source: t("risk.source"), stale: dailyStale(x.meta.fetched_at), tools: csvBtn() }) +
      panel({ title: t("risk.corr"), cls: "span-8", body: heat, meta: x.meta, source: t("risk.source"), tools: csvBtn() }) +
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
      // French UI + translation on: show the machine translation, original title on hover
      const useFr = S.lang === "fr" && S.translate && h.title_fr && C.numbersSubset(h.title, h.title_fr);
      const title = useFr
        ? `<a href="${esc(safeUrl(h.link))}" target="_blank" rel="noopener" title="${esc(t("news.mt_tip") + " " + h.title)}">${esc(h.title_fr)}</a> <span class="mt">${t("news.mt")}</span>`
        : `<a href="${esc(safeUrl(h.link))}" target="_blank" rel="noopener">${esc(h.title)}</a>`;
      return `<div class="news-item"><span class="when">${fmtDT(h.published)}<span class="src">${esc(h.publisher || "—")}<span class="feed">${esc(h.feed)}</span></span></span>
        <span>${title}</span>${sent}</div>`;
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
    const trErr = x.meta.translation_error && S.lang === "fr" && S.translate ? `<div class="unavail">${t("news.translation_error")}: <span class="err">${esc(x.meta.translation_error)}</span></div>` : "";
    return panel({ title: t("news.title"), tools, body: sentErr + trErr + body + `<p class="note">${t("news.method")}</p>`, meta: x.meta, stale: newsStale(x.meta.fetched_at) });
  }

  // ------------------------------------------------------------------ ECO
  async function renderECO() {
    const x = ds("macro.json");
    const fx = await historyOf("EURUSD=X");
    if (!x.ok) return { html: panel({ title: t("eco.title"), body: dsUnavailable(x), meta: x.meta, source: "FRED / US Treasury / NY Fed / BLS / ECB" }) };
    const m = x.data, errs = x.meta.errors || {};
    const st = dailyStale(x.meta.fetched_at);
    const missing = ids => ids.filter(id => !m[id]).map(id => `${id}: ${errs[id] || t("unavailable")}`);
    const srcOf = ids => [...new Set(ids.filter(i => m[i]).map(i => m[i].source))].join(" · ") || "—";
    const chartPanel = (id, title, ids, cls) => {
      const miss = missing(ids);
      return panel({ title, cls, meta: x.meta, source: srcOf(ids), stale: st,
        body: `<div class="chart" id="${id}"></div>` + (miss.length ? `<div class="unavail"><b>${t("unavailable")}</b><span class="err">${esc(miss.join(" | "))}</span></div>` : "") });
    };
    const lastPt = id => (m[id] ? m[id].latest : null);
    const curve = [["3M", "DGS3MO"], ["2Y", "DGS2"], ["10Y", "DGS10"]].map(([k, id]) => ({ k, p: lastPt(id) }));
    const html =
      chartPanel("ecoRates", t("eco.rates"), ["DFF", "DGS3MO", "DGS2", "DGS10"], "span-8") +
      panel({ title: t("eco.curve"), cls: "span-4", meta: x.meta, source: srcOf(["DGS3MO", "DGS2", "DGS10"]), stale: st, body: curveSVG(curve) }) +
      chartPanel("ecoInfl", t("eco.inflation"), ["CPIAUCSL", "HICP_EA"], "span-6") +
      chartPanel("ecoUnemp", t("eco.unemp"), ["UNRATE"], "span-6") +
      chartPanel("ecoEcb", t("eco.ecb"), ["ECBDFR"], "span-6") +
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

  // ------------------------------------------------------------------ EQS (equity screener)
  const EQS_COLS = [
    ["ticker", "col.ticker", "l"], ["name", "col.name", "l nm"], ["country", "col.country", "l"], ["segment", "col.segment", "l", "size"],
    ["mcap", "col.mcap", "", "mcap"], ["last", "col.last"], ["pct", "col.pct"], ["perf", "col.perf1y", "", "perf1y"], ["vol", "risk.vol", "", "vol"],
    ["beta", "risk.beta", "", "beta"], ["mdd", "risk.mdd", "", "mdd"], ["sharpe", "risk.sharpe", "", "sharpe"], ["pe", "comps.pe", "", "pe"],
    ["next", "col.next_earnings", "", "next_earnings"],
  ];
  function eqsRows() {
    const m = meta(), q = quotesEnv(), r = ds("risk.json");
    const metrics = r.ok ? r.data.metrics : {};
    const wl = new Set(watchlist());
    return m.watchlist_universe.map(tk => {
      const u = UNI[tk], x = q && q.data[tk], k = metrics[tk] || {}, cr = compRow(tk) || {};
      const okq = x && x.status === "ok", okr = k.status === "ok";
      return {
        ticker: tk, name: u.name, country: u.country, segment: cr.size || "na", region: u.region,
        mcap: isNum(cr.market_cap_eur) ? cr.market_cap_eur : null, pe: isNum(cr.pe) ? cr.pe : null, next: cr.next_earnings || null,
        last: okq ? x.last : null, currency: okq ? x.currency : "", pct: okq ? x.pct : null, quoteErr: okq ? null : (x ? x.error : t("err.no_quote")),
        perf: okr ? k.perf_window : null, vol: okr ? k.ann_vol : null, beta: okr ? k.beta : null, mdd: okr ? k.max_drawdown : null,
        sharpe: okr ? k.sharpe : null, inWl: wl.has(tk), stale: okq && quoteStale(tk, x.fetched_at),
      };
    });
  }
  function renderEQS() {
    const m = meta(); if (!m) return firstRunNotice();
    const f = S.eqs;
    let rows = eqsRows();
    const countries = [...new Set(rows.filter(r => f.region === "ALL" || r.region === f.region).map(r => r.country))].sort();
    rows = rows.filter(r => (f.region === "ALL" || r.region === f.region)
      && (f.segment === "ALL" || r.segment === f.segment)
      && (f.country === "ALL" || r.country === f.country));
    const key = f.sort, dir = f.dir;
    rows.sort((a, b) => {
      const va = a[key], vb = b[key];
      if (va == null && vb == null) return a.ticker.localeCompare(b.ticker);
      if (va == null) return 1;            // missing values always last, whatever the direction
      if (vb == null) return -1;
      return (typeof va === "string" ? va.localeCompare(vb) : va - vb) * dir;
    });
    const sel = (name, options, cur) => `<select data-eqs="${name}">${options.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
    const tools = sel("region", [["ALL", t("eqs.all_regions")], ["US", t("region.US")], ["EU", t("region.EU")]], f.region) +
      sel("segment", [["ALL", t("eqs.all_sizes")], ["large", t("size.large")], ["mid", t("size.mid")], ["small", t("size.small")], ["na", t("size.na")]], f.segment) +
      sel("country", [["ALL", t("eqs.all_countries")]].concat(countries.map(c => [c, t("country." + c)])), f.country);
    const arrow = k => (k === f.sort ? (f.dir > 0 ? " ▲" : " ▼") : "");
    const head = `<tr><th></th>${EQS_COLS.map(([k, lbl, c, d]) => {
      const def = d && I18N["def." + d];
      return `<th class="${c || ""} sortable${def ? " def" : ""}" data-sort="${k}" title="${esc((def ? def + " — " : "") + t("eqs.sort"))}">${t(lbl)}${arrow(k)}</th>`;
    }).join("")}</tr>`;
    const body = rows.map(r => `<tr class="click" data-goto="${esc(r.ticker)}">
      <td><button class="star ${r.inWl ? "on" : ""}" data-star="${esc(r.ticker)}" title="${esc(t(r.inWl ? "eqs.remove_wl" : "eqs.add_wl"))}">${r.inWl ? "★" : "☆"}</button></td>
      <td class="tk l">${esc(r.ticker)}</td><td class="nm">${esc(r.name)}</td><td class="l">${esc(r.country)}</td><td class="l note">${t("size." + r.segment)}</td>
      <td>${bn(r.mcap)}</td>
      ${r.last == null ? `<td class="na" colspan="2" title="${esc(r.quoteErr || "")}">${t("unavailable")}</td>`
        : `<td>${num(r.last, r.last < 10 ? 4 : 2)} <span class="note">${esc(r.currency)}</span>${r.stale ? ` <span class="stale">${t("stale")}</span>` : ""}</td><td class="${cls(r.pct)}">${pct(r.pct)}</td>`}
      <td class="${cls(r.perf)}">${pct(r.perf, 1)}</td><td>${pct(r.vol, 1, false)}</td><td>${num(r.beta, 2)}</td>
      <td class="${isNum(r.mdd) ? "down" : ""}">${pct(r.mdd, 1)}</td><td class="${cls(r.sharpe)}">${num(r.sharpe, 2)}</td>
      <td>${mult(r.pe)}</td><td class="note">${r.next ? fmtDate(r.next) : "—"}</td></tr>`).join("");
    const q = quotesEnv(), regs = q ? Object.values(q._meta.regions || {}) : [];
    const r = ds("risk.json");
    return panel({ title: `EQS — ${t("eqs.title")} ${delayed()}`, tools: tools + csvBtn(),
      updated: regs.length ? regs.map(x => x.fetched_at).sort().pop() : null,
      source: "Yahoo Finance (yfinance) · " + t("risk.source"),
      body: `<div class="note">${t("eqs.count", { n: rows.length })} · ${t("eqs.help")}</div><table class="t">${head}${body}</table>
        <p class="note">${t("eqs.defs")}${r.ok ? " " + t("eqs.risk_asof", { d: fmtDT(r.meta.fetched_at) }) : ""}</p>` });
  }

  // ------------------------------------------------------------------ shared: definitions, CSV, companies index
  // header cell with the metric's definition on hover (glossary in HELP)
  function th(defKey, label, extra) {
    const d = I18N["def." + defKey];
    return `<th class="${extra || ""}${d ? " def" : ""}"${d ? ` title="${esc(d)}"` : ""}>${label}</th>`;
  }
  const csvBtn = () => `<button class="btn" data-csv title="${esc(t("csv.tip"))}">CSV</button>`;
  function exportCsv(btn) {
    const panelEl = btn.closest(".panel");
    const table = panelEl && panelEl.querySelector("table.t, table.heat");
    if (!table) return;
    const sep = S.numfmt === "fr" ? ";" : ",";
    const cell = c => {
      const s = c.innerText.replace(/[★☆▲▼↗]/g, "").replace(/\s+/g, " ").trim();
      return /[";,\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [...table.rows].map(r => [...r.cells].map(cell).join(sep));
    const tEl = panelEl.querySelector(".ph-title");
    const title = tEl ? [...tEl.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(" ").trim() || tEl.innerText : "atlas";
    const name = "atlas-" + title.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "").slice(0, 40) + ".csv";
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });   // BOM so Excel reads UTF-8
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  const companies = () => ds("companies.json");
  const compRow = tk => { const c = companies(); return c.ok ? c.data.rows[tk] : null; };
  const bn = v => (isNum(v) ? num(v / 1e9, v >= 1e11 ? 0 : 1) : "—");       // EUR billions
  const mult = v => (isNum(v) ? num(v, 1) + "x" : "—");

  // ------------------------------------------------------------------ earnings calendar (MKTS)
  function earningsPanel() {
    const c = companies();
    if (!c.ok) return panel({ title: t("cal.title"), cls: "span-12", body: dsUnavailable(c), meta: c.meta, source: "Yahoo Finance" });
    const today = new Date().toISOString().slice(0, 10);
    const horizon = new Date(Date.now() + 45 * 864e5).toISOString().slice(0, 10);
    const wl = watchlist();
    const rows = wl.map(tk => [tk, c.data.rows[tk]]).filter(([, r]) => r && r.status === "ok" && r.next_earnings && r.next_earnings >= today && r.next_earnings <= horizon)
      .sort((a, b) => a[1].next_earnings.localeCompare(b[1].next_earnings));
    const body = rows.length ? `<table class="t"><tr><th class="l">${t("cal.date")}</th><th class="l">${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th>
        ${th("eps_est", t("cal.eps_est"))}${th("n_analysts", t("cal.n"))}</tr>
      ${rows.map(([tk, r]) => `<tr class="click" data-goto-des="${esc(tk)}"><td class="l">${fmtDate(r.next_earnings, { weekday: "short" })}</td><td class="tk l">${esc(tk)}</td>
        <td class="nm">${esc((UNI[tk] || {}).name)}</td><td>${num(r.eps_estimate_next)}</td><td>${r.n_analysts || "—"}</td></tr>`).join("")}</table>`
      : `<div class="note">${t("cal.none")}</div>`;
    return panel({ title: t("cal.title"), cls: "span-12", body: body + `<p class="note">${t("cal.note")}</p>`, meta: c.meta, source: "Yahoo Finance (calendarEvents)", tools: csvBtn() });
  }

  // ------------------------------------------------------------------ DES (company page)
  async function companyOf(tk) {
    const name = "company/" + C.safeName(tk) + ".json";
    if (!FILES[name]) await load(name, FILES);
    return ds(name, FILES);
  }
  async function esefOf(tk) {
    const name = "esef/" + C.safeName(tk) + ".json";
    if (!FILES[name]) await load(name, FILES);
    return ds(name, FILES);
  }
  function factSentence(f, ccy) {
    const p = (v, d = 1) => pct(v, d);
    switch (f.key) {
      case "rev_growth_fy": return t("fact.rev_growth_fy", { v: p(f.v), fy: fmtDate(f.fy) });
      case "net_margin_fy": return t("fact.net_margin_fy", { v: pct(f.v, 1, false), d: signed(f.delta_pts, 1) });
      case "rev_growth_q": return t("fact.rev_growth_q", { v: p(f.v), q: fmtDate(f.q) });
      case "eps_beats": return t("fact.eps_beats", { beats: f.beats, n: f.n });
      case "consensus_fy":
      case "consensus_next_fy":
        return t("fact." + f.key, { n: f.n, eps: p(f.eps_growth), end: fmtDate(f.end) }) +
          (isNum(f.rev_growth) ? t("fact.rev_part", { rev: p(f.rev_growth) }) : "") + ".";
      case "eps_revision_30d": return t("fact.eps_revision_30d", { v: p(f.v) });
      case "target_upside": return t("fact.target_upside", { mean: num(f.mean), n: f.n, v: p(f.v) });
      case "reco_split": return t("fact.reco_split", { buy: f.buy, hold: f.hold, sell: f.sell });
      case "leverage": return t("fact.leverage", { v: num(f.v, 1), fy: fmtDate(f.fy) });
      case "net_cash": return t("fact.net_cash", { v: compact(f.v) + " " + (ccy || ""), fy: fmtDate(f.fy) });
      case "next_earnings": return t("fact.next_earnings", { date: fmtDate(f.date, { weekday: "long", day: "numeric", month: "long", year: "numeric" }) });
      default: return null;
    }
  }
  function kv(label, value, defKey) {
    const d = defKey && I18N["def." + defKey];
    return `<div class="kv2"><span class="${d ? "def" : ""}"${d ? ` title="${esc(d)}"` : ""}>${label}</span><b>${value}</b></div>`;
  }
  function finTable(rows, ccy, quarterly) {
    if (!rows || !rows.length) return `<div class="note">${t(quarterly ? "des.no_quarters" : "des.no_statements")}</div>`;
    const money = v => (isNum(v) ? compact(v) : "—");
    const line = (label, fn, defKey) => `<tr>${th(defKey || "", label, "l").replace("<th", "<td").replace("</th>", "</td>")}${rows.map(r => `<td>${fn(r)}</td>`).join("")}</tr>`;
    const head = `<tr><th class="l">${t(quarterly ? "fa.quarter_end" : "fa.year_end")} (${esc(ccy || "")})</th>${rows.map(r => `<th>${fmtDate(r.end)}</th>`).join("")}</tr>`;
    const body = quarterly
      ? line(t("fa.revenue"), r => money(r.revenue)) + line(t("des.ebitda"), r => money(r.ebitda), "ebitda") +
        line(t("fa.net_income"), r => money(r.net_income)) + line(t("fa.net_margin"), r => pct(r.net_margin, 1, false), "net_margin") +
        line(t("fa.eps"), r => num(r.eps_diluted), "eps")
      : line(t("fa.revenue"), r => money(r.revenue)) + line(t("des.growth"), r => `<span class="${cls(r.revenue_growth)}">${pct(r.revenue_growth, 1)}</span>`, "growth") +
        line(t("des.ebitda"), r => money(r.ebitda), "ebitda") + line(t("des.ebit_margin"), r => pct(r.ebit_margin, 1, false), "ebit_margin") +
        line(t("fa.net_income"), r => money(r.net_income)) + line(t("fa.net_margin"), r => pct(r.net_margin, 1, false), "net_margin") +
        line(t("fa.eps"), r => num(r.eps_diluted), "eps") + line(t("des.fcf"), r => money(r.fcf), "fcf") +
        line(t("des.net_debt"), r => money(r.net_debt), "net_debt") + line(t("des.nd_ebitda"), r => (isNum(r.net_debt_to_ebitda) ? num(r.net_debt_to_ebitda, 1) + "x" : "—"), "nd_ebitda") +
        line(t("des.roe"), r => pct(r.roe, 1, false), "roe");
    return `<table class="t">${head}${body}</table>`;
  }
  async function renderDES() {
    const m = meta(); if (!m) return firstRunNotice();
    const stocks = m.watchlist_universe.filter(tk => UNI[tk] && UNI[tk].kind === "stock");
    const tk = stocks.includes(S.ticker) ? S.ticker : (stocks.includes("MC.PA") ? "MC.PA" : stocks[0]);
    const info = UNI[tk] || {};
    const [x, es] = await Promise.all([companyOf(tk), info.region === "EU" ? esefOf(tk) : Promise.resolve(null)]);
    const tools = tickerSelect(tk, stocks, "des-ticker");
    const src = "Yahoo Finance (yfinance)";
    if (!x.ok) {
      return panel({ title: `DES — ${esc(tk)} ${esc(info.name || "")}`, tools, meta: x.meta, source: src,
        body: dsUnavailable(x) + `<p class="note">${t("des.rotation_note")}</p>` });
    }
    const c = x.data, pf = c.profile || {}, va = c.valuation || {}, tg = c.targets || {}, cal = c.calendar || {};
    const q = quotesEnv(), qq = q && q.data[tk];
    const cr = compRow(tk) || {};
    const ccy = pf.financial_currency || pf.currency;
    const price = qq && qq.status === "ok" ? qq.last : tg.current_price;
    // header
    const head = `<div class="qhead"><span class="px">${num(price)} <span class="note">${esc(qq ? qq.currency : pf.currency || "")}</span></span>
      ${qq && qq.status === "ok" ? `<span class="ch ${cls(qq.pct)}">${pct(qq.pct)}</span>${delayed()}` : ""}
      <span class="kv">${t("des.sector")} <b>${esc(pf.sector || "—")}</b> · <b>${esc(pf.industry || "—")}</b></span>
      <span class="kv">${t("col.country")} <b>${esc(pf.country || info.country || "—")}</b></span>
      ${pf.employees ? `<span class="kv">${t("des.employees")} <b>${num(pf.employees, 0)}</b></span>` : ""}
      ${isNum(cr.market_cap_eur) ? `<span class="kv">${t("term.mcap")} <b>${bn(cr.market_cap_eur)} ${t("unit.bn")} €</b> <span class="note">(${t("size." + cr.size)})</span></span>` : ""}
      ${pf.website ? `<a class="kv" href="${esc(safeUrl(pf.website))}" target="_blank" rel="noopener">${esc(pf.website.replace(/^https?:\/\/(www\.)?/, ""))} ↗</a>` : ""}</div>`;
    // factual commentary
    const sentences = (cr.facts || []).map(f => factSentence(f, ccy)).filter(Boolean);
    const comment = sentences.length ? `<ul class="facts">${sentences.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : `<div class="note">${t("des.no_facts")}</div>`;
    const summaryPanel = panel({ title: `DES — <span class="sec">${esc(C.bbgCode(tk, info))}</span> ${esc(pf.name || info.name || "")}`, tools, meta: x.meta, source: src,
      body: head + `<div class="sub">${t("des.key_points")}</div>` + comment + `<p class="note">${t("des.facts_note")}</p>` });
    // results
    const resultsPanel = panel({ title: t("des.results_annual"), cls: "span-8", meta: x.meta, source: src + " — " + t("des.statements_src"), tools: csvBtn(),
      body: finTable(c.annual, ccy, false) + (c.statements_error ? `<div class="note down">${esc(c.statements_error)}</div>` : "") });
    const quartersPanel = panel({ title: t("des.results_quarterly"), cls: "span-4", meta: x.meta, source: src, tools: csvBtn(),
      body: finTable((c.quarterly || []).slice(-4), ccy, true) });
    // consensus
    const per = { "0q": t("des.p_0q"), "+1q": t("des.p_1q"), "0y": t("des.p_0y"), "+1y": t("des.p_1y") };
    const est = (c.estimates || []).filter(e => per[e.period] && (isNum(e.eps_avg) || isNum(e.rev_avg)));
    const estBody = est.length ? `<table class="t"><tr><th class="l">${t("des.period")}</th><th>${t("des.end")}</th>${th("eps_est", t("des.eps_avg"))}<th>${t("des.range")}</th>
        ${th("n_analysts", t("cal.n"))}${th("growth", t("des.eps_growth"))}${th("rev_est", t("des.rev_avg"))}${th("growth", t("des.rev_growth"))}</tr>
      ${est.map(e => `<tr><td class="l">${per[e.period]}</td><td>${fmtDate(e.end_date)}</td><td>${num(e.eps_avg)}</td>
        <td class="note">${isNum(e.eps_low) || isNum(e.eps_high) ? `${num(e.eps_low)} – ${num(e.eps_high)}` : "—"}</td><td>${e.eps_n || "—"}</td><td class="${cls(e.eps_growth)}">${pct(e.eps_growth, 1)}</td>
        <td>${compact(e.rev_avg)}</td><td class="${cls(e.rev_growth)}">${pct(e.rev_growth, 1)}</td></tr>`).join("")}</table>`
      : `<div class="note">${t("des.no_consensus")}</div>`;
    const consensusPanel = panel({ title: t("des.consensus"), id: "sec-consensus", cls: "span-8", meta: x.meta, source: src + " — earningsTrend", tools: csvBtn(),
      body: estBody + `<p class="note">${t("des.consensus_note")}</p>` });
    // targets & recommendations
    const rec = (c.recommendations || []).find(r => r.period === "0m");
    const recBar = rec ? (() => {
      const parts = [["strongBuy", "#3fd16b"], ["buy", "#2f9d52"], ["hold", "#8d877b"], ["sell", "#c9552f"], ["strongSell", "#ff4d4d"]];
      const tot = parts.reduce((s, [k]) => s + (rec[k] || 0), 0);
      if (!tot) return "";
      return `<div class="recbar">${parts.map(([k, col]) => rec[k] ? `<span style="flex:${rec[k]};background:${col}" title="${esc(t("reco." + k))}: ${rec[k]}">${rec[k]}</span>` : "").join("")}</div>
        <div class="note">${parts.map(([k]) => `${t("reco." + k)} ${rec[k] || 0}`).join(" · ")}</div>`;
    })() : "";
    const upside = isNum(tg.mean) && isNum(price) ? tg.mean / price - 1 : null;
    const targetsPanel = panel({ title: t("des.targets"), id: "sec-targets", cls: "span-4", meta: x.meta, source: src + " — financialData, recommendationTrend",
      body: (isNum(tg.mean) ? kv(t("des.target_mean"), `${num(tg.mean)} <span class="${cls(upside)}">(${pct(upside, 1)})</span>`, "target") +
        kv(t("des.target_range"), `${num(tg.low)} – ${num(tg.high)}`) + kv(t("cal.n"), tg.n_analysts || "—", "n_analysts") +
        kv(t("des.reco"), tg.reco_key ? t("reco.key." + tg.reco_key) : "—", "reco") : `<div class="note">${t("des.no_targets")}</div>`) + recBar });
    // surprises
    const sur = (c.surprises || []).slice(-4);
    const surBody = sur.length ? `<table class="t"><tr><th class="l">${t("des.quarter")}</th>${th("eps_est", t("des.eps_est"))}${th("eps", t("des.eps_act"))}${th("surprise", t("des.surprise"))}</tr>
      ${sur.map(s => `<tr><td class="l">${fmtDate(s.quarter)}</td><td>${num(s.eps_estimate)}</td><td>${num(s.eps_actual)}</td>
        <td class="${cls(s.surprise_pct)}">${pct(s.surprise_pct, 1)}</td></tr>`).join("")}</table>` : `<div class="note">${t("des.no_surprises")}</div>`;
    const surprisesPanel = panel({ title: t("des.surprises"), id: "sec-surprises", cls: "span-4", meta: x.meta, source: src + " — earningsHistory", body: surBody });
    // calendar & valuation
    const calPanel = panel({ title: t("des.calendar"), cls: "span-4", meta: x.meta, source: src + " — calendarEvents",
      body: kv(t("des.next_results"), (() => {
          const today = new Date().toISOString().slice(0, 10);
          const up = (cal.earnings_dates || []).filter(d => d >= today);
          const past = (cal.earnings_dates || []).filter(d => d < today);
          return up.length ? up.map(d => fmtDate(d)).join(" / ") : (past.length ? `— <span class="note">(${t("des.last_known")} ${fmtDate(past[past.length - 1])})</span>` : "—");
        })()) +
        kv(t("des.eps_expected"), cal.eps_avg != null ? `${num(cal.eps_avg)}${isNum(cal.eps_low) ? ` <span class="note">(${num(cal.eps_low)} – ${num(cal.eps_high)})</span>` : ""}` : "—", "eps_est") +
        kv(t("des.rev_expected"), compact(cal.revenue_avg), "rev_est") + kv(t("des.ex_div"), fmtDate(cal.ex_dividend)) });
    const valPanel = panel({ title: t("des.valuation"), cls: "span-4", meta: x.meta, source: t("des.val_src"),
      body: kv(t("comps.pe"), mult(cr.pe), "pe") + kv(t("comps.ev_ebitda"), mult(cr.ev_ebitda), "ev_ebitda") + kv(t("comps.ev_sales"), mult(cr.ev_sales), "ev_sales") +
        kv(t("des.pe_fwd_yahoo"), mult(va.forward_pe), "pe_fwd") + kv(t("des.pb_yahoo"), mult(va.price_to_book), "pb") +
        kv(t("des.div_yield"), pct(va.dividend_yield, 2, false), "div_yield") + kv(t("des.beta_yahoo"), num(va.beta_yahoo), "beta") +
        `<p class="note">${t("des.val_note")}</p>` });
    // official report (ESEF) + profile
    let esefBlock = "";
    if (es) {
      esefBlock = es.ok
        ? `<p>${t("des.esef_ok", { entity: esc(es.data.entity || ""), date: fmtDate(es.data.period_end) })} ${es.data.viewer_url ? `<a href="${esc(safeUrl(es.data.viewer_url))}" target="_blank" rel="noopener">${t("des.esef_open")} ↗</a>` : ""} · <a href="#FA/${encodeURIComponent(tk)}" data-tab-fa="${esc(tk)}">${t("des.esef_fa")}</a></p>`
        : `<p class="note">${t("des.esef_ko")}: ${esc(es.error)}</p>`;
    }
    const profilePanel = panel({ title: t("des.profile"), cls: "span-12", meta: x.meta, source: src + " — assetProfile",
      body: esefBlock + (pf.summary ? ((S.lang === "fr" && S.translate && pf.summary_fr && C.numbersSubset(pf.summary, pf.summary_fr))
        ? `<p class="summary" lang="fr" title="${esc(pf.summary)}">${esc(pf.summary_fr)}${pf.summary_fr_excerpt ? " […]" : ""}</p><p class="note">${t(pf.summary_fr_excerpt ? "des.summary_note_fr_excerpt" : "des.summary_note_fr")}</p>`
        : `<p class="summary" lang="en">${esc(pf.summary)}</p><p class="note">${t("des.summary_note")}</p>`) : "") });
    return summaryPanel + resultsPanel + quartersPanel + consensusPanel + targetsPanel + surprisesPanel + calPanel + valPanel + profilePanel;
  }

  // ------------------------------------------------------------------ ESEF in FA
  async function esefPanel(tk) {
    const x = await esefOf(tk);
    const src = "ESEF (filings.xbrl.org)";
    if (!x.ok) return panel({ title: t("esef.title"), cls: "span-12", body: dsUnavailable(x) + `<p class="note">${t("esef.note_missing")}</p>`, meta: x.meta, source: src });
    const e = x.data, rows = e.rows || [];
    const money = v => (isNum(v) ? compact(v) : "—");
    const line = (label, fn, defKey) => `<tr><td class="l${I18N["def." + defKey] ? " def" : ""}"${I18N["def." + defKey] ? ` title="${esc(t("def." + defKey))}"` : ""}>${label}</td>${rows.map(r => `<td>${fn(r)}</td>`).join("")}</tr>`;
    const table = `<table class="t"><tr><th class="l">${t("fa.year_end")} (${esc(e.currency || "")})</th>${rows.map(r => `<th>${fmtDate(r.end)}</th>`).join("")}</tr>
      ${line(t("fa.revenue"), r => money(r.revenue))}${line(t("des.growth"), r => `<span class="${cls(r.revenue_growth)}">${pct(r.revenue_growth, 1)}</span>`, "growth")}
      ${line(t("esef.ebit"), r => money(r.ebit), "ebit_margin")}${line(t("des.ebit_margin"), r => pct(r.ebit_margin, 1, false), "ebit_margin")}
      ${line(t("fa.net_income"), r => money(r.net_income))}${line(t("fa.net_margin"), r => pct(r.net_margin, 1, false), "net_margin")}
      ${line(t("fa.eps"), r => num(r.eps_diluted), "eps")}${line(t("esef.ocf"), r => money(r.op_cash_flow))}${line(t("esef.capex"), r => money(r.capex))}
      ${line(t("des.fcf"), r => money(r.fcf), "fcf")}${line(t("esef.cash"), r => money(r.cash))}${line(t("esef.equity"), r => money(r.equity))}
      ${line(t("esef.dividends"), r => money(r.dividends_paid))}</table>`;
    return panel({ title: `${t("esef.title")} — ${esc(e.entity || tk)}`, cls: "span-12", meta: x.meta, source: src, tools: csvBtn(),
      body: table + `<p class="note">${t("esef.note", { lei: esc(e.lei), n: e.n_reports })} ${e.viewer_url ? `<a href="${esc(safeUrl(e.viewer_url))}" target="_blank" rel="noopener">${t("des.esef_open")} ↗</a>` : ""}</p>` });
  }

  // ------------------------------------------------------------------ COMPS
  function renderCOMPS() {
    const m = meta(); if (!m) return firstRunNotice();
    const c = companies();
    if (!c.ok) return panel({ title: "COMPS", body: dsUnavailable(c), meta: c.meta, source: "Yahoo Finance" });
    const rows = c.data.rows;
    const sectors = [...new Set(Object.values(rows).filter(r => r.status === "ok" && r.sector).map(r => r.sector))].sort();
    const mine = rows[S.ticker] && rows[S.ticker].sector;
    if (!S.comps.sector || !sectors.includes(S.comps.sector)) S.comps.sector = mine || sectors[0];
    const sel = (name, options, cur) => `<select data-comps="${name}">${options.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
    const tools = sel("sector", sectors.map(s => [s, s]), S.comps.sector) +
      sel("region", [["ALL", t("eqs.all_regions")], ["US", t("region.US")], ["EU", t("region.EU")]], S.comps.region) + csvBtn();
    const list = Object.entries(rows).filter(([tk, r]) => r.status === "ok" && r.sector === S.comps.sector && (S.comps.region === "ALL" || (UNI[tk] || {}).region === S.comps.region))
      .sort((a, b) => (b[1].market_cap_eur || 0) - (a[1].market_cap_eur || 0));
    const cols = [["market_cap_eur", "col.mcap", "mcap", bn], ["ev_eur", "comps.ev", "ev", bn], ["pe", "comps.pe", "pe", mult], ["ev_ebitda", "comps.ev_ebitda", "ev_ebitda", mult],
      ["ev_sales", "comps.ev_sales", "ev_sales", mult], ["ebit_margin", "comps.ebit_m", "ebit_margin", v => pct(v, 1, false)], ["net_margin", "comps.net_m", "net_margin", v => pct(v, 1, false)],
      ["revenue_growth", "comps.growth", "growth", v => pct(v, 1)], ["roe", "des.roe", "roe", v => pct(v, 1, false)], ["net_debt_to_ebitda", "comps.nd", "nd_ebitda", v => (isNum(v) ? num(v, 1) + "x" : "—")],
      ["dividend_yield", "comps.dy", "div_yield", v => pct(v, 1, false)]];
    const med = k => C.median(list.map(([, r]) => r[k]).filter(isNum));
    const head = `<tr><th class="l">${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th><th class="l">${t("col.country")}</th>${th("size", t("col.segment"), "l")}${th("fy", t("comps.fy"))}
      ${cols.map(([, lbl, d]) => th(d, t(lbl))).join("")}</tr>`;
    const body = list.map(([tk, r]) => `<tr class="click ${tk === S.ticker ? "hl" : ""}" data-goto-des="${esc(tk)}"><td class="tk l">${esc(tk)}</td><td class="nm">${esc((UNI[tk] || {}).name)}</td>
      <td class="l">${esc((UNI[tk] || {}).country || "")}</td><td class="l note">${r.size ? t("size." + r.size) : "—"}</td><td class="note">${fmtDate(r.fy)}</td>
      ${cols.map(([k, , , f]) => `<td class="${k === "revenue_growth" ? cls(r[k]) : ""}">${f(r[k])}</td>`).join("")}</tr>`).join("");
    const medRow = `<tr class="med"><td class="l" colspan="5">${t("comps.median", { n: list.length })}</td>${cols.map(([k, , , f]) => `<td>${f(med(k))}</td>`).join("")}</tr>`;
    return panel({ title: `COMPS — ${esc(S.comps.sector || "")}`, tools, meta: c.meta, source: c.meta.source,
      body: list.length ? `<table class="t">${head}${body}${medRow}</table><p class="note">${t("comps.note")}</p>` : `<div class="note">${t("comps.empty")}</div>` });
  }

  // ------------------------------------------------------------------ DEALS
  function renderDEALS() {
    const m = meta(); if (!m) return firstRunNotice();
    const x = ds("deals.json");
    if (!x.ok) return panel({ title: "DEALS", body: dsUnavailable(x), meta: x.meta, source: "SEC EDGAR" });
    const f = S.deals.ticker;
    const tools = `<select data-deals="ticker"><option value="ALL">${t("deals.all")}</option>${m.watchlist_universe.map(tk => `<option value="${esc(tk)}" ${f === tk ? "selected" : ""}>${esc(tk)}</option>`).join("")}</select>`;
    const sec = x.data.sec.filter(d => f === "ALL" || d.ticker === f).slice(0, 80);
    const secBody = sec.length ? `<table class="t"><tr><th class="l">${t("fa.filed")}</th><th class="l">${t("col.ticker")}</th><th class="l">${t("fa.form")}</th><th class="l">${t("deals.type")}</th><th></th></tr>
      ${sec.map(d => `<tr><td class="l">${fmtDate(d.filed)}</td><td class="tk l">${esc(d.ticker)}</td><td class="l">${esc(d.form)}</td>
        <td class="l">${d.kinds.map(k => esc(t("deal." + k))).join(", ")}</td><td class="l"><a href="${esc(safeUrl(d.url))}" target="_blank" rel="noopener">${t("open")} ↗</a></td></tr>`).join("")}</table>`
      : `<div class="note">${t("deals.none_sec")}</div>`;
    const news = x.data.news.filter(d => f === "ALL" || d.ticker === f).slice(0, 80);
    const newsBody = news.length ? news.map(h => {
      const useFr = S.lang === "fr" && S.translate && h.title_fr && C.numbersSubset(h.title, h.title_fr);
      return `<div class="news-item"><span class="when">${fmtDT(h.published)}<span class="src">${esc(h.publisher || "—")}<span class="feed">${esc(h.feed || "")}</span></span></span>
        <span><b class="tk">${esc(h.ticker)}</b> <a href="${esc(safeUrl(h.link))}" target="_blank" rel="noopener" title="${esc(h.title)}">${esc(useFr ? h.title_fr : h.title)}</a>${useFr ? ` <span class="mt">${t("news.mt")}</span>` : ""}</span>
        <span class="sent" title="${esc(t("deals.kw_tip"))}">${esc(h.keyword)}</span></div>`;
    }).join("") : `<div class="note">${t("deals.none_news")}</div>`;
    return panel({ title: t("deals.sec_title"), cls: "span-6", tools, meta: x.meta, source: "SEC EDGAR (submissions)",
        body: secBody + `<p class="note">${t("deals.sec_note")}</p>` }) +
      panel({ title: t("deals.news_title"), cls: "span-6", meta: x.meta, source: t("deals.news_src"),
        body: newsBody + `<p class="note">${t("deals.news_note")}</p>` });
  }

  // ------------------------------------------------------------------ glossary (HELP)
  function glossaryPanel() {
    const keys = Object.keys(I18N).filter(k => k.startsWith("def.")).sort((a, b) => t("term." + a.slice(4)).localeCompare(t("term." + b.slice(4))));
    return panel({ title: t("help.glossary"), updated: null, source: "Atlas Terminal",
      body: `<table class="t gloss">${keys.map(k => `<tr><td class="l tk">${esc(t("term." + k.slice(4)))}</td><td class="l">${esc(t(k))}</td></tr>`).join("")}</table>` });
  }

  // ================================================================== terminal chrome: tape, status bar, menus, flash
  const arrowOf = v => (!isNum(v) || v === 0 ? "" : v > 0 ? "▲ " : "▼ ");
  function renderTape() {
    const el = $("#tape"); if (!el) return;
    const q = quotesEnv(), m = meta();
    if (!q || !m) { el.innerHTML = ""; return; }
    const list = ["^STOXX50E", "^FCHI", "^GDAXI", "^FTSE", "^GSPC", "^IXIC", "^N225", "^VIX", "EURUSD=X", "EURGBP=X", "BZ=F", "GC=F"];
    const item = tk => {
      const x = q.data[tk]; if (!x || x.status !== "ok") return "";
      const code = C.bbgCode(tk, UNI[tk]).replace(/ (Index|Curncy|Comdty)$/, "");
      return `<span class="ti" data-goto="${esc(tk)}"><b>${esc(code)}</b> ${num(x.last, x.last < 10 ? 4 : 2)} <span class="${cls(x.pct)}">${arrowOf(x.pct)}${pct(x.pct)}</span></span>`;
    };
    const html = list.map(item).join("");
    el.innerHTML = html ? `<div class="tape-track">${html}${html}</div>` : "";   // doubled for a seamless loop
  }
  function renderStatusBar() {
    const el = $("#statusbar"); if (!el) return;
    const st = D["status.json"] && D["status.json"].ok ? D["status.json"].env : null;
    const m = meta();
    const health = !st ? `<span class="note">STATUS —</span>`
      : st.problems.length ? `<a class="sb-alert" data-tab="STATUS">⚠ ${t("sb.alerts", { n: st.problems.length })}</a>`
      : `<a class="sb-ok" data-tab="STATUS">● ${t("sb.ok")}</a>`;
    el.innerHTML = `<span class="sb-delay">DELAYED</span><span>${t("sb.last_run")}: ${fmtDT(m && m.generated_at)}</span>${health}
      <span class="sb-msg" id="sbMsg"></span><span class="sb-right">${esc(t("foot.short"))}</span>`;
  }
  // numbered menu of the current screen: "1) Summary 2) Results ..." -> type the number + GO
  let MENU = [];
  function setMenu(items) { MENU = items || []; }
  function renderMenu() {
    const el = $("#menu"); if (!el) return;
    el.innerHTML = MENU.length ? MENU.map((it, i) => `<button class="mi" data-menu="${i + 1}"><b>${i + 1})</b> ${esc(it.label)}</button>`).join("") : "";
    el.hidden = !MENU.length;
  }
  function runMenu(n) {
    const it = MENU[n - 1];
    if (!it) { $("#cmdMsg").textContent = t("cmd.bad_menu", { n }); return; }
    if (it.go) return it.go();
    const target = document.getElementById(it.target);
    if (target) { target.scrollIntoView({ behavior: "smooth", block: "start" }); target.classList.add("hit"); setTimeout(() => target.classList.remove("hit"), 1200); }
  }
  // brief green / red flash on prices that changed since the previous refresh
  let PREV_PX = {};
  function flashChanges() {
    const q = quotesEnv(); if (!q) return;
    document.querySelectorAll("[data-px]").forEach(el => {
      const tk = el.dataset.px, x = q.data[tk];
      if (!x || x.status !== "ok") return;
      const before = PREV_PX[tk];
      if (before != null && x.last !== before) {
        el.classList.add(x.last > before ? "flash-up" : "flash-down");
        setTimeout(() => el.classList.remove("flash-up", "flash-down"), 1500);
      }
    });
    PREV_PX = Object.fromEntries(Object.entries(q.data).filter(([, x]) => x.status === "ok").map(([k, x]) => [k, x.last]));
  }

  // ================================================================== WEI — world equity indices
  const perfOf = tk => { const p = ds("perf.json"); return p.ok ? p.data[tk] : null; };
  function weiRows(tickers, compact) {
    const q = quotesEnv();
    return tickers.map(tk => {
      const x = q && q.data[tk], p = perfOf(tk) || {}, u = UNI[tk] || {};
      const ok = x && x.status === "ok";
      const code = C.bbgCode(tk, u).replace(/ Index$/, "");
      const base = `<td class="tk l" title="${esc(tk)}">${esc(code)}</td><td class="nm">${esc(u.name || tk)}</td>`;
      if (!ok) return `<tr class="click" data-goto="${esc(tk)}">${base}<td class="na" colspan="${compact ? 2 : 8}" title="${esc(x ? x.error : "")}">${t("unavailable")}</td></tr>`;
      const cells = `<td data-px="${esc(tk)}">${num(x.last)}</td><td class="${cls(x.pct)}">${arrowOf(x.pct)}${pct(x.pct)}</td>`;
      if (compact) return `<tr class="click" data-goto="${esc(tk)}">${base}${cells}</tr>`;
      return `<tr class="click" data-goto="${esc(tk)}">${base}${cells}<td class="${cls(x.change)}">${signed(x.change)}</td>
        <td class="${cls(p.w1)}">${pct(p.w1, 1)}</td><td class="${cls(p.m1)}">${pct(p.m1, 1)}</td><td class="${cls(p.ytd)}">${pct(p.ytd, 1)}</td>
        <td class="${cls(p.y1)}">${pct(p.y1, 1)}</td><td class="note">${fmtDate(x.date)}</td></tr>`;
    }).join("");
  }
  function weiTable(compact) {
    const m = meta(); if (!m) return "";
    const zones = [["AMER", t("zone.AMER")], ["EMEA", t("zone.EMEA")], ["APAC", t("zone.APAC")]];
    const idx = m.universe.filter(u => u.kind === "index");
    const head = compact ? `<tr><th class="l">${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th><th>${t("col.last")}</th><th>${t("col.pct")}</th></tr>`
      : `<tr><th class="l">${t("col.ticker")}</th><th class="l nm">${t("col.name")}</th><th>${t("col.last")}</th><th>${t("col.pct")}</th><th>${t("col.chg")}</th>
        ${th("perf1w", t("perf.w1"))}${th("perf1m", t("perf.m1"))}${th("ytd", t("perf.ytd"))}${th("perf1y", t("perf.y1"))}<th>${t("col.date")}</th></tr>`;
    return `<table class="t">${head}${zones.map(([z, label]) => {
      const tks = idx.filter(u => u.zone === z).map(u => u.ticker);
      return tks.length ? `<tr class="grp"><td colspan="${compact ? 4 : 10}">${label}</td></tr>${weiRows(tks, compact)}` : "";
    }).join("")}</table>`;
  }
  function renderWEI() {
    const m = meta(); if (!m) return firstRunNotice();
    const p = ds("perf.json");
    return panel({ title: `WEI — ${t("wei.title")} ${delayed()}`, tools: csvBtn(), source: "Yahoo Finance (yfinance)",
      updated: quotesUpdated(),
      body: weiTable(false) + `<p class="note">${t("wei.note")}${p.ok ? " " + t("wei.perf_asof", { d: fmtDT(p.meta.fetched_at) }) : ""}</p>` });
  }

  // ================================================================== MOST — biggest movers & most active
  const quotesUpdated = () => { const q = quotesEnv(); return q ? Object.values(q._meta.regions || {}).map(r => r.fetched_at).filter(Boolean).sort().pop() : null; };
  function fxRates() { const c = companies(); return c.ok ? c.data.fx || {} : {}; }
  function toEurJs(v, ccy) {
    const r = fxRates();
    if (!isNum(v) || !ccy) return null;
    if (ccy === "GBp") { v /= 100; ccy = "GBP"; }
    return r[ccy] ? v / r[ccy] : null;
  }
  function mostLists(region, n) {
    const m = meta(), q = quotesEnv();
    if (!m || !q) return null;
    const rows = m.watchlist_universe.filter(tk => (UNI[tk] || {}).kind === "stock" && (region === "ALL" || UNI[tk].region === region))
      .map(tk => [tk, q.data[tk]]).filter(([, x]) => x && x.status === "ok" && isNum(x.pct));
    const up = [...rows].sort((a, b) => b[1].pct - a[1].pct).slice(0, n);
    const down = [...rows].sort((a, b) => a[1].pct - b[1].pct).slice(0, n);
    const active = rows.map(([tk, x]) => [tk, x, toEurJs(x.last * (x.volume || 0), x.currency)]).filter(r => isNum(r[2]))
      .sort((a, b) => b[2] - a[2]).slice(0, n);
    return { up, down, active, n: rows.length };
  }
  function mostTable(list, withTurnover) {
    return `<table class="t">${list.map(([tk, x, eur]) => `<tr class="click" data-goto="${esc(tk)}"><td class="tk l">${esc(tk)}</td><td class="nm">${esc((UNI[tk] || {}).name)}</td>
      <td data-px="${esc(tk)}">${num(x.last)} <span class="note">${esc(x.currency || "")}</span></td><td class="${cls(x.pct)}">${arrowOf(x.pct)}${pct(x.pct)}</td>
      ${withTurnover ? `<td>${compact(eur)} €</td>` : ""}</tr>`).join("")}</table>`;
  }
  function renderMOST() {
    const L = mostLists(S.most.region, 15);
    if (!L) return firstRunNotice();
    const tools = `<select data-most="region">${[["ALL", t("eqs.all_regions")], ["US", t("region.US")], ["EU", t("region.EU")]].map(([v, l]) => `<option value="${v}" ${S.most.region === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
    const src = "Yahoo Finance (yfinance)", updated = quotesUpdated();
    return panel({ title: `MOST — ${t("most.up")} ${delayed()}`, cls: "span-4", tools, source: src, updated, body: mostTable(L.up) }) +
      panel({ title: `MOST — ${t("most.down")}`, cls: "span-4", source: src, updated, body: mostTable(L.down) }) +
      panel({ title: `MOST — ${t("most.active")}`, cls: "span-4", source: src + " · " + t("most.turnover_src"), updated, body: mostTable(L.active, true) + `<p class="note">${t("most.note", { n: L.n })}</p>` });
  }

  // ================================================================== FXC — cross currency rates
  const FX_CCY = ["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK"];
  const FX_TK = { USD: "EURUSD=X", GBP: "EURGBP=X", CHF: "EURCHF=X", SEK: "EURSEK=X", NOK: "EURNOK=X", DKK: "EURDKK=X" };
  function fxMatrix(field) {
    const q = quotesEnv(); if (!q) return null;
    const r = { EUR: 1 };
    for (const [c, tk] of Object.entries(FX_TK)) { const x = q.data[tk]; if (x && x.status === "ok" && isNum(x[field])) r[c] = x[field]; }
    return r;
  }
  function fxcTable(compact) {
    const now = fxMatrix("last"), prev = fxMatrix("prev_close");
    if (!now) return unavailable(t("err.no_quote"), null);
    const cur = FX_CCY.filter(c => now[c]);
    return `<table class="t fxc"><tr><th class="l">1 ↓ = </th>${cur.map(c => `<th>${c}</th>`).join("")}</tr>
      ${cur.map(a => `<tr><td class="tk l">${a}</td>${cur.map(b => {
        if (a === b) return `<td class="note">—</td>`;
        const v = now[b] / now[a], p = prev && prev[a] && prev[b] ? prev[b] / prev[a] : null;
        const ch = isNum(p) ? v / p - 1 : null;
        return `<td class="${compact ? cls(ch) : ""}" title="${a}/${b} ${isNum(ch) ? pct(ch) : ""}">${num(v, v >= 100 ? 2 : 4)}${!compact && isNum(ch) ? `<br><span class="${cls(ch)} small">${arrowOf(ch)}${pct(ch)}</span>` : ""}</td>`;
      }).join("")}</tr>`).join("")}</table>`;
  }
  function renderFXC() {
    return panel({ title: `FXC — ${t("fxc.title")} ${delayed()}`, tools: csvBtn(), source: "Yahoo Finance (EURxxx=X)",
      updated: quotesEnv() ? (quotesEnv()._meta.regions.EU || {}).fetched_at : null,
      body: fxcTable(false) + `<p class="note">${t("fxc.note")}</p>` });
  }

  // ================================================================== HP — historical prices
  async function renderHP() {
    const m = meta(); if (!m) return firstRunNotice();
    const tk = S.ticker, h = await historyOf(tk);
    const tools = tickerSelect(tk, m.universe.map(u => u.ticker), "hp-ticker") +
      ["D", "W", "M"].map(p => `<button class="btn ${S.hp === p ? "on" : ""}" data-hp="${p}">${t("hp." + p)}</button>`).join("") + csvBtn();
    if (!h.ok) return panel({ title: `HP — <span class="sec">${esc(C.bbgCode(tk, UNI[tk]))}</span>`, tools, body: dsUnavailable(h), meta: h.meta, source: "Yahoo Finance" });
    const d = h.data, rows = [];
    const key = i => (S.hp === "D" ? d.dates[i] : S.hp === "W" ? isoWeek(d.dates[i]) : d.dates[i].slice(0, 7));
    for (let i = 0; i < d.dates.length; i++) {
      const k = key(i), last = rows[rows.length - 1];
      if (!last || last.k !== k) rows.push({ k, date: d.dates[i], close: d.close[i], high: d.high[i], low: d.low[i], vol: d.volume[i] || 0 });
      else { last.date = d.dates[i]; last.close = d.close[i]; last.high = Math.max(last.high, d.high[i]); last.low = Math.min(last.low, d.low[i]); last.vol += d.volume[i] || 0; }
    }
    const view = rows.slice(-61);
    const body = `<table class="t"><tr><th class="l">${t("col.date")}</th><th>${t("quote.close")}</th><th>${t("col.chg")}</th><th>${t("col.pct")}</th><th>${t("hp.high")}</th><th>${t("hp.low")}</th><th>${t("quote.volume")}</th></tr>
      ${view.slice(1).reverse().map((r, i, arr) => {
        const prev = view[view.length - 2 - i];
        const ch = r.close - prev.close, p = r.close / prev.close - 1;
        return `<tr><td class="l">${fmtDate(r.date)}</td><td>${num(r.close)}</td><td class="${cls(ch)}">${signed(ch)}</td><td class="${cls(p)}">${arrowOf(p)}${pct(p)}</td>
          <td>${num(r.high)}</td><td>${num(r.low)}</td><td>${compact(r.vol)}</td></tr>`;
      }).join("")}</table>`;
    return panel({ title: `HP — <span class="sec">${esc(C.bbgCode(tk, UNI[tk]))}</span> ${esc((UNI[tk] || {}).name || "")}`, tools, body: body + `<p class="note">${t("hp.note")}</p>`,
      meta: h.meta, source: "Yahoo Finance (yfinance)" });
  }
  function isoWeek(ymd) {
    const d = new Date(ymd + "T12:00:00Z"), day = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - day + 3);
    const y = d.getUTCFullYear(), first = new Date(Date.UTC(y, 0, 4));
    return y + "-W" + String(1 + Math.round(((d - first) / 864e5 - 3 + ((first.getUTCDay() + 6) % 7)) / 7)).padStart(2, "0");
  }

  // ================================================================== DVD — dividends
  async function renderDVD() {
    const m = meta(); if (!m) return firstRunNotice();
    const stocks = m.watchlist_universe.filter(tk => (UNI[tk] || {}).kind === "stock");
    const tk = stocks.includes(S.ticker) ? S.ticker : "MC.PA";
    const x = await companyOf(tk);
    const tools = tickerSelect(tk, stocks, "dvd-ticker") + csvBtn();
    const title = `DVD — <span class="sec">${esc(C.bbgCode(tk, UNI[tk]))}</span> ${esc((UNI[tk] || {}).name || "")}`;
    if (!x.ok) return panel({ title, tools, body: dsUnavailable(x) + `<p class="note">${t("des.rotation_note")}</p>`, meta: x.meta, source: "Yahoo Finance" });
    const c = x.data, dv = c.dividends || [], ccy = (c.profile || {}).currency === "GBp" ? "GBP" : (c.profile || {}).currency;
    // page collected before dividends were added: say so, never "no dividend"
    if (!("dividends" in c)) return panel({ title, tools, meta: x.meta, source: "Yahoo Finance", body: `<div class="note">${t("dvd.pending")}</div>` });
    if (!dv.length) return panel({ title, tools, meta: x.meta, source: "Yahoo Finance", body: `<div class="note">${t(c.dividends_error ? "dvd.error" : "dvd.none")} ${esc(c.dividends_error || "")}</div>` });
    const byYear = {};
    dv.forEach(([d, a]) => { byYear[d.slice(0, 4)] = (byYear[d.slice(0, 4)] || 0) + a; });
    const years = Object.keys(byYear).sort();
    const thisYear = new Date().getUTCFullYear().toString();
    const yearRows = years.map((y, i) => `<tr><td class="l">${y}${y === thisYear ? ` <span class="note">(${t("dvd.ytd")})</span>` : ""}</td><td>${num(byYear[y], 4)}</td>
      <td class="${i ? cls(byYear[y] / byYear[years[i - 1]] - 1) : ""}">${i && y !== thisYear ? pct(byYear[y] / byYear[years[i - 1]] - 1, 1) : "—"}</td></tr>`).reverse().join("");
    const pays = dv.slice().reverse().slice(0, 30).map(([d, a]) => `<tr><td class="l">${fmtDate(d)}</td><td>${num(a, 4)} <span class="note">${esc(ccy || "")}</span></td></tr>`).join("");
    const va = c.valuation || {}, cal = c.calendar || {};
    return panel({ title, tools, cls: "span-8", meta: x.meta, source: "Yahoo Finance (dividends)",
        body: `<table class="t"><tr><th class="l">${t("dvd.ex_date")}</th><th>${t("dvd.amount")}</th></tr>${pays}</table><p class="note">${t("dvd.note")}</p>` }) +
      panel({ title: t("dvd.by_year"), cls: "span-4", meta: x.meta, source: "Yahoo Finance",
        body: kv(t("des.div_yield"), pct(va.dividend_yield, 2, false), "div_yield") + kv(t("dvd.payout"), pct(va.payout_ratio, 0, false)) +
          kv(t("des.ex_div"), fmtDate(cal.ex_dividend)) + `<table class="t"><tr><th class="l">${t("dvd.year")}</th><th>${t("dvd.total")} (${esc(ccy || "")})</th><th>${t("dvd.growth")}</th></tr>${yearRows}</table>` });
  }

  // ================================================================== GIP — intraday chart
  function intradayOf(tk) { const x = ds("intraday.json"); return x.ok ? x.data[tk] : null; }
  function drawIntraday(el, d, height) {
    const xs = d.t.map(s => Date.parse(s) / 1000);
    const dec = d.p[d.p.length - 1] < 10 ? 4 : 2;
    makeChart(el, [line(t("gip.price"), PAL.price, v => num(v, dec))], [xs, d.p], {
      height: height || 320, yfmt: v => num(v, dec), xtime: true });
  }
  function renderGIP() {
    const m = meta(); if (!m) return firstRunNotice();
    const tk = S.ticker, d = intradayOf(tk), x = ds("intraday.json");
    const avail = m.universe.filter(u => x.ok && x.data[u.ticker]).map(u => u.ticker);
    const tools = tickerSelect(avail.includes(tk) ? tk : (avail[0] || tk), avail.length ? avail : [tk], "gip-ticker");
    const title = `GIP — <span class="sec">${esc(C.bbgCode(tk, UNI[tk]))}</span> ${esc((UNI[tk] || {}).name || "")} ${delayed()}`;
    if (!x.ok) return { html: panel({ title, tools, body: dsUnavailable(x), meta: x.meta, source: "Yahoo Finance" }) };
    if (!d) return { html: panel({ title, tools, meta: x.meta, source: "Yahoo Finance", body: `<div class="note">${t("gip.not_covered")}</div>` }) };
    const first = d.p[0], last = d.p[d.p.length - 1];
    const html = panel({ title, tools, meta: x.meta, source: "Yahoo Finance (5 min)",
      body: `<div class="qhead"><span class="px">${num(last)}</span><span class="ch ${cls(last - first)}">${arrowOf(last - first)}${pct(last / first - 1)} ${t("gip.since_open")}</span>
        <span class="kv">${t("gip.session")} <b>${fmtDate(d.date)}</b></span><span class="kv">${t("hp.high")} <b>${num(Math.max(...d.p))}</b></span><span class="kv">${t("hp.low")} <b>${num(Math.min(...d.p))}</b></span></div>
        <div class="chart" id="gipChart"></div><p class="note">${t("gip.note")}</p>` });
    return { html, after: () => drawIntraday($("#gipChart"), d) };
  }

  // ================================================================== STATUS — health of every source
  function renderSTATUS() {
    const x = D["status.json"];
    if (!x || !x.ok) return panel({ title: "STATUS", body: unavailable(x ? x.error : t("loading"), null), updated: null, source: "Atlas" });
    const st = x.env;
    const rows = st.datasets.map(r => `<tr><td class="l">${esc(r.label)}</td><td class="l note wrap">${esc(r.source || "")}</td>
      <td>${fmtDT(r.last_success)}</td><td>${isNum(r.age_h) ? num(r.age_h, 1) + " h" : "—"}</td><td>${r.max_age_h} h</td>
      <td class="l ${r.ok ? "up" : (r.critical ? "down" : "warn")}">${r.ok ? "● OK" : (r.status === "error" ? "● " + t("status.error") : "● " + t("status.late"))}</td>
      <td class="l note" style="white-space:normal">${r.ok ? "" : esc(r.error || "")}</td></tr>`).join("");
    const fail = st.failing.length ? `<table class="t"><tr><th class="l">${t("status.item")}</th><th>${t("status.since")}</th><th>${t("status.days")}</th><th class="l">${t("status.err")}</th></tr>
      ${st.failing.map(f => `<tr><td class="tk l">${esc(f.key)}</td><td>${fmtDT(f.since)}</td><td class="${f.days >= 3 ? "down" : ""}">${num(f.days, 1)}</td><td class="l note" style="white-space:normal">${esc(f.error || "")}</td></tr>`).join("")}</table>`
      : `<div class="note">${t("status.no_fail")}</div>`;
    const probs = st.problems.length ? `<ul class="facts down">${st.problems.map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : `<p class="up">● ${t("sb.ok")}</p>`;
    const cnt = st.counts || {};
    return panel({ title: `STATUS — ${t("status.title")}`, updated: st.generated_at, source: "Atlas Terminal (pipeline/health.py)",
        body: probs + `<table class="t"><tr><th class="l">${t("status.dataset")}</th><th class="l">${t("panel.source")}</th><th>${t("last_success")}</th><th>${t("status.age")}</th><th>${t("status.limit")}</th><th class="l">${t("status.state")}</th><th class="l"></th></tr>${rows}</table>
          <p class="note">${t("status.alert_note")}</p>` }) +
      panel({ title: t("status.failing"), cls: "span-8", updated: st.generated_at, source: "state.json", body: fail + `<p class="note">${t("status.fail_note")}</p>` }) +
      panel({ title: t("status.coverage"), cls: "span-4", updated: st.generated_at, source: "Atlas",
        body: kv(t("status.universe"), st.universe) + kv(t("status.company_pages"), cnt.company ? `${cnt.company.ok} / ${cnt.company.total}` : "—") +
          kv(t("status.esef"), cnt.esef ? `${cnt.esef.ok} / ${cnt.esef.total}` : "—") + kv(t("sb.last_run"), fmtDT(st.last_run)) +
          `<p class="note">${t("status.coverage_note")}</p>` });
  }

  // ================================================================== LP — launchpad (4 windows)
  const LP_DEFAULT = ["MON", "MC FP GP", "MC FP DES", "WEI"];
  function lpLayout() { const l = LS.get("lp", null); return Array.isArray(l) && l.length === 4 ? l : LP_DEFAULT.slice(); }
  async function lpPane(cmd, i) {
    const m = meta();
    const c = String(cmd || "").trim().toUpperCase();
    if (c === "MON" || c === "MKTS") {
      const wl = watchlist();
      return { title: t("lp.mon"), html: `<table class="t">${wl.map(tk => { const x = (quotesEnv() || { data: {} }).data[tk]; const ok = x && x.status === "ok";
        return `<tr class="click" data-goto="${esc(tk)}"><td class="tk l">${esc(tk)}</td><td data-px="${esc(tk)}">${ok ? num(x.last) : "—"}</td><td class="${ok ? cls(x.pct) : ""}">${ok ? arrowOf(x.pct) + pct(x.pct) : t("unavailable")}</td></tr>`; }).join("")}</table>` };
    }
    if (c === "WEI") return { title: "WEI", html: weiTable(true) };
    if (c === "FXC") return { title: "FXC", html: fxcTable(true) };
    if (c === "MOST") { const L = mostLists("ALL", 6); return { title: "MOST", html: L ? `<div class="sub">${t("most.up")}</div>${mostTable(L.up)}<div class="sub">${t("most.down")}</div>${mostTable(L.down)}` : "—" }; }
    const r = C.parseCommand(cmd, m ? m.universe : []);
    if (r.type !== "ticker") return { title: esc(cmd), html: `<div class="note">${t("lp.unknown")}</div>` };
    const tk = r.ticker, code = `<span class="sec">${esc(C.bbgCode(tk, UNI[tk]))}</span>`;
    if (r.tab === "QUOTE" || r.tab === "GIP") {
      if (r.tab === "GIP") { const d = intradayOf(tk); return { title: `${code} GIP`, html: d ? `<div class="chart" id="lpc${i}"></div>` : `<div class="note">${t("gip.not_covered")}</div>`, after: () => d && drawIntraday($("#lpc" + i), d, 260) }; }
      const h = await historyOf(tk);
      if (!h.ok) return { title: `${code} GP`, html: dsUnavailable(h) };
      const d = h.data, n = Math.min(d.dates.length, 130), i0 = d.dates.length - n;
      const q = (quotesEnv() || { data: {} }).data[tk];
      return { title: `${code} GP <span class="note">6M</span>`, html: `${q && q.status === "ok" ? `<div class="qhead"><span class="px small" data-px="${esc(tk)}">${num(q.last)}</span><span class="${cls(q.pct)}">${arrowOf(q.pct)}${pct(q.pct)}</span></div>` : ""}<div class="chart" id="lpc${i}"></div>`,
        after: () => makeChart($("#lpc" + i), [line(t("quote.close"), PAL.price, v => num(v)), line(t("quote.ma50"), PAL.blue, v => num(v), { width: 1.5 })],
          [d.dates.slice(i0).map(toTs), d.close.slice(i0), C.sma(d.close, 50).slice(i0)], { height: 240, yfmt: v => num(v, 0), hideLegend: true }) };
    }
    if (r.tab === "DES") {
      const cr = compRow(tk) || {};
      const facts = (cr.facts || []).map(f => factSentence(f)).filter(Boolean).slice(0, 7);
      return { title: `${code} DES`, html: `<div class="note">${esc((UNI[tk] || {}).name || "")} · ${esc(cr.sector || "")}</div>
        ${kv(t("term.mcap"), isNum(cr.market_cap_eur) ? bn(cr.market_cap_eur) + " " + t("unit.bn") + " €" : "—", "mcap")}${kv(t("comps.pe"), mult(cr.pe), "pe")}${kv(t("comps.ev_ebitda"), mult(cr.ev_ebitda), "ev_ebitda")}
        ${facts.length ? `<ul class="facts">${facts.map(s => `<li>${esc(s)}</li>`).join("")}</ul>` : `<div class="note">${t("des.no_facts")}</div>`}
        <button class="btn" data-goto-des="${esc(tk)}">${t("lp.open_full")}</button>` };
    }
    if (r.tab === "NEWS") {
      const n = ds("news.json"), v = n.ok ? n.data[tk] : null;
      return { title: `${code} CN`, html: v ? newsList((v.en || []).slice(0, 8), "en") : `<div class="note">${t("news.none")}</div>` };
    }
    return { title: `${code} ${esc(r.tab)}`, html: `<div class="note">${t("lp.not_in_pane")}</div><button class="btn" data-lp-open="${esc(r.tab)}|${esc(tk)}">${t("lp.open_full")}</button>` };
  }
  async function renderLP() {
    const m = meta(); if (!m) return firstRunNotice();
    const layout = lpLayout();
    const panes = await Promise.all(layout.map((cmd, i) => lpPane(cmd, i)));
    const html = `<div class="lp">${panes.map((p, i) => `<section class="panel lp-pane">
        <div class="ph"><span class="ph-title">${p.title}</span><form class="lp-cmd" data-lp="${i}"><input value="${esc(layout[i])}" spellcheck="false" aria-label="${esc(t("lp.cmd"))}"><button class="btn">GO</button></form></div>
        <div class="pb">${p.html}</div></section>`).join("")}</div>
      <p class="note">${t("lp.note")}</p>`;
    return { html, after: () => panes.forEach(p => p.after && p.after()) };
  }

  // ------------------------------------------------------------------ HELP
  function renderHELP() {
    const cmds = [["AAPL", "help.quote"], ["AAPL FA", "help.fa"], ["MC.PA RISK", "help.risk"], ["NVDA NEWS", "help.news"],
      ["MC.PA DES", "help.des"], ["MC.PA COMPS", "help.comps"], ["DEALS", "help.deals"],
      ["MKTS", "help.mkts"], ["EQS", "help.eqs"], ["ECO", "help.eco"], ["LANG FR / LANG EN", "help.lang"], ["HELP", "help.help"]];
    return panel({ title: "HELP", updated: null, source: "Atlas Terminal",
      body: `<div class="help-list">${cmds.map(([c, k]) => `<code>${c}</code> — ${t(k)}`).join("<br>")}</div>` }) + glossaryPanel();
  }

  // ------------------------------------------------------------------ render loop
  let renderSeq = 0;
  async function render() {
    const seq = ++renderSeq;
    renderTabs(); renderClocks();
    renderTape(); renderStatusBar();
    const fn = { LP: renderLP, MKTS: renderMKTS, WEI: renderWEI, MOST: renderMOST, QUOTE: renderQUOTE, GIP: renderGIP, HP: renderHP, DES: renderDES,
      FA: renderFA, DVD: renderDVD, RISK: renderRISK, NEWS: renderNEWS, ECO: renderECO, FXC: renderFXC, EQS: renderEQS, COMPS: renderCOMPS,
      DEALS: renderDEALS, STATUS: renderSTATUS, HELP: renderHELP }[S.tab] || renderMKTS;
    let out = await fn();
    if (seq !== renderSeq) return;            // a newer render started meanwhile
    if (typeof out === "string") out = { html: out };
    destroyCharts();
    $("#main").innerHTML = out.html;
    if (out.after) out.after();
    // numbered menu: every panel of the screen gets a number ("2 <GO>" jumps to the second one)
    setMenu([...document.querySelectorAll("#main .panel")].map((p, i) => {
      if (!p.id) p.id = "pn-" + (i + 1);
      const title = p.querySelector(".ph-title");
      title.insertAdjacentHTML("afterbegin", `<span class="pnum">${i + 1})</span> `);
      return { label: title.textContent.replace(/^\d+\)\s*/, "").replace(/DIFFÉRÉ|DELAYED/g, "").trim().slice(0, 40), target: p.id };
    }));
    renderMenu();
    if (S.pendingSection) { const sec = S.pendingSection; S.pendingSection = null; const el = document.getElementById("sec-" + sec); if (el) el.scrollIntoView({ block: "start" }); }
    flashChanges();
    const hash = "#" + S.tab + (TICKER_TABS.includes(S.tab) ? "/" + encodeURIComponent(S.ticker) : "");
    if (location.hash !== hash) history.replaceState(null, "", hash);
  }
  function go(tab, ticker) {
    if (ticker) S.ticker = ticker;
    S.tab = tab;
    $("#cmdMsg").textContent = "";
    render();
  }

  // ------------------------------------------------------------------ command bar
  // ---- search helper (suggestions under the command bar)
  let SUG = [], SUGI = -1;
  function suggLabel(s) {
    if (s.kind === "ticker") {
      const u = UNI[s.ticker] || {};
      const where = [u.country, u.kind === "stock" ? t("seg." + (u.region === "US" ? "us" : u.segment)) : t("kind." + (u.kind || "stock"))].filter(Boolean).join(" · ");
      return `<b>${esc(s.ticker)}</b><span>${esc(u.name || "")}</span><span class="meta">${esc(where)}</span>`;
    }
    if (s.kind === "fn") return `<b>${esc(s.value)}</b><span>${t("tab." + s.fn)} — ${esc((UNI[s.ticker] || {}).name || "")}</span><span class="meta">${t("sugg.function")}</span>`;
    const tab = s.value.split(" ")[0];
    const desc = s.value.startsWith("LANG") ? t("help.lang") : (C.TABS.includes(tab) ? t("tab." + tab) : t("help.help"));
    return `<b>${esc(s.value)}</b><span>${esc(desc)}</span><span class="meta">${t("sugg.command")}</span>`;
  }
  function renderSugg() {
    const box = $("#cmdSugg"), input = $("#cmd");
    if (!SUG.length) { box.hidden = true; input.setAttribute("aria-expanded", "false"); return; }
    box.innerHTML = SUG.map((s, i) => `<li role="option" id="sugg-${i}" data-sugg="${i}" class="${i === SUGI ? "on" : ""}" aria-selected="${i === SUGI}">${suggLabel(s)}</li>`).join("") +
      `<li class="hint">${t("sugg.hint")}</li>`;
    box.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (SUGI >= 0) { input.setAttribute("aria-activedescendant", "sugg-" + SUGI); const el = $("#sugg-" + SUGI); if (el) el.scrollIntoView({ block: "nearest" }); }
    else input.removeAttribute("aria-activedescendant");
  }
  function updateSugg() {
    const m = meta();
    SUG = m ? C.suggest($("#cmd").value, m.universe, 8) : [];
    SUGI = -1;
    renderSugg();
  }
  function closeSugg() { SUG = []; SUGI = -1; renderSugg(); }
  function runText(text) {
    $("#cmd").value = text;
    closeSugg();
    onCommand(new Event("submit"));
  }
  function pickSugg(i) {
    const s = SUG[i];
    if (s) runText(s.value);
  }
  function onCmdKey(e) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!SUG.length) { updateSugg(); if (!SUG.length) return; }
      e.preventDefault();
      SUGI = e.key === "ArrowDown" ? (SUGI + 1) % SUG.length : (SUGI <= 0 ? SUG.length - 1 : SUGI - 1);
      renderSugg();
    } else if (e.key === "Enter" && SUGI >= 0) {
      e.preventDefault(); pickSugg(SUGI);
    } else if (e.key === "Tab" && SUG.length) {
      // complete the text without running it: "TTE" -> "TTE.PA " (then functions are proposed)
      e.preventDefault();
      const s = SUG[Math.max(SUGI, 0)];
      $("#cmd").value = s.kind === "ticker" ? s.value + " " : s.value;
      updateSugg();
    } else if (e.key === "Escape") {
      closeSugg();
    }
  }

  function onCommand(e) {
    e.preventDefault();
    closeSugg();
    const input = $("#cmd");
    const m = meta();
    const res = C.parseCommand(input.value, m ? m.universe : []);
    if (res.type === "none") return;
    if (res.type === "error") { $("#cmdMsg").textContent = t(res.key, { arg: res.arg || "" }); return; }
    input.value = "";
    if (res.type === "lang") return setLang(res.lang);
    if (res.type === "help") return go("HELP");
    if (res.type === "tab") return go(res.tab);
    if (res.type === "menu") return runMenu(res.n);
    if (res.type === "fn") { S.pendingSection = res.section || null; return go(res.tab, S.ticker); }
    if (res.type === "ticker") {
      S.pendingSection = res.section || null;
      if (res.tab === "NEWS") S.newsTicker = watchlist().includes(res.ticker) ? res.ticker : "ALL";
      if (res.tab === "DEALS") S.deals.ticker = res.ticker;
      if (res.tab === "COMPS") S.comps.sector = null;   // the ticker's own sector
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
      <div class="setting"><span>${t("settings.translate")}</span>${seg("translate", [[true, t("on")], [false, t("off")]])}</div>
      <div class="setting"><span>${t("settings.reset_wl")}</span><button class="btn" data-action="reset-wl">${t("settings.reset")}</button></div>
      <p class="note">${t("settings.note")}</p>`;
  }
  function renderWlEditor() {
    const m = meta(); if (!m) return;
    const wl = watchlist();
    const box = tk => `<label><input type="checkbox" data-wl="${esc(tk)}" ${wl.includes(tk) ? "checked" : ""}>${esc(tk)} <span>${esc(UNI[tk].name)}</span></label>`;
    const group = (title, tks) => (tks.length ? `<div class="wl-h">${title}</div><div class="wl-grid">${tks.map(box).join("")}</div>` : "");
    const all = m.watchlist_universe.map(tk => UNI[tk]);
    const smid = all.filter(u => u.region === "EU" && u.segment === "smid");
    const countries = [...new Set(smid.map(u => u.country))].sort();
    $("#wlBody").innerHTML =
      group(t("region.US"), all.filter(u => u.region === "US").map(u => u.ticker)) +
      group(`${t("region.EU")} — ${t("seg.large")}`, all.filter(u => u.region === "EU" && u.segment !== "smid").map(u => u.ticker)) +
      countries.map(c => group(`${t("region.EU")} — ${t("seg.smid")} — ${t("country." + c)}`, smid.filter(u => u.country === c).map(u => u.ticker))).join("") +
      `<p class="note">${t("wl.note")}</p>`;
  }
  function openDialog(id) { $(id).hidden = false; }
  function closeDialogs() { document.querySelectorAll(".overlay").forEach(o => { o.hidden = true; }); }

  // ------------------------------------------------------------------ events
  function bind() {
    $("#cmdForm").addEventListener("submit", onCommand);
    // launchpad: each window has its own command line; the layout is remembered in this browser
    document.addEventListener("submit", e => {
      const f = e.target.closest("[data-lp]"); if (!f) return;
      e.preventDefault();
      const l = lpLayout(); l[Number(f.dataset.lp)] = f.querySelector("input").value.trim() || LP_DEFAULT[Number(f.dataset.lp)];
      LS.set("lp", l); render();
    });
    $("#cmd").addEventListener("input", updateSugg);
    $("#cmd").addEventListener("keydown", onCmdKey);
    $("#cmd").addEventListener("focus", () => { if ($("#cmd").value.trim()) updateSugg(); });
    $("#cmd").addEventListener("blur", () => setTimeout(closeSugg, 150));
    // mousedown (not click) so it fires before the input loses focus
    $("#cmdSugg").addEventListener("mousedown", e => {
      const li = e.target.closest("[data-sugg]");
      if (li) { e.preventDefault(); pickSugg(Number(li.dataset.sugg)); }
    });
    $("#gearBtn").addEventListener("click", () => { renderSettings(); openDialog("#settings"); });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") closeDialogs();
      if (e.key === "/" && !/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) { e.preventDefault(); $("#cmd").focus(); }
    });
    document.addEventListener("click", async e => {
      const star = e.target.closest("[data-star]");
      if (star) {  // add / remove from watchlist without leaving the screener
        e.stopPropagation();
        const set = new Set(watchlist()), tk = star.dataset.star;
        if (set.has(tk)) set.delete(tk); else set.add(tk);
        S.watchlist = meta().watchlist_universe.filter(x => set.has(x));
        LS.set("watchlist", S.watchlist);
        return render();
      }
      const mi = e.target.closest("[data-menu]");
      if (mi) return runMenu(Number(mi.dataset.menu));
      const hp = e.target.closest("[data-hp]");
      if (hp) { S.hp = hp.dataset.hp; LS.set("hp", S.hp); return render(); }
      const lpo = e.target.closest("[data-lp-open]");
      if (lpo) { const [tab, tk] = lpo.dataset.lpOpen.split("|"); return go(tab, tk); }
      const csv = e.target.closest("[data-csv]");
      if (csv) { e.stopPropagation(); return exportCsv(csv); }
      const des = e.target.closest("[data-goto-des]");
      if (des) return go("DES", des.dataset.gotoDes);
      const fa = e.target.closest("[data-tab-fa]");
      if (fa) { e.preventDefault(); return go("FA", fa.dataset.tabFa); }
      const th = e.target.closest("[data-sort]");
      if (th) {
        const k = th.dataset.sort;
        S.eqs.dir = S.eqs.sort === k ? -S.eqs.dir : (["ticker", "name", "country", "segment"].includes(k) ? 1 : -1);
        S.eqs.sort = k; LS.set("eqs", S.eqs);
        return render();
      }
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
      if (el.dataset.action === "des-ticker") go("DES", el.value);
      if (el.dataset.action === "hp-ticker") go("HP", el.value);
      if (el.dataset.action === "dvd-ticker") go("DVD", el.value);
      if (el.dataset.action === "gip-ticker") go("GIP", el.value);
      if (el.dataset.most) { S.most.region = el.value; LS.set("mostRegion", el.value); render(); }
      if (el.dataset.comps) { S.comps[el.dataset.comps] = el.value; if (el.dataset.comps === "region") LS.set("compsRegion", el.value); render(); }
      if (el.dataset.deals) { S.deals[el.dataset.deals] = el.value; render(); }
      if (el.dataset.action === "news-ticker") { S.newsTicker = el.value; render(); }
      if (el.dataset.eqs) {
        S.eqs[el.dataset.eqs] = el.value;
        if (el.dataset.eqs === "region") S.eqs.country = "ALL";
        LS.set("eqs", S.eqs); render();
      }
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
    else if (!location.hash) S.tab = "MKTS";
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
