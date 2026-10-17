"""M&A activity: (1) SEC filings that signal a deal, (2) headlines that mention a deal
(keyword detection on the news already collected — labelled as such, may contain false positives)."""
import re

DEAL_FORMS = {
    "SC 13D": "stake_13d", "SC 13D/A": "stake_13d", "SCHEDULE 13D": "stake_13d", "SCHEDULE 13D/A": "stake_13d",
    "SC TO-T": "tender_third", "SC TO-T/A": "tender_third", "SC TO-I": "tender_issuer", "SC TO-I/A": "tender_issuer",
    "SC 14D9": "tender_response", "SC 14D9/A": "tender_response",
    "S-4": "merger_registration", "S-4/A": "merger_registration", "F-4": "merger_registration", "F-4/A": "merger_registration",
    "DEFM14A": "merger_proxy", "PREM14A": "merger_proxy", "425": "merger_communication",
}
DEAL_ITEMS = {"1.01": "material_agreement", "2.01": "acquisition_completed"}

MA_PATTERNS = [
    r"\bacquir(e|es|ed|ing)\b", r"\bacquisitions?\b", r"\bmergers?\b", r"\btakeover\b", r"\bbuyout\b",
    r"\btender offer\b", r"\bbid for\b", r"\bto buy\b.*\b(stake|unit|business|company|rival|maker|firm)\b",
    r"\bdivest(s|ed|iture|ment)?\b", r"\bspin[- ]?off\b", r"\btakes? a stake\b",
    r"\brach[eè]te\b", r"\brach[eè]tent\b", r"\brachat de\b", r"\bfusion\b", r"\bOPA\b", r"\bOPE\b", r"\boffre publique\b",
    r"\bcession\b", r"\bc[eé]der son\b", r"\bc[eé]der sa\b", r"\bc[eé]der ses\b", r"\bprise de contr[oô]le\b",
    r"\brapprochement\b", r"\bentr[eé]e au capital\b",
]
# Not M&A: share buybacks, portfolio managers buying/selling N shares, "cède x %" (= the share price falls)
_EXCLUDE = re.compile(
    r"\b(buyback|share repurchase|repurchase program|treasury shares|insider shares|insider|rachats? d'actions|programme de rachat|actions propres|acquisition d'actions)\b"
    r"|\b\d[\d,.\u202f\u00a0 ]*\s+(new\s+)?(shares|actions)\b"
    r"|\b(position|holdings?|stake) (in|of)\b.*\b(LLC|Inc\.?|L\.?P\.?|Management|Advisors?|Partners|Capital|Wealth)\b"
    r"|\b(LLC|Management|Advisors?|Partners|Capital|Wealth)\b.*\b(acquires?|buys|sells|position|stake)\b"
    r"|\bshares (acquired|bought|sold|purchased)\b|\b(acquires?|buys?|sells?|purchases?) (\w+ )?shares\b"
    r"|\$[A-Z]{1,5}\b.*\bshares\b|\bshares\b.*\$[A-Z]{1,5}\b"
    r"|\bdepositary shares\b|\b(executives?|directors?|insiders?|CEO|CFO|chairman|dirigeants?)\b.*\b(acquires?|buys?|sells?|ach[eè]tent|ach[eè]te)\b",
    re.IGNORECASE)
_MA_RE = [re.compile(p, re.IGNORECASE) for p in MA_PATTERNS]


def ma_match(title):
    """Return the first M&A keyword found in a headline, or None."""
    if not title or _EXCLUDE.search(title):
        return None
    for rx in _MA_RE:
        m = rx.search(title)
        if m:
            return m.group(0)
    return None


def deal_filings(submissions, cik, n=40):
    rec = submissions.get("filings", {}).get("recent", {})
    out = []
    for i, form in enumerate(rec.get("form", [])):
        items = (rec.get("items") or [""] * (i + 1))[i] or ""
        kinds = []
        if form in DEAL_FORMS:
            kinds.append(DEAL_FORMS[form])
        if form.startswith("8-K"):
            kinds += [DEAL_ITEMS[it.strip()] for it in items.split(",") if it.strip() in DEAL_ITEMS]
        if not kinds:
            continue
        acc = rec["accessionNumber"][i]
        doc = rec["primaryDocument"][i]
        out.append({"form": form, "filed": rec["filingDate"][i], "items": items, "kinds": kinds,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"})
        if len(out) >= n:
            break
    return out


def news_deals(news_data, limit=150):
    out = []
    for tk, v in (news_data or {}).items():
        for h in (v.get("en") or []) + (v.get("fr") or []):
            kw = ma_match(h.get("title"))
            if kw:
                out.append({"ticker": tk, "keyword": kw, **{k: h.get(k) for k in ("title", "title_fr", "link", "published", "publisher", "feed", "lang")}})
    seen, uniq = set(), []
    for d in sorted(out, key=lambda x: x.get("published") or "", reverse=True):
        if d["link"] in seen:
            continue
        seen.add(d["link"])
        uniq.append(d)
    return uniq[:limit]
