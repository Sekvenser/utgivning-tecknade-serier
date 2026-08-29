# Development

## Update the index

```
python3 cli.py update
```

Fetches from:
- **Libris** (`libris.kb.se` xsearch API) — comics classified `Hci` (legacy SAB) or `He.05` (newer kssb scheme), published in Sweden (by country *or* language, since neither field alone is reliably filled in), 2020–present. This is the backbone: any comic catalogued by the Swedish national library, including English-language books from Swedish publishers.
- **GrandOcean**'s "På gång" (upcoming/pre-order) and "Nyutkommet" (newly released) shop categories — small-press titles, often ahead of Libris. Also the primary source of cover images and full description text.
- **Libris' own catalogue record** (fetched as JSON-LD from the same identifier xsearch already gives us) — a fallback description source for anything GrandOcean doesn't stock. Many records carry a `summary` (often itself republished from Bokinfo's trade data), which xsearch's flatter API doesn't expose but the full record does.
- **Bokinfo**'s image CDN (`bokinfo.se/Images/Products/Medium/{isbn[:6]}/{isbn}.jpg`) — used as a fallback cover source, keyed directly by ISBN, for any book GrandOcean doesn't stock. Bokinfo is the trade catalog most Swedish booksellers pull their data from, but its actual book-detail pages and API require a professional bookseller/publisher/library login, so only the (public, unauthenticated) cover images are used here.
- **Bokus**' image CDN (`image.bokus.com`) — a second cover fallback, keyed by ISBN, for whatever Bokinfo doesn't have either. The main Bokus site (`www.bokus.com`) sits behind a Vercel bot-protection checkpoint and can't be scraped for text/listings, so each book also gets a generated "Sök på Bokus" search link instead of a direct product link.

Re-running `update` merges new data in: existing `hidden` flags and any fields already filled in are kept, missing fields (e.g. a Libris-only book that GrandOcean also lists) get backfilled.

## Adding a single title from Libris

```
python3 cli.py add-libris https://libris.kb.se/wh5rw3kft0mf0vkc
python3 cli.py add-libris wh5rw3kft0mf0vkc   # a bare id works too
```

For adding one specific book without waiting on/re-running the full `update` scrape — e.g. one that `update`'s query doesn't catch (some children's/juvenile comics are catalogued by Libris under a different classification scheme entirely, keyed by subject rather than form, so they never match our `SAB:Hci`/`He.05` query no matter how it's tuned). Looks the record up via `xsearch?query=onr:<id>` (`onr` = Libris' object number, extracted from the URL) rather than fetching its JSON-LD directly — xsearch already resolves contributor names to clean strings, where the raw JSON-LD record often only links to *other*, unfetched Libris records for each author. Runs through the same `normalize_libris()`/`merge()` pipeline `update` uses, then immediately backfills a cover (Bokinfo, then Bokus) and a description (Libris' own summary) for just that one book. Safe to re-run — a second call updates the existing entry instead of duplicating it. Still needs `python3 cli.py build` afterwards, same as any other command that touches the yaml.

## Fetching exact publication dates

```
pip install playwright && playwright install chromium
python3 cli.py fetch-dates            # all books missing a date
python3 cli.py fetch-dates --limit 50 # just the first 50 (for testing, or to run in smaller batches)
```

None of the sources above expose a day-level publication date — Libris and GrandOcean only ever give a year. Amazon.se product pages do, but the site sits behind an Akamai JS challenge that a plain HTTP request can't get past (Akademibokhandeln and Adlibris were also checked as candidates; both sit behind the same kind of bot-protection checkpoint as Bokus, with no public API either, so they weren't usable). A real headless browser (Playwright + Chromium) executes the challenge automatically, so `fetch-dates` uses that instead of a plain HTTP request. It's roughly 5-10s/book (search + product page + a polite delay) and matches results back to our record by comparing ISBN-13, so a run over the full catalog takes a couple of hours — it's a separate command from `update`, checkpoints its progress every 20 books, and safely skips books that already have a date, so it can be stopped and re-run at any time. Not every book is listed on Amazon.se, so not every book will get a date.

