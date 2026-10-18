"""probe/result.json (Yahoo check of probe/candidates.txt) -> pipeline/universe_ext.json.

Keeps only candidates Yahoo serves with a recent close (and, after review, a matching company name).
segment = "large" when the market cap is >= EUR 10 bn at generation time, else "smid"; it only picks
the benchmark (Euro Stoxx 50 vs STOXX Europe 600) and the screener filter, never a displayed number.

    python probe/build_universe.py probe/result.json [probe/result2.json ...]
"""
import json
import sys
import unicodedata

# tickers whose Yahoo name shows they are not the intended company (round-1 review); right tickers are in round 2
REJECT = {"MLAA.PA", "ALBI.PA"}
RENAME = {"GPE.PA": "Groupe Pizzorno Environnement", "PARP.PA": "Groupe Partouche", "CRI.PA": "Belgrano (ex-Chargeurs)"}
MIN_LAST_DATE = "2026-09-01"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "".join(c if c.isalnum() else " " for c in s).split()


def name_match(ours, yahoo):
    stop = {"group", "holding", "holdings", "ag", "sa", "se", "nv", "plc", "spa", "asa", "ab", "oyj", "as", "the", "de", "of", "and",
            "co", "inc", "ltd", "limited", "company", "groupe", "s", "a", "n", "v", "b", "bank", "banca", "banco"}
    a, b = set(norm(ours)) - stop, set(norm(yahoo)) - stop
    if not a or not b:
        return True
    return bool(a & b) or any(x[:5] == y[:5] for x in a for y in b if len(x) >= 4 and len(y) >= 4)


def main(paths):
    rows, rates = {}, {"EUR": 1.0}
    for p in paths:
        for r in json.load(open(p, encoding="utf-8")):
            if r["ticker"].endswith("=X") and r.get("ok"):
                rates[r["ticker"][3:6]] = r["last_close"]
                continue
            rows[r["ticker"]] = r          # later files (fix rounds) win
    out, review = [], []
    for t, r in rows.items():
        if not r.get("ok") or (r.get("last_date") or "") < MIN_LAST_DATE or t in REJECT or r["mic"] == "none":
            continue
        if r.get("yahoo_name") and not name_match(r["name"], r["yahoo_name"]):
            review.append((t, r["name"], r["yahoo_name"]))
        cap, ccy = r.get("market_cap"), r.get("currency")
        if ccy == "GBp":
            cap, ccy = (cap or 0) / 100, "GBP"
        eur = cap / rates[ccy] if cap and ccy in rates else None
        out.append({"ticker": t, "name": RENAME.get(t, r["name"]), "mic": r["mic"], "country": r["country"],
                    "segment": "large" if eur and eur >= 10e9 else "smid", "classified_from_mcap": eur is not None,
                    "currency": r.get("currency")})
    json.dump(out, open("pipeline/universe_ext.json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(out)} kept; {sum(1 for o in out if o['segment'] == 'large')} large; "
          f"{sum(1 for o in out if not o['classified_from_mcap'])} without market cap (smid by default)")
    for x in review:
        print("REVIEW name:", *x)


if __name__ == "__main__":
    main(sys.argv[1:])
