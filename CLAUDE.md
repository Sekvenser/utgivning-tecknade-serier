# tecknade-serier

Index of Swedish comics & graphic novels published since 2020 (year cutoff: `START_YEAR` in `cli.py`). Static site (`web/`) reading a compiled `data/books.json`, built from per-book yaml files by a Python CLI (`cli.py`). Deployed to GitHub Pages via `.github/workflows/pages.yml`.

Repo: `Sekvenser/utgivning-tecknade-serier`, default branch `main`.

## Docs map

- `README.md` — user-facing manual contribution guide (small press / fanzine publishers adding a book by hand). Swedish.
- `DEVELOPMENT.md` — CLI reference: `update`, `fetch-dates`, `build`, `list`, `hide`/`unhide`, data sources, known limitations.
- This file — orientation for working on the codebase itself.

Read `DEVELOPMENT.md` before touching `cli.py`'s data-fetching logic; it documents *why* each source is scraped the way it is (bot-protection workarounds, field quirks), not just *what* the commands do.

## Architecture

```
data/books/<id>.yaml   source of truth, one file per book, git-tracked
data/covers/           downloaded cover images, git-tracked
data/books.json        compiled from data/books/*.yaml by `cli.py build` — gitignored, NOT source
data/book/<slug>/      one real, fully pre-rendered detail page per book, also from `cli.py build` — gitignored
data/sitemap.xml       also from `cli.py build`; a <sitemapindex> + numbered sitemap-N.xml instead, past 50k URLs
web/                   static site (index.html, app.js, style.css, assets/favicon.ico, robots.txt)
web/data -> ../data    symlink so app.js's root-absolute paths ("/data/books.json", "/data/covers/...")
web/book -> ../data/book    same idea for the per-book pages (see below)
                        all work identically whether served from web/ locally or at a domain root
```

**`data/books.json`, `data/book/*`, and `data/sitemap*.xml` are build artifacts.** Never hand-edit them or treat edits as durable — regenerate with `python3 cli.py build` after touching any yaml, and re-run `build` before checking the UI locally or before it matters for a commit. All are gitignored on purpose; CI rebuilds them fresh on every deploy.

**The sitemap only lists non-hidden books.** `build_sitemap()` skips any book with `hidden: true` — don't surface those to crawlers when the site's own UI deliberately doesn't link to them either. `web/robots.txt` declares its URL (`/data/sitemap.xml`, reusing the `web/data` symlink — no separate plumbing needed) via the standard `Sitemap:` directive.