## Other commands

```
python3 cli.py list            # print all books, newest first
python3 cli.py hide <id>       # hide a book from the UI (id = isbn, or the id shown by `list`)
python3 cli.py unhide <id>
python3 cli.py optimize-covers            # convert every non-webp file in data/covers/ to .webp
python3 cli.py optimize-covers <file...>  # convert just the given file(s), e.g. before committing a new cover
```

Books whose publisher mentions "MTM" (Myndigheten för tillgängliga medier, the Swedish agency for accessible/talking-book media) are hidden automatically when first added — they're accessible-media reissues, not original releases. `unhide` still works on them like any other book if you want one visible.

## Building the display json

```
python3 cli.py build
```

The web UI doesn't read the yaml files directly — it fetches `data/books.json`, one flat json array compiled from them. Run `build` after any command that touches the yaml (`update`, `fetch-dates`, `hide`, `unhide`) and before viewing the UI or deploying. This is the command a CI job (e.g. a GitHub Action, on every push that changes `data/books/`) should run to regenerate the deployed json.

`build` also writes one fully pre-rendered static page per book into `data/book/<slug>/index.html` (`slug` is the sanitized book id) — see "Per-book static pages" below — and a sitemap at `data/sitemap.xml` (deployed to `/data/sitemap.xml`, declared in `web/robots.txt`), listing the homepage plus every non-hidden book's page. Hidden books are left out on purpose — no reason to invite crawlers to pages the site itself doesn't link to. Nowhere near it today (~1700 URLs), but `build_sitemap()` in `cli.py` follows the sitemap protocol's 50,000-URL-per-file limit correctly: past that it splits into numbered `sitemap-N.xml` files with `sitemap.xml` becoming a `<sitemapindex>` instead, rather than silently producing one giant invalid file.

## View the UI

```
cd web && python3 -m http.server 8000
```

Then open http://localhost:8000/ — a grid of covers sorted by publication date where known, otherwise by year (newest first), with a search box and a year filter. Clicking a book is a normal link to its own static page (see below), not an in-app view. `web/data` and `web/book` are symlinks to `../data` and `../data/book` so the app's root-absolute paths (`/data/books.json`, `/data/covers/...`) and the per-book pages work whether served locally like this or deployed at a domain root, with no `/web/` in the URL either way (see Deployment below).

## Per-book static pages

The list page (`index.html`/`app.js`) only ever does search/filter/listing. Each book instead gets its own real, separate static page at `data/book/<slug>/` (deployed to `/book/<slug>/`) — plain HTML, no SPA involved, no hash routing, no client-side re-rendering. This matters for two reasons: a client-rendered detail view would show identical `og:image`/title to every share/crawler regardless of which book it's for (crawlers don't execute JS, and hash fragments never reach the server anyway), and it's also just simpler — a book is a page, not a JS-rendered state.

`build_book_pages()` in `cli.py` (run as part of `cli.py build`) generates these: `render_book_detail_html()` is a Python port of the detail markup — kept in sync with `app.js`'s `renderList()`/card behavior by hand, there's no shared template — spliced into a copy of `web/index.html`'s shell (masthead + footer + the cover-zoom modal, all reused as-is; the search/year-filter toolbar is stripped out via the `<!--TOOLBAR_START-->`/`<!--TOOLBAR_END-->` markers, since those controls have no meaning on a single-book page). Book-specific `<title>`/OG/Twitter tags are spliced in between the `<!--BOOK_META_START-->`/`<!--BOOK_META_END-->` markers in that same file. `og:image` is the book's own cover if it has one, else the same default `assets/og-image.png` the homepage uses.

