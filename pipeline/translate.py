"""Machine translation of English headlines into French (Helsinki-NLP/opus-mt-en-fr, CPU).
Each headline is translated once (cache keyed by link). The original title is always kept;
sentiment is still scored on the original English title."""
from . import config

_pipe = None


def translator():
    """Seq2seq model called directly (transformers v5 removed the 'translation' pipeline)."""
    global _pipe
    if _pipe is None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(config.TRANSLATE_MODEL)
        model = AutoModelForSeq2SeqLM.from_pretrained(config.TRANSLATE_MODEL)
        model.eval()

        def run(titles, batch_size=16, max_length=256):
            out = []
            for i in range(0, len(titles), batch_size):
                enc = tok(titles[i:i + batch_size], return_tensors="pt", padding=True, truncation=True, max_length=max_length)
                with torch.no_grad():
                    gen = model.generate(**enc, max_new_tokens=128, num_beams=2)
                out += [{"translation_text": s} for s in tok.batch_decode(gen, skip_special_tokens=True)]
            return out
        _pipe = run
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
