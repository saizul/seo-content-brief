"""Score a draft against the brief built from competitor pages."""

from __future__ import annotations

import re

from .analyze import _jaccard, _stem, heading_key
from .extract import Heading, PageData, clean_text, count_words, is_question, tokenize

HEADING_THRESHOLD = 0.5
INTRO_WORDS = 100

# Points per component. Components that do not apply (for example no competitor
# questions) are left out and the score is rescaled to 100.
WEIGHTS = {
    "outline": 30,
    "terms": 25,
    "questions": 15,
    "word_count": 15,
    "keyword_placement": 15,
}

GRADES = ((90, "A"), (75, "B"), (60, "C"), (40, "D"), (0, "F"))

MD_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
MD_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
MD_FENCE = re.compile(r"^(```|~~~)")
MD_INLINE = re.compile(r"[*_`~>]+")


def _fm_title(block: str) -> str:
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == "title":
            return value.strip().strip("\"'")
    return ""


def parse_markdown(text: str, url: str) -> PageData:
    """Parse a Markdown draft into PageData (headings, title, text, words, images)."""
    page = PageData(url=url)
    m = MD_FRONT_MATTER.match(text)
    if m:
        page.title = _fm_title(m.group(1))
        text = text[m.end() :]
    headings, body, in_fence = [], [], False
    for line in text.splitlines():
        if MD_FENCE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        hm = MD_HEADING.match(line)
        if hm:
            level = len(hm.group(1))
            htext = clean_text(MD_INLINE.sub("", MD_LINK.sub(r"\1", hm.group(2))))
            if level <= 3 and htext:
                headings.append(Heading(level, htext))
            if htext and is_question(htext) and htext not in page.questions:
                page.questions.append(htext)
            body.append(htext)
            continue
        alts = MD_IMAGE.findall(line)
        page.images += len(alts)
        page.images_with_alt += sum(1 for a in alts if a.strip())
        line = MD_IMAGE.sub(" ", line)
        body.append(MD_INLINE.sub(" ", MD_LINK.sub(r"\1", line)))
    page.headings = headings
    page.h1 = [h.text for h in headings if h.level == 1]
    if not page.title and page.h1:
        page.title = page.h1[0]
    page.main_text = clean_text(" ".join(body))
    page.word_count = count_words(page.main_text)
    return page


def _stems(text: str) -> list:
    return [_stem(t) for t in tokenize(text)]


def _contains_phrase(haystack: list, phrase: list) -> bool:
    n = len(phrase)
    if not n or n > len(haystack):
        return False
    return any(haystack[i : i + n] == phrase for i in range(len(haystack) - n + 1))


def _best_heading_match(key: frozenset, keys: list) -> tuple:
    best, best_sim = None, 0.0
    for j, other in enumerate(keys):
        sim = _jaccard(key, other)
        if sim > best_sim:
            best, best_sim = j, sim
    return best, best_sim


def check_outline(draft: PageData, outline: list, threshold: float = HEADING_THRESHOLD) -> dict:
    """Which recommended outline sections have a similar H2/H3 in the draft."""
    heads = [h.text for h in draft.headings if h.level in (2, 3)]
    keys = [heading_key(t) for t in heads]
    covered, missing = [], []
    for item in outline:
        j, sim = _best_heading_match(heading_key(item.text), keys)
        if j is not None and sim >= threshold:
            covered.append({"section": item.text, "draft": heads[j], "similarity": round(sim, 2)})
        else:
            missing.append({"section": item.text, "pages": item.pages})
    total = len(outline)
    return {
        "covered": covered,
        "missing": missing,
        "ratio": round(len(covered) / total, 3) if total else None,
    }


def check_questions(draft: PageData, questions: list, threshold: float = HEADING_THRESHOLD) -> dict:
    """A competitor question counts as answered if a draft heading (or question) matches it."""
    candidates = [h.text for h in draft.headings if h.level >= 2] + list(draft.questions)
    keys = [heading_key(t) for t in candidates]
    answered, unanswered = [], []
    for question, pages in questions:
        j, sim = _best_heading_match(heading_key(question), keys)
        if j is not None and sim >= threshold:
            answered.append({"question": question, "draft": candidates[j]})
        else:
            unanswered.append({"question": question, "pages": pages})
    total = len(questions)
    return {
        "answered": answered,
        "unanswered": unanswered,
        "ratio": round(len(answered) / total, 3) if total else None,
    }


