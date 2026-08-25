# Tecknade serier sedan 2020

Index of Swedish comics & graphic novels published since 2020.

## Update the index

```
python3 cli.py update
```

Fetches from:
- **Libris** (`libris.kb.se` xsearch API) — comics classified `Hci` (legacy SAB) or `He.05` (newer kssb scheme), published in Sweden (by country *or* language, since neither field alone is reliably filled in), 2020–present. This is the backbone: any comic catalogued by the Swedish national library, including English-language books from Swedish publishers.
- **GrandOcean** "På gång" shop category — upcoming/small-press titles, often ahead of Libris. Also a source of cover images and full description text.
- **Bokus**' image CDN (`image.bokus.com`) — used as a fallback cover source, keyed by ISBN, for any book GrandOcean doesn't stock. The main Bokus site (`www.bokus.com`) sits behind a Vercel bot-protection checkpoint and can't be scraped for text/listings, so each book also gets a generated "Sök på Bokus" search link instead of a direct product link.

Re-running `update` merges new data in: existing `hidden` flags and any fields already filled in are kept, missing fields (e.g. a Libris-only book that GrandOcean also lists) get backfilled.

## Other commands

```
python3 cli.py list            # print all books, newest first
python3 cli.py hide <id>       # hide a book from the UI (id = isbn, or the id shown by `list`)
python3 cli.py unhide <id>
```

## View the UI

```
python3 -m http.server 8000
```

Then open http://localhost:8000/web/ — a grid of covers sorted by year (newest first), with a search box, and a detail page per book (description, ISBN, author, publisher, links).

## Data

Everything lives in `data/books.json`, one JSON array — easy to inspect, diff, or edit by hand if needed. Cover images are downloaded into `data/covers/` during `update` (skipped if already present) so the UI never depends on external image hosts.

## Known limitations

- Sort/filter is by **year** only — none of the sources reliably expose a full publication date for these titles.
- Covers come from GrandOcean where available, otherwise Bokus by ISBN; books with neither (no ISBN, or Bokus has no cover either — currently ~77 of 592) show a text placeholder instead.
- Cover files are named after the book id and never re-downloaded once present — delete a file under `data/covers/` to force a re-fetch on the next `update`.
- Description text only exists for GrandOcean-sourced books.
