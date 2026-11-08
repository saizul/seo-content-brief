# Contributing

Thanks for helping improve seo-content-brief.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before opening a pull request

- `ruff check .` and `ruff format .` pass.
- `pytest` passes. New behaviour needs a test; extraction changes should add or extend an HTML
  fixture in `tests/fixtures/` (synthetic content only, never copy real pages).
- Tests must not use the network. Use the fake session pattern in `tests/test_fetch.py`.
- Keep the project supporting Python 3.10-3.13 (CI runs all four).

## Principles

- Stay polite: never add search-engine scraping, never bypass robots.txt by default.
- Keep dependencies small: requests, beautifulsoup4, rich, jinja2.
- Bangla support matters. When touching tokenisation or stopwords, add a Bangla test.

## Reporting issues

Please include the command you ran and, if possible, a minimal HTML snippet that reproduces the problem.