def check_terms(draft: PageData, terms: list, top: int = 20) -> dict:
    """Top competitor terms that appear (stem-insensitively) in the draft text or headings."""
    haystack = _stems(" ".join([draft.title, draft.main_text]))
    used, missing = [], []
    for stat in terms[:top]:
        target = used if _contains_phrase(haystack, _stems(stat.term)) else missing
        target.append({"term": stat.term, "pages": stat.doc_freq})
    total = len(used) + len(missing)
    ratio = round(len(used) / total, 3) if total else None
    return {"used": used, "missing": missing, "ratio": ratio}


def check_word_count(draft: PageData, advice) -> dict:
    """Full marks inside the competitor range; partial credit when short or very long."""
    words = draft.word_count
    if advice is None:
        return {"words": words, "low": None, "high": None, "status": "unknown", "ratio": None}
    if words < advice.low:
        status, ratio = "short", words / advice.low if advice.low else 0.0
    elif words > advice.high:
        over = (words - advice.high) / advice.high if advice.high else 0.0
        status, ratio = "long", max(0.5, 1.0 - over)
    else:
        status, ratio = "ok", 1.0
    return {
        "words": words,
        "low": advice.low,
        "high": advice.high,
        "target": advice.target,
        "status": status,
        "ratio": round(ratio, 3),
    }


def _has_keyword(kw: frozenset, text: str) -> bool:
    return bool(kw) and kw <= heading_key(text)


def check_keyword(draft: PageData, keyword: str) -> dict:
    """Keyword placement: title, H1, introduction and at least one H2/H3."""
    kw = heading_key(keyword)
    intro = " ".join(tokenize(draft.main_text)[:INTRO_WORDS])
    places = {
        "title": _has_keyword(kw, draft.title),
        "h1": any(_has_keyword(kw, h) for h in draft.h1),
        "intro": _has_keyword(kw, intro),
        "subheading": any(
            _has_keyword(kw, h.text) for h in draft.headings if h.level in (2, 3)
        ),
    }
    return {
        "keyword": keyword,
        "places": places,
        "ratio": round(sum(places.values()) / len(places), 3) if kw else None,
    }


def grade(score: float) -> str:
    for floor, letter in GRADES:
        if score >= floor:
            return letter
    return "F"


def suggestions(result: dict, limit: int = 8) -> list:
    """Plain-language next steps, most valuable first."""
    out = []
    wc = result["word_count"]
    if wc["status"] == "short":
        out.append(
            f"Expand the draft: {wc['words']} words vs a competitor range of "
            f"{wc['low']}-{wc['high']} (target about {wc['target']})."
        )
    elif wc["status"] == "long":
        out.append(
            f"Consider tightening: {wc['words']} words is above the competitor range "
            f"of {wc['low']}-{wc['high']}."
        )
    missing = result["outline"]["missing"]
    if missing:
        names = ", ".join(f"'{m['section']}'" for m in missing[:limit])
        out.append(f"Add sections competitors cover: {names}.")
    unanswered = result["questions"]["unanswered"]
    if unanswered:
        names = "; ".join(q["question"] for q in unanswered[:limit])
        out.append(f"Answer these questions under their own headings: {names}")
    terms = result["terms"]["missing"]
    if terms:
        out.append(
            "Work in these terms where they fit naturally: "
            + ", ".join(t["term"] for t in terms[:limit])
            + "."
        )
    kw = result["keyword_placement"]
    labels = {"title": "the title", "h1": "the H1", "intro": "the first 100 words",
              "subheading": "at least one H2/H3"}  # fmt: skip
    absent = [labels[k] for k, ok in kw["places"].items() if not ok]
    if absent and kw["ratio"] is not None:
        out.append(f"Use the keyword '{kw['keyword']}' in " + ", ".join(absent) + ".")
    return out


def check_draft(draft: PageData, brief, top_terms: int = 20) -> dict:
    """Score ``draft`` (PageData) against a Brief built from competitor pages."""
    analysis = brief.analysis
    result = {
        "keyword": brief.keyword,
        "draft": {"url": draft.url, "title": draft.title, "words": draft.word_count},
        "competitors": len(brief.pages),
        "outline": check_outline(draft, analysis["outline"]),
        "questions": check_questions(draft, analysis["questions"]),
        "terms": check_terms(draft, analysis["terms"], top=top_terms),
        "word_count": check_word_count(draft, analysis["word_count"]),
        "keyword_placement": check_keyword(draft, brief.keyword),
    }
    earned = possible = 0.0
    components = {}
    for name, weight in WEIGHTS.items():
        ratio = result[name]["ratio"]
        if ratio is None:
            components[name] = None
            continue
        components[name] = round(ratio * weight, 1)
        earned += ratio * weight
        possible += weight
    score = round(100 * earned / possible, 1) if possible else 0.0
    result["components"] = components
    result["score"] = score
    result["grade"] = grade(score)
    result["suggestions"] = suggestions(result)
    return result
