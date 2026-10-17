"""Headlines: yfinance Ticker.news first, Google News RSS always as well.
Nothing is ever invented: an empty feed gives an empty list."""
import calendar
import urllib.parse
from datetime import datetime, timezone

from . import config


def strip_publisher(title, publisher):
    """Google News titles end with ' - Publisher'."""
    if publisher and title.endswith(" - " + publisher):
        return title[: -(len(publisher) + 3)].strip()
    return title.strip()


def _iso_from_struct(st):
    if not st:
        return None
    return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc).isoformat()


def parse_google_feed(parsed, feed_label, lang):
    items = []
    for e in parsed.entries:
        src = e.get("source") or {}
        publisher = src.get("title") if hasattr(src, "get") else None
        title = strip_publisher(e.get("title", ""), publisher)
        link = e.get("link")
        if not title or not link:
            continue
        items.append({"title": title, "publisher": publisher, "published": _iso_from_struct(e.get("published_parsed")),
                      "link": link, "feed": feed_label, "lang": lang})
    return items


def parse_yahoo_news(raw):
    """Handles both the old flat format and the newer {'content': {...}} format."""
    items = []
    for n in raw or []:
        c = n.get("content") if isinstance(n.get("content"), dict) else None
        if c:
            title = c.get("title")
            pub = (c.get("provider") or {}).get("displayName")
            link = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url"))
            published = c.get("pubDate")
            if published and published.endswith("Z"):
                published = published[:-1] + "+00:00"
        else:
            title = n.get("title")
            pub = n.get("publisher")
            link = n.get("link")
            ts = n.get("providerPublishTime")
            published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
        if title and link:
            items.append({"title": title.strip(), "publisher": pub, "published": published,
                          "link": link, "feed": "Yahoo", "lang": "en"})
    return items


def merge_latest(items, n):
    """Deduplicate by link and by title, keep the n most recent."""
    seen_links, seen_titles, out = set(), set(), []
    for it in sorted(items, key=lambda x: x.get("published") or "", reverse=True):
        key_t = it["title"].lower()
        if it["link"] in seen_links or key_t in seen_titles:
            continue
        seen_links.add(it["link"])
        seen_titles.add(key_t)
        out.append(it)
        if len(out) >= n:
            break
    return out


RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8,fr;q=0.6",
}
RSS_COOKIES = {"CONSENT": "YES+"}  # avoids the EU cookie-consent interstitial


def fetch_rss(url):
    import feedparser
    import requests
    r = requests.get(url, headers=RSS_HEADERS, cookies=RSS_COOKIES, timeout=30)
    r.raise_for_status()
    body = r.content
    if b"<rss" not in body[:2000] and b"<feed" not in body[:2000]:
        ctype = r.headers.get("content-type", "?")
        raise ValueError(f"not an RSS feed (HTTP {r.status_code}, {ctype}, {len(body)} bytes, starts: {body[:80]!r})")
    return feedparser.parse(body)


def fetch_for_ticker(ticker):
    import yfinance as yf
    info = config.BY_TICKER[ticker]
    errors = []

    en_items = []
    try:
        en_items += parse_yahoo_news(yf.Ticker(ticker).news)
    except Exception as e:  # noqa: BLE001
        errors.append(f"Yahoo: {e}")
    try:
        q_en = urllib.parse.quote_plus(info["query_en"] or ticker)
        en_items += parse_google_feed(fetch_rss(config.GOOGLE_NEWS_EN.format(q=q_en)), "Google News EN", "en")
    except Exception as e:  # noqa: BLE001
        errors.append(f"Google News EN: {type(e).__name__}: {e}"[:300])

    fr_items = []
    if info["query_fr"]:
        try:
            q_fr = urllib.parse.quote_plus(info["query_fr"])
            fr_items = parse_google_feed(fetch_rss(config.GOOGLE_NEWS_FR.format(q=q_fr)), "Google News FR", "fr")
        except Exception as e:  # noqa: BLE001
            errors.append(f"Google News FR: {type(e).__name__}: {e}"[:300])

    return {
        "en": merge_latest(en_items, config.NEWS_PER_LANG),
        "fr": merge_latest(fr_items, config.NEWS_PER_LANG) if info["query_fr"] else None,
        "errors": errors,
    }