**A book is a real static page, not an SPA view.** `app.js` has no detail-view/hash-routing concept at all — it only lists/searches/filters, and links each card straight to `/book/<slug>/`. `build_book_pages()` in `cli.py` generates those pages: `render_book_detail_html()` is a Python port of the detail markup (**kept in sync with `app.js` by hand, there's no shared template**), spliced into a copy of `index.html`'s shell — masthead/footer/cover-modal kept, the search/year-filter toolbar stripped via the `<!--TOOLBAR_START/END-->` markers since it has no meaning on a single-book page — with book-specific OG tags spliced in between `<!--BOOK_META_START/END-->`. `app.js` is loaded on both page types purely so the cover-zoom-modal JS is shared; it detects an already-populated `#app` and skips all list logic in that case. Don't reintroduce hash-based book routing (`#/book/<id>`), a `window.BOOK_ID`/hydration bootstrap, or a `renderDetail()` in `app.js` — this was tried and deliberately removed as needless complexity once the static pages became real content instead of redirect stubs. See `DEVELOPMENT.md`'s "Per-book static pages" section.

**Every internal link and asset path is root-absolute** (`/data/...`, `/#/...`, `/style.css`, `/app.js`, `/assets/...`) in both `web/app.js` and the generated pages — required because `/book/<slug>/` pages live two directories deep, unlike `index.html` at the root, and only root-absolute paths resolve correctly from both. Don't reintroduce a bare relative path (`"data/..."`, `href="#/..."`) anywhere in `app.js` or the shared parts of `index.html` — it'll silently 404 or mis-navigate from inside `/book/<slug>/`.

**`slug` in `data/books.json` is computed once**, by `book_slug()` in `cli.py`, and used both for `data/book/<slug>/`'s folder name and for the card links `app.js` generates (`b.slug` is a plain JSON field, not re-derived in JS) — keep it that way rather than porting the sanitization regex into JS a second time.

**Every book field is optional except `id` and `title`** — `web/app.js` falls back gracefully (`"–"`, empty join, etc.) for everything else. `year` should still always be set in practice since it drives sort/filter. See `README.md`'s contribution guide for the exact minimal yaml shape.

**`hidden` is user-controlled state, not a scrape output.** `cli.py update`/`merge()` never flips `hidden` on an existing book — only on first creation (see MTM rule below). Don't add logic that re-hides or re-shows an existing book based on freshly scraped data; that's what `cli.py hide`/`unhide` are for.

## CLI commands (`cli.py`)

- `update` — fetch Libris + GrandOcean (2 categories), backfill covers (Bokinfo then Bokus) and descriptions (Libris JSON-LD), merge into `data/books/*.yaml`.
- `fetch-dates [--limit N]` — Playwright + headless Chromium scrape of Amazon.se for exact `published_date`; slow (~5-10s/book), separate from `update` on purpose, checkpoints every 20 books, safe to stop/resume.
- `build [--json-out PATH]` — compile `data/books/*.yaml` → `data/books.json`, write a real, pre-rendered `data/book/<slug>/index.html` per book (see "Per-book static pages" above), and write `data/sitemap.xml`. Run this after any command that touches yaml.
- `list` — print all books.
- `hide <id>` / `unhide <id>` — toggle visibility of one book.
- `optimize-covers [files...]` — convert `data/covers/*.{jpg,png}` (or specific files) to `.webp` in place, rewriting the matching `cover_url` in yaml. Not run automatically by `update`; exists for the one-off bulk cleanup and for hand-added covers before a commit.

All commands take `--data` (default `data/books`), the yaml directory.

## Known gotchas

- **Bokus, Akademibokhandeln, Adlibris** are behind a shared Vercel bot-protection checkpoint — don't try to scrape their HTML directly, it 429s immediately. Bokus' and Bokinfo's *image* CDNs are the exception (unauthenticated, ISBN-keyed) and are used for cover fallback.
- **Amazon.se** is behind an Akamai JS challenge — only reachable via a real headless browser (Playwright), not plain HTTP. This is why `fetch-dates` exists as a separate, slower command.
- **Bokinfo**'s actual book-detail pages/API require a professional login — off-limits. Only its public image CDN is used.
- **MTM-published books** (`"MTM" in publisher`, Myndigheten för tillgängliga medier / accessible-media reissues) are auto-hidden on creation via `is_auto_hidden_publisher()` in `merge()`. `unhide` still works on them individually.
- Libris' `xsearch` sometimes returns `language` as a list, not a string — already normalized in `normalize_libris`; watch for this pattern if adding new Libris fields.
- A `libris.kb.se/<id>` URL's `<id>` isn't always the `onr` xsearch expects: older records (created before Libris' ~2019 migration to opaque ids) still carry a legacy numeric `controlNumber` as their real `onr`, while the URL uses the newer opaque id — querying `xsearch?query=onr:<opaque-id>` for one of those returns zero results even though the record exists. `resolve_libris_control_number()` fetches the record's JSON-LD (`Accept: application/ld+json`, or you get an HTML bot-check page) and reads its actual `controlNumber` first; `fetch_libris_by_id()` only skips that lookup when the given id is already purely numeric.
- Two GrandOcean categories are scraped ("På gång" *and* "Nyutkommet", category ids `21` and `14`) — deduped by GrandOcean product `Id`, not by ISBN, since a book can appear in both.
- When `fetch-dates` finds an exact date, it also overwrites `year` from that date (a precise source should win over an approximate one) — don't reintroduce a path that sets `year` without checking `published_date` first.
- `.github/workflows/release.yml` (creates a `vX.Y` GitHub Release with `data/books.json` attached on every push to `main`) triggers on `push`, not `pull_request: closed`, on purpose — a `pull_request`-triggered workflow gets a read-only token when the PR is from a fork, which would silently break release creation for external contributors. Keep any future CI touching `main` on the `push` trigger for the same reason.
- `load_store()` coerces `book["id"]`/`book["isbn"]` to `str` right after `yaml.safe_load()` — a hand-written yaml file with an unquoted all-digit id/isbn (e.g. `id: 9789181114843` instead of `id: '9789181114843'`) parses as a YAML int otherwise, which then breaks any code doing string ops on it (this actually happened with two manually-added books). Don't remove that coercion, and don't assume a manually-contributed yaml file has correctly-quoted numeric fields.
- `record_id()` and `title_search_urls()` must use `.get()`, not direct subscripting, for `isbn`/`source_url` — a manually-authored book can legitimately have neither field (only `title`/`id`), and a `record["isbn"]` KeyError there breaks `merge()` for every book that runs after it in the same batch.
- `merge()`'s per-field backfill must stay conditional (`if not existing.get(key) and record.get(key)`) — an unconditional `existing[key] = record.get(key)` writes a stray `key: null` into a manually-authored yaml file whenever both sides are already absent, even though the merge otherwise made no real change.
- The bookstore "Hitta" search links (`title_search_urls()` in `cli.py`) are computed at render time in `render_book_detail_html()`, not stored as yaml fields or passed through `merge()` — they're pure functions of `title`/`isbn`, so persisting them would need a backfill (a self-merge, or a full yaml rewrite) every time the URL pattern for one of the five sites changes. Don't reintroduce `*_search_url` fields into `BOOK_FIELD_ORDER` or `merge()`.
- A book-detail wrapper `<div>` must never carry both a shared class (like `links`) and a more-specific one (`links-buy`) meant to override it — `.links a { color: var(--accent) }` (specificity 0,1,1) beats a same-element `.buy-link { color: var(--bg) }` (0,1,0) regardless of source order, which is how the "Köp" button once rendered as invisible red-on-red text. Keep visually-distinct link groups in CSS-independent wrapper classes.

## Testing changes

There's no test suite. The pattern used throughout this project's history: write a small inline Python snippet importing `cli` to unit-test a function in isolation (e.g. `cli.merge`, `cli.save_store`) against a temp directory before touching real data, `node --check` for `web/app.js` syntax, and serving `web/` locally (`cd web && python3 -m http.server 8000`) to sanity-check HTTP 200s end-to-end. Never run a full `update` or `fetch-dates` speculatively — they hit real external services and `fetch-dates` in particular takes hours; test logic against a handful of items or a temp dir first.