`app.js` itself has no concept of a book-detail route at all — it only renders the list, and links each card straight to `/book/${b.slug}/` (`slug` is precomputed into `data/books.json` by `build_json()`, via the same `book_slug()` helper used for the folder name, so there's one canonical place that computation happens). It's the same `app.js` file on both the list page and every book page, purely so the cover-zoom-modal wiring (the one piece of interactivity a book page needs) is shared — on a book page, `app.js` detects `#app` already has content and skips all the list/fetch/search logic entirely.

Every internal link and asset path in both `web/app.js` and the generated pages is root-absolute (`/data/...`, `/#/...`, `/style.css`, ...) on purpose — these pages live two directories deep (`/book/<slug>/`), unlike `index.html` at the site root, and only root-absolute paths resolve correctly from both places, locally and deployed.

## Deployment

Pushing to `main` runs `.github/workflows/pages.yml`, which regenerates `data/books.json`, `data/sitemap*.xml`, and `data/book/*` (`cli.py build`), assembles a site with `web/`'s contents at the root, `data/books.json` + `data/sitemap*.xml` + `data/covers/` alongside them, and the per-book pages at `book/` (mirroring the local symlink setup, but with real files instead — `data/books/*.yaml` itself isn't published, only the compiled json/sitemap and the generated pages), and deploys it via GitHub Pages. Requires the repo's Pages source set to "GitHub Actions" (Settings → Pages).

The same push also runs `.github/workflows/release.yml`, which creates a GitHub Release tagged `v1.0`, `v1.1`, `v1.2`, ... (minor version bumped by one from whatever the latest existing release is, starting at `v1.0` if there are none yet) with `data/books.json` attached as the release's only artifact. It triggers on `push` rather than `pull_request: closed` deliberately — a `pull_request`-triggered workflow gets a read-only token when the PR is from a fork, which would silently fail to create a release for external contributors.

## Data

Each book is one file under `data/books/<id>.yaml` — the source of truth, meant to be committed to git. Editing, hiding, or updating one book touches only its own file, so a git diff shows exactly what changed instead of a rewrite of one giant array. `python3 cli.py build` compiles all of them into `data/books.json`, which is gitignored (a generated artifact, not source) and is what `web/app.js` actually fetches.

Cover images are downloaded into `data/covers/` during `update` (skipped if already present) so the UI never depends on external image hosts. Covers are kept as `.webp` to save space — `cli.py optimize-covers` converts any `.jpg`/`.png` in `data/covers/` (or specific files you pass it) to `.webp` in place and rewrites the matching `cover_url` in yaml. It doesn't run automatically as part of `update`, since freshly scraped covers are already reasonably-sized jpegs; it exists for the one-time bulk cleanup and for converting hand-added covers before a commit (see README.md's contribution guide). Requires `Pillow`.

Two link fields are hand-curated rather than scraped — add `more_info_url` and/or `buy_url` directly to a book's yaml file (e.g. a homepage or the publisher's own web shop) and they'll show up as "Mer information" / "Köp" links on that book's page after the next `build`. When `buy_url` is set it renders first, as a standout button (it's the recommended way to get the book), above the plain text links.

`render_book_detail_html()` also shows a "Hitta" group of links to five bookstore sites (Bokus, Adlibris, Bokbörsen, Serier & Sånt, Seriekatalogen), computed at build time by `title_search_urls()` from the book's `isbn`/`title` — pure functions of data already in the yaml, so they are never stored as fields and never need backfilling; only `more_info_url`/`buy_url` are hand-curated in the yaml itself.

Requires `PyYAML` and `Pillow` (`pip install -r requirements.txt`).

## Known limitations

- Exact `published_date` is only as complete as the `fetch-dates` command has been run — most books show a year only until then, since no source has day-level dates by default. Amazon.se also just doesn't list every book, so some will never get one.
- Covers come from GrandOcean where available, otherwise Bokinfo by ISBN, otherwise Bokus by ISBN; books with none of the three (no ISBN, or none of the sources has a cover — currently ~129 of 1687) show a text placeholder instead.
- Cover files are named after the book id and never re-downloaded once present — delete a file under `data/covers/` to force a re-fetch on the next `update`.
- Description text comes from GrandOcean where available, otherwise Libris' catalogue record if they exists.