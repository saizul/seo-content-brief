# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `seo-brief check DRAFT`: score a Markdown, text or HTML draft (or URL) out of 100 against the brief built from the same competitors, covering outline sections, terms, questions, word count and keyword placement, with next-step suggestions, `--json` output and a `--min-score` exit code for CI.
- `seo-brief build --front-matter`: prepend a YAML front matter block to the Markdown brief so it can be imported into static site generators and CMSs.
- `seo-brief compare PAGE_A PAGE_B`: shared and unique headings and terms between two pages (URL or local HTML file), with `--json` output.

## [0.1.0] - 2026-11-08

### Added
- `seo-brief build` and `seo-brief analyze` commands.
- Polite fetcher: robots.txt, custom User-Agent, per-host delay, disk cache with TTL.
- Offline mode reading saved HTML files.
- Page extraction: main content heuristic, H1-H3 outline, word counts, question headings,
  JSON-LD types, link counts, image alt coverage, author/date signals.
- Cross-competitor analysis: TF-IDF n-gram terms (English and Bangla stopwords),
  merged outline, word-count range.
- Markdown, HTML and JSON output with an E-E-A-T checklist.
- Test suite with HTML fixtures, ruff configuration and GitHub Actions CI (Python 3.10-3.13).
