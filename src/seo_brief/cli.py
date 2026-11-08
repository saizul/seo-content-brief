"""Command line interface: seo-brief."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import __version__
from .brief import build_brief, render_html, render_markdown
from .compare import compare_pages
from .extract import parse_html
from .fetch import DEFAULT_UA, Fetcher, load_offline


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\u0980-\u09FF]+", "-", text.strip().lower()).strip("-")
    return slug or "brief"


def read_urls_file(path) -> list:
    urls = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="seo-brief",
        description="Build an SEO content brief from competitor pages you supply.",
    )
    p.add_argument("--version", action="version", version=f"seo-brief {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("-k", "--keyword", required=True, help="target keyword or topic")
        sp.add_argument("-u", "--url", action="append", default=[], help="competitor URL (repeat)")
        sp.add_argument("--urls-file", help="text file with one competitor URL per line")
        sp.add_argument(
            "--offline", metavar="DIR", help="read saved .html files instead of fetching"
        )
        sp.add_argument("--cache-dir", default=".seo-brief-cache", help="disk cache directory")
        sp.add_argument("--no-cache", action="store_true", help="disable the disk cache")
        sp.add_argument(
            "--delay", type=float, default=2.0, help="seconds between requests (per host)"
        )
        sp.add_argument("--timeout", type=float, default=15.0, help="request timeout in seconds")
        sp.add_argument("--user-agent", default=DEFAULT_UA, help="custom User-Agent string")

    b = sub.add_parser("build", help="fetch/read pages and write the brief files")
    common(b)
    b.add_argument("-o", "--out", default="brief-output", help="output directory")
    b.add_argument("-f", "--format", default="md,html", help="comma list of: md, html, json")

    a = sub.add_parser("analyze", help="print a per-page comparison table")
    common(a)
    a.add_argument("--json", action="store_true", help="print JSON instead of a table")

    c = sub.add_parser("compare", help="show heading and term overlap between two pages")
    c.add_argument("page_a", metavar="PAGE_A", help="URL or saved .html file")
    c.add_argument("page_b", metavar="PAGE_B", help="URL or saved .html file")
    c.add_argument("--top", type=int, default=15, help="terms to list per group (default 15)")
    c.add_argument("--json", action="store_true", help="print JSON instead of tables")
    c.add_argument("--cache-dir", default=".seo-brief-cache", help="disk cache directory")
    c.add_argument("--no-cache", action="store_true", help="disable the disk cache")
    c.add_argument("--delay", type=float, default=2.0, help="seconds between requests (per host)")
    c.add_argument("--timeout", type=float, default=15.0, help="request timeout in seconds")
    c.add_argument("--user-agent", default=DEFAULT_UA, help="custom User-Agent string")
    return p


def collect_pages(args, console: Console) -> tuple:
    """Return (pages, skipped) from offline files or polite fetching."""
    pages, skipped = [], []
    if args.offline:
        for name, html in load_offline(args.offline):
            page = parse_html(html, f"file://{name}")
            if page.canonical:
                page = parse_html(html, page.canonical)
            else:
                page.url = name
            pages.append(page)
        return pages, skipped
    urls = list(args.url)
    if args.urls_file:
        urls += read_urls_file(args.urls_file)
    urls = list(dict.fromkeys(urls))
    if not urls:
        raise SystemExit("error: provide --url, --urls-file or --offline")
    fetcher = Fetcher(
        cache_dir=None if args.no_cache else args.cache_dir,
        delay=args.delay,
        timeout=args.timeout,
        user_agent=args.user_agent,
    )
    for url in urls:
        res = fetcher.fetch(url)
        if not res.ok:
            skipped.append((url, res.error or "empty response"))
            console.print(f"[yellow]skip[/yellow] {url}: {res.error}")
            continue
        suffix = " (cache)" if res.from_cache else ""
        console.print(f"[green]ok[/green] {url}{suffix}")
        pages.append(parse_html(res.html, url))
    return pages, skipped


def cmd_build(args, console: Console) -> int:
    pages, skipped = collect_pages(args, console)
    if not pages:
        console.print("[red]No pages could be analysed.[/red]")
        return 2
    brief = build_brief(args.keyword, pages, skipped)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = slugify(args.keyword)
    formats = [f.strip().lower() for f in args.format.split(",") if f.strip()]
    written = []
    if "md" in formats:
        path = out / f"{stem}.md"
        path.write_text(render_markdown(brief), encoding="utf-8")
        written.append(path)
    if "html" in formats:
        path = out / f"{stem}.html"
        path.write_text(render_html(brief), encoding="utf-8")
        written.append(path)
    if "json" in formats:
        path = out / f"{stem}.json"
        data = {"keyword": brief.keyword, "pages": [p.to_dict() for p in pages]}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
    for path in written:
        console.print(f"wrote {path}")
    return 0


def cmd_analyze(args, console: Console) -> int:
    pages, _ = collect_pages(args, console)
    if not pages:
        console.print("[red]No pages could be analysed.[/red]")
        return 2
    if args.json:
        print(json.dumps([p.to_dict() for p in pages], ensure_ascii=False, indent=2))
        return 0
    table = Table(title=f"Competitors for: {args.keyword}")
    for col in ("Page", "Words", "H2/H3", "?", "Int", "Ext", "Img", "Alt%", "Schema"):
        table.add_column(col, overflow="fold")
    for p in pages:
        h23 = sum(1 for h in p.headings if h.level in (2, 3))
        table.add_row(
            p.url, str(p.word_count), str(h23), str(len(p.questions)),
            str(p.internal_links), str(p.external_links), str(p.images),
            f"{p.alt_coverage * 100:.0f}", ", ".join(p.schema_types) or "-",
        )  # fmt: skip
    console.print(table)
    return 0


def _load_one(source: str, fetcher_args, console: Console):
    """Parse a local HTML file, or fetch a URL politely. Returns PageData or None."""
    path = Path(source)
    if "://" not in source and path.is_file():
        return parse_html(path.read_text(encoding="utf-8", errors="replace"), path.name)
    if "://" not in source:
        raise FileNotFoundError(f"file not found: {source}")
    fetcher = Fetcher(
        cache_dir=None if fetcher_args.no_cache else fetcher_args.cache_dir,
        delay=fetcher_args.delay,
        timeout=fetcher_args.timeout,
        user_agent=fetcher_args.user_agent,
    )
    res = fetcher.fetch(source)
    if not res.ok:
        console.print(f"[yellow]skip[/yellow] {source}: {res.error or 'empty response'}")
        return None
    return parse_html(res.html, source)


def cmd_compare(args, console: Console) -> int:
    if args.top < 1:
        console.print("[red]error:[/red] --top must be at least 1")
        return 2
    page_a = _load_one(args.page_a, args, console)
    page_b = _load_one(args.page_b, args, console)
    if page_a is None or page_b is None:
        console.print("[red]Both pages are needed to compare.[/red]")
        return 2
    result = compare_pages(page_a, page_b, top=args.top)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    stats = Table(title="Page comparison")
    for col in ("", "A", "B"):
        stats.add_column(col, overflow="fold")
    for key, label in (
        ("url", "Page"), ("words", "Words"), ("headings", "H2/H3 (non-question)"),
        ("questions", "Questions"), ("internal_links", "Internal links"),
        ("external_links", "External links"), ("images", "Images"),
    ):  # fmt: skip
        stats.add_row(label, str(result["a"][key]), str(result["b"][key]))
    stats.add_row(
        "Schema", ", ".join(result["a"]["schema_types"]) or "-",
        ", ".join(result["b"]["schema_types"]) or "-",
    )  # fmt: skip
    console.print(stats)
    heads = result["headings"]
    console.print(
        f"\nHeading overlap: {heads['overlap'] * 100:.0f}% ({len(heads['shared'])} shared)"
    )
    for item in heads["shared"]:
        console.print(f"  = {item['a']}  [dim]~ {item['b']}[/dim]", highlight=False)
    for text in heads["only_a"]:
        console.print(f"  A only: {text}", highlight=False)
    for text in heads["only_b"]:
        console.print(f"  B only: {text}", highlight=False)
    terms = result["terms"]
    console.print(f"\nTerm overlap: {terms['overlap'] * 100:.0f}%")
    console.print(
        "  Shared: "
        + (", ".join(f"{t['term']} ({t['a']}/{t['b']})" for t in terms["shared"]) or "-"),
        highlight=False,
    )
    console.print(
        "  A only: " + (", ".join(t["term"] for t in terms["only_a"]) or "-"), highlight=False
    )
    console.print(
        "  B only: " + (", ".join(t["term"] for t in terms["only_b"]) or "-"), highlight=False
    )
    return 0


def main(argv: list | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console(file=sys.stderr if getattr(args, "json", False) else None)
    try:
        if args.command == "build":
            return cmd_build(args, console)
        if args.command == "compare":
            return cmd_compare(args, console)
        return cmd_analyze(args, console)
    except FileNotFoundError as exc:
        console.print(f"[red]error:[/red] {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
