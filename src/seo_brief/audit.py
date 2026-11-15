"""On-page technical audit of a single HTML page (no competitors needed)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .extract import _host, clean_text, parse_html, tokenize
from .stopwords import is_stopword

SEVERITIES = ("error", "warning", "notice")
PENALTY = {"error": 15, "warning": 5, "notice": 1}

TITLE_RANGE = (30, 60)
DESCRIPTION_RANGE = (70, 160)
THIN_CONTENT_WORDS = 300
OG_PROPERTIES = ("og:title", "og:description", "og:image")


@dataclass
class Finding:
    code: str
    severity: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> str | None:
    tag = soup.find("meta", attrs={attr: re.compile(rf"^{re.escape(value)}$", re.I)})
    if tag is None:
        return None
    return clean_text(tag.get("content", ""))


def _length_finding(kind: str, text: str, low: int, high: int) -> Finding | None:
    n = len(text)
    if n < low:
        return Finding(
            f"{kind}-short",
            "warning",
            f"{kind.capitalize()} is {n} characters (aim for {low}-{high})",
        )
    if n > high:
        return Finding(
            f"{kind}-long",
            "warning",
            f"{kind.capitalize()} is {n} characters and may be truncated (aim for {low}-{high})",
        )
    return None


def heading_skips(levels: list) -> list:
    """Return (from, to) pairs where the outline jumps down more than one level."""
    skips = []
    prev = 0
    for level in levels:
        if prev and level > prev + 1:
            skips.append((prev, level))
        prev = level
    return skips


def _check_title(soup, findings: list) -> str:
    title = clean_text(soup.title.get_text()) if soup.title is not None else ""
    if not title:
        findings.append(Finding("title-missing", "error", "The page has no <title>"))
        return ""
    found = _length_finding("title", title, *TITLE_RANGE)
    if found:
        findings.append(found)
    return title


def _check_description(soup, findings: list) -> str:
    desc = _meta_content(soup, "name", "description")
    if not desc:
        findings.append(
            Finding(
                "description-missing",
                "warning",
                "No meta description; search engines will pick text",
            )
        )
        return ""
    found = _length_finding("description", desc, *DESCRIPTION_RANGE)
    if found:
        findings.append(found)
    return desc


def _check_headings(soup, findings: list) -> list:
    tags = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    pairs = [(int(h.name[1]), clean_text(h.get_text(" "))) for h in tags]
    h1 = [text for level, text in pairs if level == 1]
    if not h1:
        findings.append(Finding("h1-missing", "error", "The page has no H1"))
    elif len(h1) > 1:
        findings.append(Finding("h1-multiple", "warning", f"The page has {len(h1)} H1 headings"))
    if any(level == 1 and not text for level, text in pairs):
        findings.append(Finding("h1-empty", "warning", "An H1 heading is empty"))
    for prev, level in heading_skips([level for level, _ in pairs]):
        findings.append(
            Finding("heading-skip", "notice", f"Heading level jumps from H{prev} to H{level}")
        )
    return h1


def _check_indexing(soup, findings: list) -> bool:
    noindex = False
    for name in ("robots", "googlebot"):
        content = (_meta_content(soup, "name", name) or "").lower()
        directives = {d.strip() for d in content.split(",")}
        if "noindex" in directives or "none" in directives:
            noindex = True
            findings.append(
                Finding("noindex", "error", f'meta name="{name}" blocks indexing ({content})')
            )
    return noindex


def _check_canonical(soup, url: str, findings: list) -> str:
    links = [
        link
        for link in soup.find_all("link", href=True)
        if "canonical" in [str(r).lower() for r in (link.get("rel") or [])]
    ]
    hrefs = [link.get("href", "").strip() for link in links if link.get("href", "").strip()]
    if not hrefs:
        findings.append(Finding("canonical-missing", "notice", "No canonical link"))
        return ""
    if len(set(hrefs)) > 1:
        findings.append(
            Finding("canonical-multiple", "error", f"{len(set(hrefs))} different canonical URLs")
        )
    canonical = hrefs[0]
    parsed = urlparse(canonical)
    if not parsed.scheme or not parsed.netloc:
        findings.append(
            Finding("canonical-relative", "warning", f"Canonical is not absolute: {canonical}")
        )
    elif urlparse(url).scheme in ("http", "https") and _host(canonical) != _host(url):
        findings.append(
            Finding(
                "canonical-cross-domain",
                "notice",
                f"Canonical points to another host: {_host(canonical)}",
            )
        )
    return canonical


def _check_head_basics(soup, findings: list) -> None:
    lang = (soup.html.get("lang") or "").strip() if soup.html is not None else ""
    if not lang:
        findings.append(Finding("lang-missing", "warning", "<html> has no lang attribute"))
    if _meta_content(soup, "name", "viewport") is None:
        findings.append(
            Finding(
                "viewport-missing",
                "warning",
                "No meta viewport; the page may not be mobile friendly",
            )
        )
    missing = [p for p in OG_PROPERTIES if not _meta_content(soup, "property", p)]
    if missing:
        findings.append(
            Finding(
                "open-graph-missing", "notice", "Missing Open Graph tags: " + ", ".join(missing)
            )
        )


def _check_jsonld(soup, findings: list) -> int:
    bad = 0
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = (script.string or script.get_text() or "").strip()
        try:
            json.loads(raw)
        except (ValueError, TypeError):
            bad += 1
    if bad:
        findings.append(
            Finding("jsonld-invalid", "warning", f"{bad} JSON-LD block(s) are not valid JSON")
        )
    return bad


def _check_images(soup, findings: list) -> int:
    missing = [img for img in soup.find_all("img") if img.get("alt") is None]
    if missing:
        findings.append(
            Finding(
                "img-alt-missing",
                "warning",
                f'{len(missing)} image(s) have no alt attribute (use alt="" for decorative images)',
            )
        )
    return len(missing)


def _contains_keyword(text: str, keyword_tokens: list) -> bool:
    if not keyword_tokens:
        return False
    tokens = tokenize(text)
    n = len(keyword_tokens)
    return any(tokens[i : i + n] == keyword_tokens for i in range(len(tokens) - n + 1))


def _slug_has_keyword(slug: str, keyword_tokens: list) -> bool:
    """URL slugs often drop stopwords, so only the content words must all appear."""
    words = set(tokenize(slug))
    needed = [t for t in keyword_tokens if not is_stopword(t)] or keyword_tokens
    return bool(needed) and all(t in words for t in needed)


def _check_keyword(keyword: str, places: dict, findings: list) -> dict:
    kw = tokenize(keyword)
    result = {}
    for name, text in places.items():
        if name == "url":
            result[name] = _slug_has_keyword(text, kw)
        else:
            result[name] = _contains_keyword(text, kw)
    for name, ok in result.items():
        if not ok:
            findings.append(
                Finding(f"keyword-{name}", "notice", f"Keyword '{keyword}' is not in the {name}")
            )
    return result


def score(findings: list) -> int:
    return max(0, 100 - sum(PENALTY[f.severity] for f in findings))


def audit_html(html: str, url: str, keyword: str = "") -> dict:
    """Audit one HTML document and return a JSON-serialisable result."""
    soup = BeautifulSoup(html, "html.parser")
    findings: list = []
    title = _check_title(soup, findings)
    description = _check_description(soup, findings)
    h1 = _check_headings(soup, findings)
    noindex = _check_indexing(soup, findings)
    canonical = _check_canonical(soup, url, findings)
    _check_head_basics(soup, findings)
    _check_jsonld(soup, findings)
    _check_images(soup, findings)

    page = parse_html(html, canonical if urlparse(canonical).netloc else url)
    if page.word_count < THIN_CONTENT_WORDS:
        findings.append(
            Finding(
                "thin-content",
                "warning",
                f"Main content has {page.word_count} words (under {THIN_CONTENT_WORDS})",
            )
        )
    keyword_places = None
    if keyword.strip():
        slug = re.sub(r"[-_/]+", " ", urlparse(canonical or url).path)
        keyword_places = _check_keyword(
            keyword.strip(),
            {"title": title, "h1": " ".join(h1), "description": description, "url": slug},
            findings,
        )

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order[f.severity])
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITIES}
    return {
        "url": url,
        "score": score(findings),
        "counts": counts,
        "title": title,
        "description": description,
        "canonical": canonical,
        "noindex": noindex,
        "word_count": page.word_count,
        "keyword": keyword_places,
        "findings": [f.to_dict() for f in findings],
    }


def fails(result: dict, fail_on: str | None) -> bool:
    """True when the result has a finding at or above the fail_on severity."""
    if not fail_on:
        return False
    limit = SEVERITIES.index(fail_on)
    return any(result["counts"][s] for s in SEVERITIES[: limit + 1])
