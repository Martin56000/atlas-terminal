"""Machine translation of English headlines into French (Helsinki-NLP/opus-mt-en-fr, CPU).
Each headline is translated once (cache keyed by link). The original title is always kept;
sentiment is still scored on the original English title."""
from . import config

_pipe = None


def translator():
    global _pipe
    if _pipe is None:
        from transformers import pipeline
        _pipe = pipeline("translation", model=config.TRANSLATE_MODEL, device=-1)
    return _pipe


def translate_new(headlines, cache, tr=None):
    """Translate English headlines whose link is not in cache. Mutates and returns cache."""
    todo = [h for h in headlines if h["lang"] == "en" and h["link"] not in cache]
    if todo:
        tr = tr or translator()
        results = tr([h["title"] for h in todo], batch_size=16, max_length=256)
        for h, r in zip(todo, results):
            text = (r.get("translation_text") or "").strip()
            if text:
                cache[h["link"]] = text
    return cache


def attach(items, cache):
    for h in items:
        h["title_fr"] = cache.get(h["link"]) if h["lang"] == "en" else None
    return items
