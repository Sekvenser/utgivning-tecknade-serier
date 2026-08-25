# Tecknade serier sedan 2020

Index of Swedish comics & graphic novels published since 2020.

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
```

Books whose publisher mentions "MTM" (Myndigheten för tillgängliga medier, the Swedish agency for accessible/talking-book media) are hidden automatically when first added — they're accessible-media reissues, not original releases. `unhide` still works on them like any other book if you want one visible.

## Building the display json

```
python3 cli.py build
```

The web UI doesn't read the yaml files directly — it fetches `data/books.json`, one flat json array compiled from them. Run `build` after any command that touches the yaml (`update`, `fetch-dates`, `hide`, `unhide`) and before viewing the UI or deploying. This is the command a CI job (e.g. a GitHub Action, on every push that changes `data/books/`) should run to regenerate the deployed json.

## View the UI

```
cd web && python3 -m http.server 8000
```

Then open http://localhost:8000/ — a grid of covers sorted by publication date where known, otherwise by year (newest first), with a search box, a year filter, and a detail page per book (description, ISBN, author, publisher, exact publication date where known, links). `web/data` is a symlink to `../data` so the app's relative paths (`data/books.json`, `data/covers/...`) work whether served locally like this or deployed at a domain root, with no `/web/` in the URL either way (see Deployment below).

## Deployment

Pushing to `main` runs `.github/workflows/pages.yml`, which regenerates `data/books.json` (`cli.py build`), assembles a site with `web/`'s contents at the root and `data/books.json` + `data/covers/` alongside them (mirroring the local symlink setup, but with real files instead — `data/books/*.yaml` itself isn't published, only the compiled json), and deploys it via GitHub Pages. Requires the repo's Pages source set to "GitHub Actions" (Settings → Pages).

## Data

Each book is one file under `data/books/<id>.yaml` — the source of truth, meant to be committed to git. Editing, hiding, or updating one book touches only its own file, so a git diff shows exactly what changed instead of a rewrite of one giant array. `python3 cli.py build` compiles all of them into `data/books.json`, which is gitignored (a generated artifact, not source) and is what `web/app.js` actually fetches.

Cover images are downloaded into `data/covers/` during `update` (skipped if already present) so the UI never depends on external image hosts.

Requires `PyYAML` (`pip install -r requirements.txt`).

## Known limitations

- Exact `published_date` is only as complete as the `fetch-dates` command has been run — most books show a year only until then, since no source has day-level dates by default. Amazon.se also just doesn't list every book, so some will never get one.
- Covers come from GrandOcean where available, otherwise Bokinfo by ISBN, otherwise Bokus by ISBN; books with none of the three (no ISBN, or none of the sources has a cover — currently ~129 of 1687) show a text placeholder instead.
- Cover files are named after the book id and never re-downloaded once present — delete a file under `data/covers/` to force a re-fetch on the next `update`.
- Description text comes from GrandOcean where available, otherwise Libris' catalogue record; books with neither (currently ~444 of 1688) show no description.
