"""Machine translation of English headlines into French (Helsinki-NLP/opus-mt-tc-big-en-fr, CPU).
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
                    gen = model.generate(**enc, max_new_tokens=128, num_beams=4)
                out += [{"translation_text": s} for s in tok.batch_decode(gen, skip_special_tokens=True)]
            return out
        _pipe = run
    return _pipe


# In finance headlines "stock" means a share, which MT models often render literally as "stock".
GLOSSARY = [
    (r"\bLes stocks de\b", "Les actions"), (r"\bles stocks de\b", "les actions"),
    (r"\bLe stock de\b", "L'action"), (r"\ble stock de\b", "l'action"),
    (r"\bLe stock\b", "L'action"), (r"\ble stock\b", "l'action"),
    (r"\bdu stock\b", "de l'action"),
]


def fix_terms(text):
    import re
    for pat, rep in GLOSSARY:
        text = re.sub(pat, rep, text)
    return text


def translate_new(headlines, cache, tr=None, budget_s=None, batch=16):
    """Translate English headlines whose link is not in cache, newest first, within a time budget
    (the rest stays in English and is translated in the next runs). Mutates and returns cache."""
    import time
    todo = [h for h in headlines if h["lang"] == "en" and h["link"] not in cache]
    todo.sort(key=lambda h: h.get("published") or "", reverse=True)
    if todo:
        tr = tr or translator()
        start = time.monotonic()
        for i in range(0, len(todo), batch):
            if budget_s is not None and time.monotonic() - start > budget_s:
                break
            chunk = todo[i:i + batch]
            for h, r in zip(chunk, tr([h["title"] for h in chunk], batch_size=batch, max_length=256)):
                text = (r.get("translation_text") or "").strip()
                if text:
                    cache[h["link"]] = fix_terms(text)
    return cache


def attach(items, cache):
    for h in items:
        tr = cache.get(h["link"]) if h["lang"] == "en" else None
        h["title_fr"] = fix_terms(tr) if tr else None   # also fixes translations cached before the glossary
    return items


def split_sentences(text):
    import re
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", (text or "").strip())
    return [p for p in parts if p]


def translate_text(text, tr=None, max_sentences=None):
    """Long text -> French, sentence by sentence (the model handles ~one sentence well).
    max_sentences: translate only the beginning (an excerpt), which keeps CPU time reasonable."""
    sents = split_sentences(text)[:max_sentences] if max_sentences else split_sentences(text)
    if not sents:
        return None
    tr = tr or translator()
    out = tr(sents, batch_size=8, max_length=256)
    return fix_terms(" ".join((r.get("translation_text") or "").strip() for r in out))
