"""Cross-competitor analysis: terms (TF-IDF), merged outline, word-count range."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .extract import is_question, tokenize
from .stopwords import ALL as STOPWORDS

SENTENCE_SPLIT = re.compile(r"[.!?;:।\n•|]+")


@dataclass
class TermStat:
    term: str
    doc_freq: int
    total_count: int
    score: float


@dataclass
class OutlineItem:
    text: str
    level: int
    pages: int
    position: float
    variants: list = field(default_factory=list)


@dataclass
class WordCountAdvice:
    low: int
    high: int
    target: int
    median: int
    samples: int


def content_tokens(text: str) -> list:
    return tokenize(text)


def _is_term_token(tok: str) -> bool:
    return tok not in STOPWORDS and len(tok) > 1 and not tok.isdigit()


def ngrams_in_text(text: str, max_n: int = 3) -> Counter:
    """Count 1..max_n-grams made only of non-stopword tokens, within sentences."""
    counts: Counter = Counter()
    for sentence in SENTENCE_SPLIT.split(text):
        toks = tokenize(sentence)
        run: list = []
        runs = []
        for tok in toks:
            if _is_term_token(tok):
                run.append(tok)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)
        for r in runs:
            for n in range(1, max_n + 1):
                for i in range(len(r) - n + 1):
                    counts[" ".join(r[i : i + n])] += 1
    return counts


def _is_subphrase(short: str, long: str) -> bool:
    return short != long and f" {short} " in f" {long} "


def min_doc_freq(n_docs: int) -> int:
    if n_docs <= 1:
        return 1
    return max(2, math.ceil(0.3 * n_docs))


def tfidf_terms(texts: list, top: int = 30, max_n: int = 3, min_df: int | None = None) -> list:
    """Rank terms shared across competitor texts by summed sublinear TF-IDF."""
    n_docs = len(texts)
    if n_docs == 0:
        return []
    if min_df is None:
        min_df = min_doc_freq(n_docs)
    doc_counts = [ngrams_in_text(t, max_n) for t in texts]
    df: Counter = Counter()
    for c in doc_counts:
        df.update(c.keys())
    stats = []
    for term, d in df.items():
        if d < min_df:
            continue
        idf = math.log((n_docs + 1) / (d + 0.5)) + 1.0
        total = 0
        score = 0.0
        for c in doc_counts:
            cnt = c.get(term, 0)
            if cnt:
                total += cnt
                score += (1.0 + math.log(cnt)) * idf
        n_words = len(term.split())
        score = score / n_docs * (1 + 0.15 * (n_words - 1))
        stats.append(TermStat(term, d, total, round(score, 4)))
    stats.sort(key=lambda s: (-s.score, s.term))
    pool = stats[: max(top * 8, 100)]
    kept = []
    for s in pool:
        redundant = any(
            o is not s
            and o.doc_freq == s.doc_freq
            and o.total_count == s.total_count
            and _is_subphrase(s.term, o.term)
            for o in pool
        )
        if not redundant:
            kept.append(s)
        if len(kept) >= top:
            break
    return kept


def _stem(tok: str) -> str:
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def heading_key(text: str) -> frozenset:
    return frozenset(_stem(t) for t in tokenize(text) if t not in STOPWORDS and not t.isdigit())


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def merge_outline(
    pages: list, threshold: float = 0.6, max_items: int = 15, min_pages: int | None = None
) -> list:
    """Cluster similar H2/H3 headings across pages; order by average position."""
    n_pages = len(pages)
    if min_pages is None:
        min_pages = 1 if n_pages <= 1 else 2
    clusters: list = []
    for page in pages:
        heads = [h for h in page.headings if h.level in (2, 3) and not is_question(h.text)]
        total = max(len(heads), 1)
        seen_here: set = set()
        for idx, h in enumerate(heads):
            key = heading_key(h.text)
            if not key:
                continue
            target = None
            best = 0.0
            for ci, c in enumerate(clusters):
                sim = _jaccard(key, c["key"])
                if sim >= threshold and sim > best:
                    target, best = ci, sim
            if target is None:
                clusters.append(
                    {"key": key, "texts": Counter(), "levels": Counter(), "pages": set(), "pos": []}
                )
                target = len(clusters) - 1
            c = clusters[target]
            c["texts"][h.text] += 1
            c["levels"][h.level] += 1
            if target not in seen_here:
                c["pages"].add(page.url)
                c["pos"].append(idx / total)
                seen_here.add(target)
    items = []
    for c in clusters:
        if len(c["pages"]) < min_pages:
            continue
        label = sorted(c["texts"].items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]
        items.append(
            OutlineItem(
                text=label,
                level=c["levels"].most_common(1)[0][0],
                pages=len(c["pages"]),
                position=sum(c["pos"]) / len(c["pos"]),
                variants=sorted(t for t in c["texts"] if t != label),
            )
        )
    items.sort(key=lambda i: (-i.pages, i.position))
    items = items[:max_items]
    items.sort(key=lambda i: i.position)
    return items


def percentile(values: list, q: float) -> float:
    if not values:
        raise ValueError("no values")
    data = sorted(values)
    if len(data) == 1:
        return float(data[0])
    k = (len(data) - 1) * q
    lo = math.floor(k)
    hi = math.ceil(k)
    return data[lo] + (data[hi] - data[lo]) * (k - lo)


def _round50(x: float) -> int:
    return int(round(x / 50.0) * 50)


def word_count_advice(counts: list) -> WordCountAdvice | None:
    counts = [c for c in counts if c > 0]
    if not counts:
        return None
    median = percentile(counts, 0.5)
    if len(counts) == 1:
        low, high = median * 0.9, median * 1.15
    elif len(counts) < 4:
        low, high = min(counts), max(counts)
    else:
        low, high = percentile(counts, 0.25), percentile(counts, 0.75)
    lo, hi, mid = _round50(low), _round50(high), _round50(median)
    if hi <= lo:
        hi = lo + 100
    mid = min(max(mid, lo), hi)
    return WordCountAdvice(lo, hi, mid, int(round(median)), len(counts))


def collect_questions(pages: list, limit: int = 15) -> list:
    """Return (question, pages_count) sorted by how many competitors ask it."""
    counter: Counter = Counter()
    display: dict = {}
    for page in pages:
        seen = set()
        for q in page.questions:
            key = " ".join(tokenize(q))
            if not key or key in seen:
                continue
            seen.add(key)
            counter[key] += 1
            display.setdefault(key, q)
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(display[k], n) for k, n in ranked[:limit]]


MINOR_SCHEMA_TYPES = frozenset(
    {"Answer", "Question", "ListItem", "ImageObject", "PropertyValue", "Person", "Thing"}
)


def schema_summary(pages: list) -> list:
    """Return (type, pages_count) sorted by prevalence, ignoring nested helper types."""
    counter: Counter = Counter()
    for p in pages:
        counter.update(t for t in set(p.schema_types) if t not in MINOR_SCHEMA_TYPES)
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))


def average(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


def page_text_stats(pages: list) -> dict:
    n = len(pages)
    imgs = sum(p.images for p in pages)
    alts = sum(p.images_with_alt for p in pages)
    return {
        "pages": n,
        "avg_words": average([p.word_count for p in pages]),
        "avg_internal_links": average([p.internal_links for p in pages]),
        "avg_external_links": average([p.external_links for p in pages]),
        "avg_images": average([p.images for p in pages]),
        "alt_coverage": (alts / imgs) if imgs else 1.0,
        "with_author": sum(1 for p in pages if p.has_author),
        "with_date": sum(1 for p in pages if p.has_date),
    }


def analyze_pages(pages: list, top_terms: int = 30) -> dict:
    return {
        "word_count": word_count_advice([p.word_count for p in pages]),
        "outline": merge_outline(pages),
        "questions": collect_questions(pages),
        "terms": tfidf_terms([p.main_text for p in pages], top=top_terms),
        "schema": schema_summary(pages),
        "stats": page_text_stats(pages),
    }
