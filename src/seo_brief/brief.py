"""Assemble and render the content brief (Markdown and HTML)."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from jinja2 import Environment

from .analyze import analyze_pages
from .extract import bangla_ratio


@dataclass
class Brief:
    keyword: str
    generated: str
    pages: list
    skipped: list = field(default_factory=list)  # [(url, reason)]
    analysis: dict = field(default_factory=dict)
    checklist: list = field(default_factory=list)  # [(category, text)]
    schema_suggestions: list = field(default_factory=list)
    language: str = "en"


def detect_language(keyword: str, pages: list) -> str:
    sample = keyword + " " + " ".join(p.main_text[:2000] for p in pages)
    return "bn" if bangla_ratio(sample) > 0.4 else "en"


def eeat_checklist(analysis: dict, keyword: str) -> list:
    st = analysis["stats"]
    n = st["pages"]
    ext = max(2, int(round(st["avg_external_links"])))
    items = [
        (
            "Experience",
            f"Show first-hand experience with '{keyword}': original screenshots, photos, "
            "data or a short case result that competitors cannot copy.",
        ),
        (
            "Experience",
            "Add a concrete example, mini case study or walkthrough with real numbers.",
        ),
        (
            "Expertise",
            f"Add a visible byline with author credentials ({st['with_author']} of {n} "
            "competitors show an author) and link to an author bio page.",
        ),
        (
            "Expertise",
            "Have a subject-matter expert review the draft; note the reviewer and review date.",
        ),
        (
            "Authoritativeness",
            f"Cite at least {ext} reputable external sources (competitors average "
            f"{st['avg_external_links']:.1f} external links in the main content).",
        ),
        (
            "Authoritativeness",
            "Link related in-depth pages on your own site "
            f"(competitors average {st['avg_internal_links']:.1f} internal links).",
        ),
        (
            "Trust",
            f"Show a published date and a last-updated date ({st['with_date']} of {n} "
            "competitors show a date).",
        ),
        (
            "Trust",
            "Provide clear contact details, an About page and an editorial policy; "
            "disclose affiliate or sponsored relationships.",
        ),
        (
            "Trust",
            "Serve the page over HTTPS and fact-check every statistic against a primary source.",
        ),
        (
            "Content quality",
            f"Give every image descriptive alt text (competitor alt coverage: "
            f"{st['alt_coverage'] * 100:.0f}%).",
        ),
    ]
    return items


def suggest_schema(analysis: dict) -> list:
    seen = {t for t, _ in analysis["schema"]}
    out = []
    if not seen & {"Article", "BlogPosting", "NewsArticle"}:
        out.append("Article (or BlogPosting) with author, datePublished and dateModified")
    else:
        out.append("Article/BlogPosting with author, datePublished and dateModified")
    if analysis["questions"]:
        out.append("FAQPage for the question section (only if the answers are visible on the page)")
    if "BreadcrumbList" in seen:
        out.append("BreadcrumbList (used by competitors)")
    if "Organization" in seen or "WebSite" in seen:
        out.append("Organization / WebSite markup at site level")
    return out


def build_brief(keyword: str, pages: list, skipped: list | None = None, today=None) -> Brief:
    if not pages:
        raise ValueError("at least one successfully analysed page is required")
    analysis = analyze_pages(pages)
    today = today or _dt.date.today()
    return Brief(
        keyword=keyword,
        generated=today.isoformat(),
        pages=pages,
        skipped=skipped or [],
        analysis=analysis,
        checklist=eeat_checklist(analysis, keyword),
        schema_suggestions=suggest_schema(analysis),
        language=detect_language(keyword, pages),
    )


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(brief: Brief) -> str:
    a = brief.analysis
    wc = a["word_count"]
    st = a["stats"]
    lines = [f"# Content brief: {brief.keyword}", ""]
    lines.append(f"Generated {brief.generated} from {st['pages']} competitor page(s).")
    lines.append("")
    lines.append("## Recommended length")
    lines.append("")
    if wc:
        lines.append(
            f"- Word count range: **{wc.low}-{wc.high}** words (target about {wc.target})."
        )
        lines.append(f"- Competitor median: {wc.median} words across {wc.samples} page(s).")
    lines.append(f"- Images: aim for about {round(st['avg_images'])} with descriptive alt text.")
    lines.append(
        f"- Links: about {round(st['avg_internal_links'])} internal and "
        f"{round(st['avg_external_links'])} external."
    )
    if brief.language == "bn":
        lines.append("- Language: Bangla content detected; keep terminology consistent in Bangla.")
    lines += ["", "## Suggested outline", ""]
    if a["outline"]:
        lines.append("- H1: a title containing the target keyword")
        for item in a["outline"]:
            indent = "   " if item.level == 3 else ""
            lines.append(
                f"{indent}- H{item.level}: {item.text} _(used by {item.pages}/{st['pages']})_"
            )
    else:
        lines.append("_No shared headings found; build the outline from the questions below._")
    lines += ["", "## Questions to answer", ""]
    if a["questions"]:
        for q, n in a["questions"]:
            lines.append(f"- {q} _(asked by {n}/{st['pages']})_")
    else:
        lines.append("_No question-style headings were found in the competitor pages._")
    lines += ["", "## Terms to cover", ""]
    if a["terms"]:
        lines += ["| Term | Pages | Mentions | Score |", "|---|---:|---:|---:|"]
        for t in a["terms"]:
            lines.append(
                f"| {_md_escape(t.term)} | {t.doc_freq} | {t.total_count} | {t.score:.2f} |"
            )
    else:
        lines.append("_Not enough shared vocabulary found._")
    lines += ["", "## Structured data", ""]
    if a["schema"]:
        lines.append("Seen on competitors: " + ", ".join(f"{t} ({n})" for t, n in a["schema"]))
    else:
        lines.append("No JSON-LD structured data found on competitors.")
    lines.append("")
    lines += [f"- Suggested: {s}" for s in brief.schema_suggestions]
    lines += ["", "## E-E-A-T checklist", ""]
    current = None
    for cat, text in brief.checklist:
        if cat != current:
            lines.append(f"**{cat}**")
            current = cat
        lines.append(f"- [ ] {text}")
    lines += ["", "## Competitor snapshot", ""]
    lines += [
        "| URL | Words | H2/H3 | Questions | Int. links | Ext. links | Images | Alt % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for p in brief.pages:
        h23 = sum(1 for h in p.headings if h.level in (2, 3))
        lines.append(
            f"| {_md_escape(p.url)} | {p.word_count} | {h23} | {len(p.questions)} | "
            f"{p.internal_links} | {p.external_links} | {p.images} | {p.alt_coverage * 100:.0f} |"
        )
    if brief.skipped:
        lines += ["", "## Skipped URLs", ""]
        lines += [f"- {u}: {reason}" for u, reason in brief.skipped]
    lines.append("")
    return "\n".join(lines)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="{{ 'bn' if b.language == 'bn' else 'en' }}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Content brief: {{ b.keyword }}</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:860px;margin:2rem auto;
padding:0 1rem;line-height:1.55;color:#1d2330}
h1{font-size:1.7rem}h2{margin-top:2rem;border-bottom:1px solid #dde1ea;padding-bottom:.25rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border:1px solid #dde1ea;padding:.35rem .5rem;text-align:left}th{background:#f4f6fa}
.muted{color:#667085}.l3{margin-left:1.5rem}code{background:#f4f6fa;padding:0 .25rem}
</style>
</head>
<body>
<h1>Content brief: {{ b.keyword }}</h1>
<p class="muted">Generated {{ b.generated }} from {{ st.pages }} competitor page(s).</p>
<h2>Recommended length</h2>
<ul>
{% if wc %}<li>Word count range: <strong>{{ wc.low }}-{{ wc.high }}</strong> words
(target about {{ wc.target }}).</li>
<li>Competitor median: {{ wc.median }} words across {{ wc.samples }} page(s).</li>{% endif %}
<li>Images: aim for about {{ st.avg_images|round|int }} with descriptive alt text.</li>
<li>Links: about {{ st.avg_internal_links|round|int }} internal and
{{ st.avg_external_links|round|int }} external.</li>
</ul>
<h2>Suggested outline</h2>
{% if a.outline %}<ul>
<li>H1: a title containing the target keyword</li>
{% for i in a.outline %}<li class="{{ 'l3' if i.level == 3 else '' }}">H{{ i.level }}: {{ i.text }}
<span class="muted">(used by {{ i.pages }}/{{ st.pages }})</span></li>
{% endfor %}</ul>{% else %}<p class="muted">No shared headings found.</p>{% endif %}
<h2>Questions to answer</h2>
{% if a.questions %}<ul>{% for q, n in a.questions %}<li>{{ q }}
<span class="muted">(asked by {{ n }}/{{ st.pages }})</span></li>{% endfor %}</ul>
{% else %}<p class="muted">No question-style headings were found.</p>{% endif %}
<h2>Terms to cover</h2>
{% if a.terms %}<table><tr><th>Term</th><th>Pages</th><th>Mentions</th><th>Score</th></tr>
{% for t in a.terms %}<tr><td>{{ t.term }}</td><td>{{ t.doc_freq }}</td><td>{{ t.total_count }}</td>
<td>{{ '%.2f'|format(t.score) }}</td></tr>
{% endfor %}</table>{% else %}<p class="muted">Not enough shared vocabulary found.</p>{% endif %}
<h2>Structured data</h2>
{% if a.schema %}<p>Seen on competitors: {% for t, n in a.schema %}<code>{{ t }}</code> ({{ n }}){{ ', ' if not loop.last }}{% endfor %}</p>
{% else %}<p>No JSON-LD structured data found on competitors.</p>{% endif %}
<ul>{% for s in b.schema_suggestions %}<li>Suggested: {{ s }}</li>{% endfor %}</ul>
<h2>E-E-A-T checklist</h2>
{% for cat, items in groups %}<h3>{{ cat }}</h3>
<ul style="list-style:none;padding-left:0">{% for text in items %}<li><label><input type="checkbox"> {{ text }}</label></li>
{% endfor %}</ul>
{% endfor %}
<h2>Competitor snapshot</h2>
<table><tr><th>URL</th><th>Words</th><th>H2/H3</th><th>Questions</th><th>Int. links</th>
<th>Ext. links</th><th>Images</th><th>Alt %</th></tr>
{% for p in b.pages %}<tr><td>{{ p.url }}</td><td>{{ p.word_count }}</td>
<td>{{ p.headings|selectattr('level', 'in', [2, 3])|list|length }}</td>
<td>{{ p.questions|length }}</td><td>{{ p.internal_links }}</td><td>{{ p.external_links }}</td>
<td>{{ p.images }}</td><td>{{ (p.alt_coverage * 100)|round|int }}</td></tr>
{% endfor %}</table>
{% if b.skipped %}<h2>Skipped URLs</h2><ul>{% for u, r in b.skipped %}<li>{{ u }}: {{ r }}</li>{% endfor %}</ul>{% endif %}
</body>
</html>
"""


def render_html(brief: Brief) -> str:
    env = Environment(autoescape=True)
    groups: list = []
    for cat, text in brief.checklist:
        if groups and groups[-1][0] == cat:
            groups[-1][1].append(text)
        else:
            groups.append((cat, [text]))
    tpl = env.from_string(HTML_TEMPLATE)
    return tpl.render(
        b=brief,
        a=brief.analysis,
        st=brief.analysis["stats"],
        wc=brief.analysis["word_count"],
        groups=groups,
    )
