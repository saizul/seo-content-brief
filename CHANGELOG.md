# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
