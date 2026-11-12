# seo-content-brief

Turn a target keyword and a handful of competitor URLs into a practical **SEO content brief**: recommended
length, a merged outline, questions to answer, terms to cover, schema ideas and an E-E-A-T checklist.
Output is Markdown and a self-contained HTML page.

Built by [Saizul Amin](https://saizul.com). MIT licensed.

## Why

Writing a brief by hand means opening ten tabs and copying headings into a doc. This tool does the
mechanical part, honestly and politely, and leaves the judgement to you.

- You supply the competitor URLs. There is **no search engine scraping**.
- Fetching is polite: `robots.txt` is respected, a descriptive User-Agent is sent, requests to the same
  host are spaced by a configurable delay, and responses are cached on disk.
- An **offline mode** analyses HTML files you saved yourself, so you can work without any network access.
- English and **Bangla** are both supported (tokenisation, stopwords, question detection).

## What it extracts

Per page: title, meta description, canonical, language, H1-H3 outline, main-content word count,
question headings (ending in `?`), JSON-LD `@type` values (including `@graph` and `FAQPage` questions),
internal/external link counts, image count and alt-text coverage, and whether an author and a date are shown.

Across pages: a recommended word-count range (interquartile range of competitors, rounded to 50),
a merged outline of headings that several competitors share (Jaccard similarity on stemmed, stopword-free
headings), the most-asked questions, and the top single words, bigrams and trigrams ranked by sublinear
TF-IDF (terms must appear on several pages; redundant sub-phrases are dropped).

## Install

```bash
pip install .            # Python 3.10+
# or for development
pip install -e ".[dev]"
```

## Usage

```bash
# Fetch competitors politely and write brief-output/<keyword>.md and .html
seo-brief build -k "email marketing for small business" \
  -u https://example.com/guide -u https://example.org/post

# URLs from a file (one per line, # comments allowed)
seo-brief build -k "email marketing" --urls-file examples/urls.txt --delay 3

# Work offline from saved HTML files
seo-brief build -k "email marketing" --offline examples/offline-pages -f md,html,json

# Quick comparison table (or --json) without writing a brief
seo-brief analyze -k "email marketing" --offline examples/offline-pages

# Head-to-head: your page vs one competitor (URLs or saved .html files)
seo-brief compare my-draft.html https://example.com/guide --top 20

# Score your draft (Markdown, text or HTML) against the brief for the same competitors
seo-brief check my-draft.md -k "email marketing" --offline examples/offline-pages --min-score 70
```

`compare` matches the H2/H3 outlines of the two pages (question headings are left to the FAQ section)
and reports shared headings, headings only on one page, and the 1-3 word terms (used at least twice)
that both pages share or only one uses, plus a word/heading/link/image comparison. Add `--json` for
machine-readable output.

`check` builds the brief in memory from the same competitor sources as `build` (`-u`, `--urls-file`
or `--offline`) and scores a draft out of 100, with a letter grade and a list of next steps:

| Component | Points | Full marks when |
|---|---|---|
| Outline | 30 | every merged-outline section has a similar H2/H3 in the draft |
| Terms | 25 | the top `--top-terms` (default 20) brief terms appear in the draft (plural-insensitive) |
| Questions | 15 | every competitor question has a matching heading |
| Word count | 15 | the draft is inside the competitor range (partial credit when short or far over) |
| Keyword placement | 15 | the keyword is in the title, the H1, the first 100 words and an H2/H3 |

Components that do not apply (for example, no competitor asks a question) are left out and the score is
rescaled. Markdown drafts (`.md`, `.markdown`, `.txt`) may start with YAML front matter; its `title`
is used, otherwise the first `#` heading. Use `--json` for the full result and `--min-score N` to exit
with status 1 below a threshold, which turns the check into a CI gate for content pull requests.

Options worth knowing:

| Option | Meaning |
|---|---|
| `-u/--url`, `--urls-file` | Competitor URLs you chose |
| `--offline DIR` | Read `*.html` files from a folder instead of fetching |
| `--delay` | Seconds between requests to one host (default 2) |
| `--cache-dir`, `--no-cache` | Disk cache (default `.seo-brief-cache`, 7 day TTL) |
| `--user-agent` | Override the default `seo-brief/x.y (+https://saizul.com ...)` UA |
| `-f/--format` | Any of `md`, `html`, `json` |
| `--front-matter` | Start the Markdown file with a YAML front matter block (title, keyword, date, lang, `draft: true`, word count range, schema suggestions) for Hugo, Jekyll, Astro or CMS importers |
| `-o/--out` | Output directory (default `brief-output`) |
| `--min-score` | `check` only: exit with status 1 when the draft scores below this value |

URLs blocked by `robots.txt`, non-HTML responses, errors and oversized pages are skipped and listed
in the brief. If `robots.txt` cannot be read because of a server error, the host is skipped to be safe.

A sample brief built from the bundled fixtures is in [`examples/output`](examples/output).

## How the main content is found

1. Strip scripts, styles, forms, navigation, footers, sidebars and elements whose class/id looks like
   comments, share widgets, menus or promos.
2. Use the largest `<article>` / `<main>` / `role=main` if it has enough text.
3. Otherwise use a readability-style score: each substantial paragraph votes for its parent and
   grandparent, discounted by link density.

It is a heuristic, not a browser. JavaScript-rendered pages need to be saved (rendered) and analysed
with `--offline`.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

Tests use saved HTML fixtures and a fake HTTP session; nothing touches the network.

## Responsible use

Only analyse pages you are allowed to fetch, keep the delay reasonable, and do not republish
competitor content. The brief contains statistics and short headings, not copied articles.

## License

MIT, see [LICENSE](LICENSE).

## Run with Docker

A multi-arch image (amd64, arm64) is published to GitHub Container Registry on every change to `main`, so you can run the tool without installing Python:

```bash
docker run --rm -v "$PWD:/work" ghcr.io/saizul/seo-content-brief:latest --help
```

Mount the folder that holds your input files (and where reports should be written) at `/work`.
