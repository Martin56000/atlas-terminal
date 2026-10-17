"""Health of every data source, written to status.json (STATUS tab) and, from GitHub Actions,
turned into a GitHub issue assigned to the repository owner (GitHub then sends an e-mail):
opened when something has been failing for too long, closed automatically once it recovers.

    python -m pipeline.health              # write status.json
    python -m pipeline.health --github     # + open / update / close the alert issue
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, store

PARIS = ZoneInfo("Europe/Paris")
ISSUE_LABEL = "atlas-health"
TICKER_FAIL_DAYS = 3

# dataset -> (what it is, expected refresh in hours on a normal weekday, critical?)
DATASETS = {
    "quotes.json": ("Cotations (Yahoo Finance)", 26, True),
    "news.json": ("News + sentiment + traduction", 26, True),
    "macro.json": ("Macro (Trésor US, Fed NY, BLS, BCE, FRED)", 30, True),
    "risk.json": ("Métriques de risque", 30, True),
    "companies.json": ("Fiches société / COMPS", 30, True),
    "deals.json": ("DEALS", 30, False),
    "validation.json": ("Contrôle croisé", 30, False),
    "perf.json": ("Performances (WEI, MOST)", 30, False),
    "intraday.json": ("Intraday (GIP)", 30, False),
}


def allowed_hours(base_h, now_utc):
    """Weekends (and Monday before the 08:30 run) add 72 h: nothing is fetched on Saturday / Sunday."""
    p = now_utc.astimezone(PARIS)
    if p.weekday() >= 5 or (p.weekday() == 0 and p.hour < 10):
        return base_h + 72
    return base_h


def age_h(iso, now_utc):
    if not iso:
        return None
    return (now_utc - datetime.fromisoformat(iso)).total_seconds() / 3600


def last_success_of(env):
    m = (env or {}).get("_meta") or {}
    if m.get("last_success"):
        return m["last_success"]
    regs = m.get("regions")                     # quotes.json keeps one status per region
    if regs:
        ok = [r.get("last_success") for r in regs.values() if r.get("last_success")]
        return min(ok) if ok else None
    return m.get("fetched_at") if m.get("status") == "ok" else None


def update_fail_since(state, key, failing, error, now_iso):
    fs = state.setdefault("fail_since", {})
    if failing:
        if key not in fs:
            fs[key] = {"since": now_iso, "error": error}
        else:
            fs[key]["error"] = error
    else:
        fs.pop(key, None)


def compute(now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    rows, problems = [], []
    for name, (label, base_h, critical) in DATASETS.items():
        env = store.read(name)
        m = (env or {}).get("_meta") or {}
        last_ok = last_success_of(env)
        a = age_h(last_ok, now_utc)
        limit = allowed_hours(base_h, now_utc)
        ok = a is not None and a <= limit
        err = m.get("error")
        if not ok and m.get("regions"):
            err = " | ".join(f"{k}: {v.get('error')}" for k, v in m["regions"].items() if v.get("status") == "error") or err
        rows.append({"name": name, "label": label, "source": m.get("source"), "fetched_at": m.get("fetched_at"),
                     "last_success": last_ok, "status": m.get("status") or ("ok" if last_ok else "missing"),
                     "error": err, "max_age_h": limit, "age_h": a, "ok": ok, "critical": critical})
        if not ok and critical:
            problems.append(f"{label} : pas de mise à jour réussie depuis "
                            f"{'jamais' if a is None else f'{a:.0f} h'} (limite {limit} h). {err or ''}".strip())
    state = store.read("state.json") or {}
    failing = []
    for key, v in (state.get("fail_since") or {}).items():
        days = age_h(v["since"], now_utc) / 24
        failing.append({"key": key, "since": v["since"], "days": days, "error": v.get("error")})
    failing.sort(key=lambda x: -x["days"])
    long_fail = [f for f in failing if f["days"] >= TICKER_FAIL_DAYS]
    if long_fail:
        problems.append(f"{len(long_fail)} élément(s) en échec depuis plus de {TICKER_FAIL_DAYS} jours : "
                        + ", ".join(f["key"] for f in long_fail[:15]))
    val = ((store.read("validation.json") or {}).get("data") or {})
    if val and val.get("all_passed") is False:
        problems.append("Le contrôle croisé AAPL / MC.PA a détecté un écart.")
    meta = store.read("meta.json") or {}
    counts = {}
    for prefix in ("company", "esef"):
        d = os.path.join(store.DATA_DIR, prefix)
        files = [f for f in os.listdir(d)] if os.path.isdir(d) else []
        ok = sum(1 for f in files if (store.read(f"{prefix}/{f}") or {}).get("_meta", {}).get("status") == "ok")
        counts[prefix] = {"ok": ok, "total": len(files)}
    return {"generated_at": now_utc.replace(microsecond=0).isoformat(), "last_run": meta.get("generated_at"),
            "datasets": rows, "failing": failing, "problems": problems, "counts": counts,
            "universe": len(config.UNIVERSE)}


# ---------------- GitHub issue (e-mail alert) ----------------------------------------------------
def _gh(method, path, token, body=None):
    import requests
    r = requests.request(method, "https://api.github.com" + path, json=body, timeout=30,
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    r.raise_for_status()
    return r.json() if r.text else {}


def sync_issue(status, repo, token, owner, run_url=None, pipeline_failed=False):
    problems = list(status["problems"])
    if pipeline_failed:
        problems.insert(0, "Le passage de mise à jour s'est arrêté sur une erreur (voir le journal du workflow).")
    open_issues = _gh("GET", f"/repos/{repo}/issues?state=open&labels={ISSUE_LABEL}", token)
    if problems:
        body = ("Alerte automatique d'Atlas Terminal.\n\n" + "\n".join(f"- {p}" for p in problems) +
                f"\n\nDétail : onglet STATUS du site." + (f"\nJournal : {run_url}" if run_url else "") +
                "\n\nCette issue se fermera toute seule quand tout sera revenu à la normale.")
        if open_issues:
            _gh("PATCH", f"/repos/{repo}/issues/{open_issues[0]['number']}", token, {"body": body})
        else:
            _gh("POST", f"/repos/{repo}/issues", token, {"title": "⚠ Atlas Terminal : des données ne se mettent plus à jour",
                                                         "body": body, "labels": [ISSUE_LABEL], "assignees": [owner]})
    else:
        for iss in open_issues:
            _gh("POST", f"/repos/{repo}/issues/{iss['number']}/comments", token, {"body": "Tout est revenu à la normale. ✅"})
            _gh("PATCH", f"/repos/{repo}/issues/{iss['number']}", token, {"state": "closed"})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--github", action="store_true")
    ap.add_argument("--pipeline-failed", action="store_true")
    args = ap.parse_args(argv)
    status = compute()
    store.write("status.json", status)
    print(json.dumps({"problems": status["problems"]}, ensure_ascii=False, indent=1))
    if args.github:
        repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
        owner = os.environ.get("GITHUB_REPOSITORY_OWNER") or (repo or "/").split("/")[0]
        run_url = (f"{os.environ.get('GITHUB_SERVER_URL')}/{repo}/actions/runs/{os.environ.get('GITHUB_RUN_ID')}"
                   if os.environ.get("GITHUB_RUN_ID") else None)
        if repo and token:
            try:
                sync_issue(status, repo, token, owner, run_url, args.pipeline_failed)
            except Exception as e:  # noqa: BLE001 - the alert must never break the site update
                print(f"could not sync the GitHub issue: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
