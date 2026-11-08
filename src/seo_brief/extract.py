"""Extract SEO-relevant data from a single HTML page."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

TOKEN_RE = re.compile(r"[A-Za-z0-9ঀ-৿]+(?:['’][A-Za-z]+)?")
BANGLA_RE = re.compile(r"[ঀ-৿]")
QUESTION_ENDINGS = ("?", "？", "؟")

NOISE_TAGS = ("script", "style", "noscript", "template", "svg", "iframe", "form", "button")
LAYOUT_TAGS = ("nav", "footer", "aside", "header")
NOISE_HINT = re.compile(
    r"(comment|sidebar|footer|breadcrumb|share|social|related|advert|promo|cookie|popup|"
    r"newsletter|menu|navbar|widget)",
    re.I,
)
SKIP_HINT_TAGS = ("html", "body", "article", "main")


@dataclass
class Heading:
    level: int
    text: str


@dataclass
class PageData:
    url: str
    title: str = ""
    meta_description: str = ""
    canonical: str = ""
    lang: str = ""
    h1: list = field(default_factory=list)
    headings: list = field(default_factory=list)  # list[Heading], H1-H3 in main content
    main_text: str = ""
    word_count: int = 0
    questions: list = field(default_factory=list)
    schema_types: list = field(default_factory=list)
    internal_links: int = 0
    external_links: int = 0
    images: int = 0
    images_with_alt: int = 0
    has_author: bool = False
    has_date: bool = False

    @property
    def alt_coverage(self) -> float:
        return self.images_with_alt / self.images if self.images else 1.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["alt_coverage"] = round(self.alt_coverage, 3)
        return d


def tokenize(text: str) -> list:
    """Lowercase word tokens; supports Latin, digits and the Bengali block."""
    return [t.lower() for t in TOKEN_RE.findall(text)]


def count_words(text: str) -> int:
    return len(TOKEN_RE.findall(text))


def bangla_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha() or BANGLA_RE.match(c)]
    if not letters:
        return 0.0
    return sum(1 for c in letters if BANGLA_RE.match(c)) / len(letters)


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_question(text: str) -> bool:
    return clean_text(text).endswith(QUESTION_ENDINGS)


def _strip_noise(soup: BeautifulSoup) -> None:
    for el in soup.find_all(NOISE_TAGS):
        if not el.decomposed:
            el.decompose()
    for el in soup.find_all(LAYOUT_TAGS):
        if el.decomposed:
            continue
        # a <header> inside an article often holds the H1; keep it there
        if el.name == "header" and el.find_parent(["article", "main"]) is not None:
            continue
        el.decompose()
    for el in soup.find_all(True):
        if el.decomposed or el.name in SKIP_HINT_TAGS:
            continue
        hint = " ".join(el.get("class") or []) + " " + (el.get("id") or "")
        if hint.strip() and NOISE_HINT.search(hint):
            el.decompose()
    roles = ["navigation", "banner", "contentinfo", "complementary"]
    for el in soup.find_all(attrs={"role": roles}):
        if not el.decomposed:
            el.decompose()


def _text_len(node: Tag) -> int:
    return len(clean_text(node.get_text(" ")))


def _link_density(node: Tag) -> float:
    total = _text_len(node)
    if not total:
        return 1.0
    link_len = sum(len(clean_text(a.get_text(" "))) for a in node.find_all("a"))
    return min(1.0, link_len / total)


def _score_candidate(soup: BeautifulSoup) -> Tag | None:
    """Readability-style: paragraphs vote for their parent and grandparent."""
    scores: dict = {}
    nodes: dict = {}
    for p in soup.find_all("p"):
        text = clean_text(p.get_text(" "))
        if len(text) < 25:
            continue
        points = 1 + text.count(",") + text.count("।") + min(len(text) // 100, 3)
        parent = p.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            continue
        scores[id(parent)] = scores.get(id(parent), 0) + points
        nodes[id(parent)] = parent
        grand = parent.parent
        if grand is not None and grand.name not in ("body", "html", "[document]"):
            scores[id(grand)] = scores.get(id(grand), 0) + points / 2
            nodes[id(grand)] = grand
    best, best_score = None, 0.0
    for key, score in scores.items():
        node = nodes[key]
        adjusted = score * (1 - _link_density(node))
        if adjusted > best_score:
            best, best_score = node, adjusted
    return best


def find_main_node(soup: BeautifulSoup) -> Tag:
    """Return the node most likely to hold the primary content."""
    semantic = soup.find_all(["article", "main"]) + soup.find_all(attrs={"role": "main"})
    semantic = [n for n in semantic if not n.decomposed]
    if semantic:
        best = max(semantic, key=_text_len)
        if _text_len(best) >= 200:
            return best
    scored = _score_candidate(soup)
    if scored is not None:
        return scored
    if semantic:
        return max(semantic, key=_text_len)
    return soup.body or soup


def _walk_jsonld(obj, types: list, questions: list) -> None:
    if isinstance(obj, list):
        for item in obj:
            _walk_jsonld(item, types, questions)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        names = [t] if isinstance(t, str) else [x for x in (t or []) if isinstance(x, str)]
        for name in names:
            if name not in types:
                types.append(name)
        if "Question" in names and isinstance(obj.get("name"), str):
            questions.append(clean_text(obj["name"]))
        for value in obj.values():
            if isinstance(value, (list, dict)):
                _walk_jsonld(value, types, questions)


def extract_jsonld(soup: BeautifulSoup) -> tuple:
    """Return (schema @types, Question names) from all JSON-LD blocks."""
    types: list = []
    questions: list = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            continue
        _walk_jsonld(data, types, questions)
    return types, questions


def _host(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def classify_links(node: Tag, base_url: str) -> tuple:
    """Return (internal, external) counts of http(s)/relative links under node."""
    base_host = _host(base_url)
    internal = external = 0
    for a in node.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#"):
            continue
        scheme = urlparse(href).scheme.lower()
        if scheme and scheme not in ("http", "https"):
            continue
        if href.startswith("//") or scheme:
            target = _host(urljoin(base_url, href)) if base_host else _host(href)
            if base_host and target == base_host:
                internal += 1
            else:
                external += 1
        else:
            internal += 1
    return internal, external


def detect_author(soup: BeautifulSoup) -> bool:
    if soup.find("meta", attrs={"name": re.compile(r"^author$", re.I)}):
        return True
    if soup.find(attrs={"rel": "author"}) or soup.find(attrs={"itemprop": "author"}):
        return True
    return soup.find(class_=re.compile(r"(^|[-_ ])(author|byline)([-_ ]|$)", re.I)) is not None


def detect_date(soup: BeautifulSoup) -> bool:
    if soup.find("time"):
        return True
    return bool(
        soup.find(
            "meta",
            attrs={"property": re.compile(r"article:(published|modified)_time", re.I)},
        )
    )


def parse_html(html: str, url: str) -> PageData:
    """Parse one HTML document into a PageData record."""
    soup = BeautifulSoup(html, "html.parser")
    page = PageData(url=url)

    if soup.html is not None:
        page.lang = (soup.html.get("lang") or "").strip()
    if soup.title is not None:
        page.title = clean_text(soup.title.get_text())
    meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if meta is not None:
        page.meta_description = clean_text(meta.get("content", ""))
    canon = soup.find("link", attrs={"rel": "canonical"})
    if canon is not None and canon.get("href"):
        page.canonical = canon["href"].strip()

    page.schema_types, schema_questions = extract_jsonld(soup)
    page.has_author = detect_author(soup)
    page.has_date = detect_date(soup)
    all_h1 = [clean_text(h.get_text(" ")) for h in soup.find_all("h1")]

    _strip_noise(soup)
    main = find_main_node(soup)

    headings, questions = [], []
    for h in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = clean_text(h.get_text(" "))
        if not text:
            continue
        level = int(h.name[1])
        if level <= 3:
            headings.append(Heading(level, text))
        if is_question(text) and text not in questions:
            questions.append(text)
    for q in schema_questions:
        if q and q not in questions:
            questions.append(q)

    page.h1 = [h.text for h in headings if h.level == 1] or [h for h in all_h1 if h]
    page.headings = headings
    page.questions = questions
    page.main_text = clean_text(main.get_text(" "))
    page.word_count = count_words(page.main_text)
    page.internal_links, page.external_links = classify_links(main, page.canonical or url)
    imgs = main.find_all("img")
    page.images = len(imgs)
    page.images_with_alt = sum(1 for i in imgs if clean_text(i.get("alt") or ""))
    return page
