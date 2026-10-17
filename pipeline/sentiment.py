"""FinBERT sentiment (ProsusAI/finbert), CPU only. English headlines only,
each headline scored once (cache keyed by link)."""
from . import config

LABEL_VALUE = {"positive": 1, "neutral": 0, "negative": -1}
_pipe = None


def classifier():
    global _pipe
    if _pipe is None:
        from transformers import pipeline
        _pipe = pipeline("text-classification", model=config.FINBERT_MODEL, device=-1, truncation=True)
    return _pipe


def score_new(headlines, cache, clf=None):
    """Score headlines whose link is not in cache. Mutates and returns cache."""
    todo = [h for h in headlines if h["lang"] == "en" and h["link"] not in cache]
    if todo:
        clf = clf or classifier()
        results = clf([h["title"] for h in todo], batch_size=16)
        for h, r in zip(todo, results):
            cache[h["link"]] = {"label": r["label"].lower(), "score": round(float(r["score"]), 4)}
    return cache


def attach(items, cache):
    for h in items:
        s = cache.get(h["link"]) if h["lang"] == "en" else None
        h["sentiment"] = s["label"] if s else None
        h["confidence"] = s["score"] if s else None
    return items


def average(items):
    """Mean of +1 / 0 / -1 over scored headlines; None if none scored."""
    vals = [LABEL_VALUE[h["sentiment"]] for h in items if h.get("sentiment") in LABEL_VALUE]
    if not vals:
        return None
    return {"score": sum(vals) / len(vals), "n": len(vals),
            "positive": sum(v == 1 for v in vals), "neutral": sum(v == 0 for v in vals),
            "negative": sum(v == -1 for v in vals)}
