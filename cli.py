#!/usr/bin/env python3
"""CLI to build/update the index of Swedish comics & graphic novels published since 2020.

Sources:
  - Libris (libris.kb.se xsearch API) - authoritative catalog of published books.
    Query: SAB class Hci (tecknade serier) in Swedish, published from START_YEAR onward.
  - GrandOcean "På gång" shop category - upcoming/small-press titles, often ahead
    of Libris cataloguing. Gives cover image + full description text.

Bokus itself (www.bokus.com) sits behind a Vercel bot-protection checkpoint
(JS challenge) and can't be scraped with a plain HTTP request. Its image CDN
(image.bokus.com) is unprotected though, so it's used as a fallback cover
source for books that GrandOcean doesn't stock. A "view on Bokus" search link
is generated per ISBN regardless.

Bokinfo (bokinfo.se) is the trade catalog most Swedish booksellers pull data
from, but its full book-detail pages and API (/sv-SE/artiklar/*,
/api/publications/*) require a professional bookseller/publisher/library
login, so that data is off-limits here. Its cover image CDN
(bokinfo.se/Images/Products/Medium/{isbn[:6]}/{isbn}.jpg) is public and
ISBN-keyed though, so it's used as a second cover fallback.
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

BOOKS_DIR = "data/books"
JSON_OUTPUT_PATH = "data/books.json"
BOOK_PAGES_DIR = "data/book"
SITEMAP_PATH = "data/sitemap.xml"
SITE_URL = "https://serieutgivning.sekvenser.se"
DEFAULT_OG_DESCRIPTION = "Ett register över svenska tecknade serier och serieromaner, utgivna sedan 2020."
START_YEAR = 2020
USER_AGENT = "Mozilla/5.0 (compatible; tecknade-serier-index/1.0)"
GRANDOCEAN_CATEGORY_IDS = [21, 14]  # "På gång" (upcoming), "Nyutkommet" (newly released)
# image.bokus.com serves this exact image for any isbn/size it has no cover for.
BOKUS_PLACEHOLDER_MD5 = "1de746945c6a95329b1bf40f9e2992be"
# bokinfo.se serves this exact image when an isbn's cover folder exists but
# the specific cover doesn't (a genuinely missing isbn just 404s, no download needed).
BOKINFO_PLACEHOLDER_MD5 = "394710781c9de409c97dce605cfff5c9"


def http_get(url, params=None):
    return http_get_bytes(url, params).decode("utf-8", errors="replace")


def http_get_bytes(url, params=None):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def download_cover(url, covers_dir, record_id):
    """Download a cover image next to books.json so the UI needs no external resources."""
    if not url:
        return ""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".jpg"
    filename = re.sub(r"[^A-Za-z0-9_-]", "_", record_id) + ext
    path = os.path.join(covers_dir, filename)
    if not os.path.exists(path):
        os.makedirs(covers_dir, exist_ok=True)
        try:
            with open(path, "wb") as f:
                f.write(http_get_bytes(url))
        except urllib.error.URLError as exc:
            print(f"warning: failed to download cover {url}: {exc}", file=sys.stderr)
            return ""
    return f"covers/{filename}"


def fetch_bokus_cover(isbn, covers_dir):
    filename = f"{isbn}.jpg"
    path = os.path.join(covers_dir, filename)
    if os.path.exists(path):
        return f"covers/{filename}"
    try:
        data = http_get_bytes(f"https://image.bokus.com/images2/{isbn}_766")
    except urllib.error.URLError:
        return ""
    if hashlib.md5(data).hexdigest() == BOKUS_PLACEHOLDER_MD5:
        return ""  # Bokus has no cover for this isbn
    os.makedirs(covers_dir, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return f"covers/{filename}"


def fetch_bokinfo_cover(isbn, covers_dir):
    filename = f"bokinfo_{isbn}.jpg"
    path = os.path.join(covers_dir, filename)
    if os.path.exists(path):
        return f"covers/{filename}"
    try:
        data = http_get_bytes(f"https://www.bokinfo.se/Images/Products/Medium/{isbn[:6]}/{isbn}.jpg")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ""  # no cover folder for this isbn at all
        raise
    except urllib.error.URLError:
        return ""
    if hashlib.md5(data).hexdigest() == BOKINFO_PLACEHOLDER_MD5:
        return ""  # folder exists but no cover for this specific isbn
    os.makedirs(covers_dir, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return f"covers/{filename}"


def first(value):
    """Libris fields are sometimes a string, sometimes a list of variants."""
    if isinstance(value, list):
        for v in value:
            if v:
                return v
        return ""
    return value or ""


def extract_year(*values):
    for value in values:
        for v in value if isinstance(value, list) else [value]:
            m = re.search(r"\b(20\d{2})\b", str(v or ""))
            if m:
                return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Libris
# ---------------------------------------------------------------------------

# "Hci" is the legacy SAB code for comics; "He.05" is the equivalent in the
# newer kssb (SAB 8th ed.) scheme used for more recently catalogued records.
# Neither "språk:swe" nor "land:sw" alone is complete (e.g. a book cataloguers
# marked Swedish-published but English-language, or vice versa), so every
# combination is queried and the results are deduplicated by identifier.
LIBRIS_CLASSIFICATIONS = ["Hci", "He.05"]
LIBRIS_SWEDISH_FILTERS = ["språk:swe", "land:sw"]


def fetch_libris(year_from, year_to):
    items_by_id = {}
    for classification in LIBRIS_CLASSIFICATIONS:
        for swedish_filter in LIBRIS_SWEDISH_FILTERS:
            query = f"SAB:{classification} år:{year_from}-{year_to} {swedish_filter}"
            start = 1
            while True:
                body = http_get(
                    "https://libris.kb.se/xsearch",
                    {"query": query, "format": "json", "n": 200, "start": start},
                )
                data = json.loads(body)["xsearch"]
                items = data["list"]
                if not items:
                    break
                for item in items:
                    items_by_id[item["identifier"]] = item
                if data["to"] >= data["records"]:
                    break
                start = data["to"] + 1
    records = [normalize_libris(item) for item in items_by_id.values()]
    return [r for r in records if r]


def parse_libris_id(url_or_id):
    """Accepts a bare id, or a full libris.kb.se URL in any of its forms
    (with or without "/bib/", trailing slash, or a "?_q=..." query string)."""
    path = urllib.parse.urlparse(url_or_id.strip()).path
    return path.rstrip("/").rsplit("/", 1)[-1]


def resolve_libris_control_number(libris_id):
    """Modern libris.kb.se URLs use an opaque id (e.g. "8sl1vz3l227gzhj") that
    the legacy xsearch API doesn't index -- only the old numeric control
    number does. Fetch the record's JSON-LD (plain HTML otherwise, behind a
    bot-check) and pull the control number out of its "Record" node."""
    req = urllib.request.Request(f"https://libris.kb.se/{libris_id}",
                                  headers={"User-Agent": USER_AGENT, "Accept": "application/ld+json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    for node in data.get("@graph", []):
        if node.get("controlNumber"):
            return node["controlNumber"]
    return None


def fetch_libris_by_id(libris_id):
    """Look up one record directly by its Libris id ("onr" = object number)
    via xsearch, instead of the full JSON-LD record -- xsearch already
    resolves author names to clean strings, where the raw JSON-LD often only
    links to a separate, unfetched record for each contributor."""
    onr = libris_id if libris_id.isdigit() else resolve_libris_control_number(libris_id)
    if not onr:
        return None
    body = http_get("https://libris.kb.se/xsearch", {"query": f"onr:{onr}", "format": "json", "n": 1})
    items = json.loads(body)["xsearch"]["list"]
    return items[0] if items else None


def normalize_libris(item):
    isbn = re.sub(r"[^0-9Xx]", "", first(item.get("isbn", "")))
    year = extract_year(item.get("date"))
    if year is not None and year < START_YEAR:
        return None
    creator = first(item.get("creator"))
    authors = [a.strip() for a in re.split(r"\s*/\s*", creator) if a.strip()]
    publisher = next((p for p in (item.get("publisher") or [""]) if p.strip()), "") \
        if isinstance(item.get("publisher"), list) else (item.get("publisher") or "")
    return {
        "isbn": isbn,
        "title": item.get("title", "").strip(),
        "authors": authors,
        "publisher": publisher.strip(),
        "year": year,
        "published": first(item.get("date")) or "",
        "language": ", ".join(item["language"]) if isinstance(item.get("language"), list) else item.get("language", ""),
        "description": "",
        "cover_url": "",
        "source_url": item.get("identifier", ""),
        "sources": ["libris"],
    }


def fetch_libris_description(source_url):
    """Libris' xsearch API has no description field, but its full catalogue
    record (same identifier, fetched as JSON-LD) often does -- usually
    republished from Bokinfo's trade data. Used to backfill books that
    GrandOcean doesn't stock."""
    req = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT, "Accept": "application/ld+json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    for node in data.get("@graph", []):
        summary = node.get("summary")
        if not summary:
            continue
        label = summary[0].get("label") if isinstance(summary, list) else summary.get("label")
        if isinstance(label, list):
            label = label[0] if label else None
        if label:
            return re.sub(r"\s*\[\w+\]\s*$", "", label).strip()
    return ""


# ---------------------------------------------------------------------------
# GrandOcean
# ---------------------------------------------------------------------------

META_LABELS = {
    "författare": "author",
    "manus": "author",
    "text": "author",
    "teckningar": "author",
    "illustration": "author",
    "illustratör": "author",
    "förlag": "publisher",
    "utgivningsår": "year",
    "isbn": "isbn",
}


def fetch_grandocean(covers_dir, category_ids=GRANDOCEAN_CATEGORY_IDS):
    summaries = {}  # keyed by product Id -- a book can appear in more than one category
    for category_id in category_ids:
        page = 1
        while True:
            body = http_get(
                "https://www.grandocean.se/json/products",
                {"field": "categoryId", "id": category_id, "limit": 50,
                 "page": page, "currencyIso": "SEK"},
            )
            data = json.loads(body)
            products = data.get("products") or []
            if not products:
                break
            for product in products:
                summaries[product["Id"]] = product
            if page * 50 >= data.get("amount", 0):
                break
            page += 1

    records = []
    for product in summaries.values():
        time.sleep(0.2)  # be polite to a small shop's server
        try:
            record = fetch_grandocean_detail(product)
            record["cover_url"] = download_cover(record["cover_url"], covers_dir, record_id(record))
            records.append(record)
        except urllib.error.URLError as exc:
            print(f"warning: failed to fetch {product.get('Title')}: {exc}", file=sys.stderr)
    return records


def fetch_grandocean_detail(product):
    url = "https://www.grandocean.se" + product["Handle"]
    page_html = http_get(url)
    description, fields = parse_grandocean_description(page_html)

    isbn = re.sub(r"[^0-9Xx]", "", fields.get("isbn", "") or product.get("Ean", ""))
    authors = []
    for name in re.split(r"\s*/\s*", fields.get("author", "")):
        name = name.strip()
        if name and name not in authors:
            authors.append(name)
    year = extract_year(fields.get("year"), product.get("DateCreated"))

    image = (product.get("Images") or [""])[0]
    return {
        "isbn": isbn,
        "title": product.get("Title", "").strip(),
        "authors": authors,
        "publisher": fields.get("publisher", "").strip(),
        "year": year,
        "published": fields.get("year", ""),
        "language": "swe",
        "description": description,
        "cover_url": ("https://www.grandocean.se" + image) if image else "",
        "source_url": url,
        "sources": ["grandocean"],
        "grandocean_id": product.get("Id"),
    }


def parse_grandocean_description(page_html):
    m = re.search(
        r'id="tabs-pane1".*?<div class="ck-content"[^>]*>(.*?)</div>\s*</div>',
        page_html, re.S,
    )
    block = m.group(1) if m else ""

    paragraphs = []
    for p in re.findall(r"<p>(.*?)</p>", block, re.S):
        p = re.sub(r"<br\s*/?>", "\n", p)
        p = re.sub(r"<[^>]+>", "", p)
        p = html.unescape(p).strip()
        if p:
            paragraphs.append(p)

    meta_para = None
    desc_paragraphs = []
    for p in paragraphs:
        if "ISBN" in p.upper() and ":" in p:
            meta_para = p
        else:
            desc_paragraphs.append(p)

    fields = {}
    if meta_para:
        for line in meta_para.split("\n"):
            if ":" not in line:
                continue
            label, value = line.split(":", 1)
            key = META_LABELS.get(label.strip().lower())
            if not key:
                continue
            value = value.strip()
            if key == "author" and key in fields:
                fields[key] = fields[key] + " / " + value
            else:
                fields[key] = value

    return "\n\n".join(desc_paragraphs), fields


# ---------------------------------------------------------------------------
# Amazon.se (exact publication dates)
# ---------------------------------------------------------------------------
#
# None of our other sources expose a day-level publication date (Libris and
# GrandOcean only ever give a year). Amazon.se product pages do, in a
# "Produktinformation" bullet list, but the site sits behind an Akamai
# JS challenge that a plain HTTP request can't get past (it silently returns
# an interstitial page instead of a 403, so it's not obvious from a status
# code alone). A real, JS-executing browser (Playwright + headless Chromium)
# solves the challenge automatically, so that's what this uses -- see the
# `fetch-dates` command, kept separate from `update` because it's an order
# of magnitude slower and Amazon-specific.

AMAZON_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
AMAZON_MONTHS_SV = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6,
    "juli": 7, "augusti": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
}
AMAZON_DETAIL_LIST_RE = re.compile(
    r'<ul class="a-unordered-list a-nostyle a-vertical a-spacing-none detail-bullet-list">(.*?)</ul>', re.S)
AMAZON_DETAIL_ITEM_RE = re.compile(
    r'<li><span class="a-list-item">\s*<span class="a-text-bold">(.*?)</span>\s*<span>(.*?)</span>\s*</span></li>', re.S)


def parse_swedish_date(text):
    m = re.match(r"(\d{1,2})\s+([A-Za-zÅÄÖåäö]+)\s+(\d{4})", text.strip())
    if not m:
        return None
    day, month_name, year = m.groups()
    month = AMAZON_MONTHS_SV.get(month_name.lower())
    if not month:
        return None
    return f"{year}-{month:02d}-{int(day):02d}"


def parse_amazon_detail_bullets(detail_html):
    list_match = AMAZON_DETAIL_LIST_RE.search(detail_html)
    if not list_match:
        return {}
    fields = {}
    for label_raw, value_raw in AMAZON_DETAIL_ITEM_RE.findall(list_match.group(1)):
        label = re.sub(r"[‎‏:]|&rlm;|&lrm;", "", label_raw).strip().lower()
        value = html.unescape(re.sub(r"<[^>]+>", "", value_raw)).strip()
        if "utgivare" in label:
            fields["publisher"] = value
        elif "publiceringsdatum" in label:
            fields["published_raw"] = value
        elif "isbn-13" in label:
            fields["isbn13"] = value
    return fields


def amazon_goto(page, url):
    """Navigate and give an Akamai JS challenge (if served) time to resolve."""
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    if "akam-logo" in page.content() or not page.title().strip():
        page.wait_for_timeout(6000)
    return page.content()


def fetch_amazon_publication_date(page, isbn):
    target_isbn13 = re.sub(r"[^0-9]", "", isbn)
    search_html = amazon_goto(page, f"https://www.amazon.se/s?k={isbn}")

    asins = []
    for m in re.finditer(r'href="/[^"]*?/dp/([A-Z0-9]{10})[^"]*"', search_html):
        if m.group(1) not in asins:
            asins.append(m.group(1))
        if len(asins) >= 3:  # bound the cost of a wrong/ambiguous search match
            break

    for asin in asins:
        detail_html = amazon_goto(page, f"https://www.amazon.se/dp/{asin}/")
        fields = parse_amazon_detail_bullets(detail_html)
        if re.sub(r"[^0-9]", "", fields.get("isbn13", "")) == target_isbn13:
            return parse_swedish_date(fields.get("published_raw", ""))
    return None


# ---------------------------------------------------------------------------
# Store -- one yaml file per book (data/books/<id>.yaml) is the source of
# truth, so a single edit (e.g. hiding a book) is a small git diff to one
# file instead of a rewrite of one giant json array. `build_json` compiles
# them into data/books.json, the flat file the web UI actually fetches --
# see the `build` command, meant to be run in CI/a GitHub Action after the
# yaml files are updated.
# ---------------------------------------------------------------------------

BOOK_FIELD_ORDER = [
    "id", "isbn", "title", "authors", "publisher", "year", "published", "published_date",
    "language", "description", "cover_url", "source_url",
    "more_info_url", "buy_url",  # optional, hand-curated -- not filled in by any scraper
    "sources", "grandocean_id", "hidden", "added_at",
]


def record_id(record):
    if record.get("isbn"):
        return record["isbn"]
    if "grandocean_id" in record:
        return f"go:{record['grandocean_id']}"
    if record.get("source_url"):
        return f"libris:{record['source_url'].rsplit('/', 1)[-1]}"
    return record["id"]  # a manually-authored book with none of the above -- keep its own id as-is


def book_slug(book_id):
    """Filesystem/URL-safe id, used both for data/books/<slug>.yaml and for
    the deployed /book/<slug>/ page -- one canonical place to compute it."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", book_id)


def book_filename(book_id):
    return book_slug(book_id) + ".yaml"


def ordered_book(book):
    ordered = {k: book[k] for k in BOOK_FIELD_ORDER if k in book}
    ordered.update((k, v) for k, v in book.items() if k not in ordered)
    return ordered


def load_store(books_dir):
    store = {}
    if not os.path.isdir(books_dir):
        return store
    for name in sorted(os.listdir(books_dir)):
        if not name.endswith(".yaml"):
            continue
        with open(os.path.join(books_dir, name), encoding="utf-8") as f:
            book = yaml.safe_load(f)
        # A hand-written yaml file's id/isbn can come out as a YAML int if left
        # unquoted (e.g. "id: 9789181114843") -- string ops throughout assume str.
        book["id"] = str(book["id"])
        if book.get("isbn") is not None:
            book["isbn"] = str(book["isbn"])
        store[book["id"]] = book
    return store


def save_store(books_dir, store):
    os.makedirs(books_dir, exist_ok=True)
    for book in store.values():
        path = os.path.join(books_dir, book_filename(book["id"]))
        content = yaml.safe_dump(ordered_book(book), allow_unicode=True, sort_keys=False, width=100)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if f.read() == content:
                    continue  # unchanged -- skip the write, keeps git diffs to books that actually changed
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


def build_json(books_dir, json_path):
    store = load_store(books_dir)
    for book in store.values():
        book["slug"] = book_slug(book["id"])  # so app.js can link straight to /book/<slug>/
    books = sorted(store.values(),
                   key=lambda b: (b.get("year") or 0, b.get("published_date") or "", b["title"]),
                   reverse=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)


# --- Per-book static pages -------------------------------------------------
#
# Each book gets a real, fully pre-rendered page at data/book/<slug>/ (deployed
# to /book/<slug>/) -- not a client-rendered SPA view and not a redirect stub.
# The list page (index.html/app.js) only ever does search/filter/listing and
# links straight to these; app.js has no concept of a "book detail route".
#
# render_book_detail_html() is a Python port of web/app.js's renderList()-
# adjacent detail markup -- there is no shared template between the two, so
# keep them in sync by hand when either changes.
#
# Every internal link and asset path in both this template and app.js is
# root-absolute (e.g. "/data/...", "/#/...") on purpose: these pages live two
# directories deep (/book/<slug>/), unlike index.html at the site root, and
# only root-absolute paths resolve correctly from both places.

def truncate_description(text, limit=200):
    text = " ".join((text or DEFAULT_OG_DESCRIPTION).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


SWEDISH_MONTHS = ["januari", "februari", "mars", "april", "maj", "juni",
                  "juli", "augusti", "september", "oktober", "november", "december"]


def format_date_sv(iso_date):
    year, month, day = iso_date.split("-")
    return f"{int(day)} {SWEDISH_MONTHS[int(month) - 1]} {year}"


def format_language_sv(language):
    if not language:
        return ""
    return ", ".join(LANGUAGE_LABELS.get(code.strip(), code.strip()) for code in language.split(","))


LANGUAGE_LABELS = {  # mirror of web/app.js's LANGUAGE_LABELS
    "swe": "Svenska", "eng": "Engelska", "nor": "Norska", "dan": "Danska", "fin": "Finska",
    "dut": "Nederländska", "fre": "Franska", "ger": "Tyska", "spa": "Spanska", "ita": "Italienska",
    "cze": "Tjeckiska", "ara": "Arabiska", "sme": "Nordsamiska",
}


def source_label_sv(source):
    return {"libris": "Libris", "grandocean": "GrandOcean"}.get(source, source)


def cover_src(cover_url):
    return f"/data/{cover_url}" if cover_url else ""


# This markup has no JS equivalent (app.js never renders a book detail view) --
# it only needs to be kept in sync with itself if the ad copy/design changes.
AD_SLOT_HTML = """<aside class="ad-slot" id="ad-slot" aria-label="Annonsplats">
        <div class="ad-label">Annonser</div>
        <a class="ad-unit" href="https://sekvenser.se" target="_blank" rel="noopener">
          <img src="/assets/blurb-news-cropped.png" alt="Sekvenser">
          <p>Sekvenser 2&ndash;3 ute nu. Sveriges enda oberoende tidskrift om tecknade serier och sekventiell konst. Köp den på sekvenser.se</p>
        </a>
        <a class="ad-unit ad-unit-text" href="mailto:mikkeschiren@gmail.com">
          Vill du annonsera här? Kontakta mikkeschiren@gmail.com
        </a>
      </aside>"""


def render_book_detail_html(book):
    """The only place a book's detail markup is rendered -- app.js has no
    equivalent (it never renders a book detail view; see build_book_pages)."""
    # buy_url is the recommended place to buy the book (typically the
    # publisher's own shop) -- shown first and styled to stand out from the
    # plain-text links below, which are either informational or just search
    # links to general marketplaces/used-book sites.
    buy_html = ""
    if book.get("buy_url"):
        buy_html = (f'<div class="links-buy"><a class="buy-link" href="{html.escape(book["buy_url"])}" '
                    f'target="_blank" rel="noopener">Köp</a></div>')

    links = []
    if book.get("more_info_url"):
        links.append(f'<a href="{html.escape(book["more_info_url"])}" target="_blank" rel="noopener">Mer information</a>')
    if book.get("source_url"):
        sources = ", ".join(source_label_sv(s) for s in book.get("sources") or [])
        links.append(f'<a href="{html.escape(book["source_url"])}" target="_blank" rel="noopener">'
                      f'Källa ({html.escape(sources)})</a>')

    # Kept on its own line, separate from `links` above: automated per-store
    # search links, not curated/verified the way more_info_url/buy_url are.
    # Always all five, since they're pure functions of title/isbn.
    search_urls = title_search_urls(book)
    other_links = [
        f'<a href="{html.escape(search_urls[field])}" target="_blank" rel="noopener">{label}</a>'
        for field, label in [
            ("bokus_search_url", "Bokus"),
            ("adlibris_search_url", "Adlibris"),
            ("bokborsen_search_url", "Bokbörsen"),
            ("seriersant_search_url", "Serier & Sånt"),
            ("seriekatalogen_search_url", "Seriekatalogen"),
        ]
    ]

    if book.get("cover_url"):
        src = html.escape(cover_src(book["cover_url"]))
        cover_html = (f'<div class="cover" role="button" tabindex="0" aria-label="Visa omslag i fullstorlek" '
                      f'data-cover="{src}"><img src="{src}" alt=""></div>')
    else:
        cover_html = f'<div class="cover">{html.escape(book["title"])}</div>'

    if book.get("published_date"):
        published = format_date_sv(book["published_date"])
    else:
        published = book.get("published") or str(book.get("year") or "") or "–"

    description_html = (f'<div class="description">{html.escape(book["description"])}</div>'
                         if book.get("description")
                         else '<p class="empty">Ingen textinformation tillgänglig.</p>')

    return f"""<a class="back" href="/#/">&larr; Tillbaka</a>
    <div class="detail-layout">
      <div class="detail">
        <div class="detail-head">
          {cover_html}
          <div>
            <h2>{html.escape(book['title'])}</h2>
            <dl>
              <dt>Upphovsperson</dt><dd>{html.escape(", ".join(book.get("authors") or []) or "–")}</dd>
              <dt>Förlag</dt><dd>{html.escape(book.get("publisher") or "–")}</dd>
              <dt>Utgiven</dt><dd>{html.escape(published or "–")}</dd>
              <dt>ISBN</dt><dd>{html.escape(book.get("isbn") or "–")}</dd>
              <dt>Språk</dt><dd>{html.escape(format_language_sv(book.get("language")) or "–")}</dd>
            </dl>
            {buy_html}
            <div class="links">{" ".join(links)}</div>
            {f'<div class="links-other"><span class="links-other-label">Hitta</span>{" ".join(other_links)}</div>' if other_links else ""}
          </div>
        </div>
        {description_html}
      </div>
      {AD_SLOT_HTML}
    </div>"""


BOOK_META_TEMPLATE = """<title>{title}</title>
<meta name="description" content="{description}">

<meta property="og:type" content="book">
<meta property="og:site_name" content="Svenska tecknade serier">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical_url}">
<meta property="og:image" content="{image_url}">
{image_dims}<meta property="og:locale" content="sv_SE">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{image_url}">"""


def build_book_pages(books_dir, pages_dir, template_path="web/index.html", site_url=SITE_URL):
    with open(template_path, encoding="utf-8") as f:
        template = f.read()
    if ("<!--BOOK_META_START-->" not in template or '<main id="app"></main>' not in template
            or "<!--TOOLBAR_START-->" not in template):
        raise ValueError(f"{template_path} is missing an expected BOOK_META/#app/TOOLBAR marker")

    # A single book page has no list to filter, so it doesn't need the
    # search box / year picker -- drop them, keeping the rest of the header.
    template = re.sub(r"<!--TOOLBAR_START-->.*?<!--TOOLBAR_END-->", "", template, flags=re.S)

    store = load_store(books_dir)
    for book in store.values():
        slug = book_slug(book["id"])

        if book.get("cover_url"):
            image_url = f"{site_url}{cover_src(book['cover_url'])}"
            image_dims = ""  # cover dimensions vary per book; omitting is valid per the OG spec
        else:
            image_url = f"{site_url}/assets/og-image.png"
            image_dims = ('<meta property="og:image:width" content="1200">\n'
                          '<meta property="og:image:height" content="630">\n')
        meta = BOOK_META_TEMPLATE.format(
            title=html.escape(f"{book['title']} – Svenska tecknade serier"),
            description=html.escape(truncate_description(book.get("description"))),
            canonical_url=html.escape(f"{site_url}/book/{slug}/"),
            image_url=html.escape(image_url),
            image_dims=image_dims,
        )

        page = re.sub(r"<!--BOOK_META_START-->.*?<!--BOOK_META_END-->", meta, template, flags=re.S)
        page = page.replace('<main id="app"></main>', f'<main id="app">{render_book_detail_html(book)}</main>')

        page_dir = os.path.join(pages_dir, slug)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)


# sitemaps.org protocol: max 50,000 <url> entries (and 50MB uncompressed) per
# sitemap file. Nowhere near that today (~1700 books), but if it's ever
# exceeded this splits into numbered sitemap-N.xml files plus a <sitemapindex>
# written to the usual sitemap.xml path, instead of producing an invalid file.
SITEMAP_MAX_URLS = 50000


def _write_urlset(path, urls):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{html.escape(loc)}</loc>")
        if lastmod:
            lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append("  </url>")
    lines.append("</urlset>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def build_sitemap(books_dir, sitemap_path, site_url=SITE_URL):
    store = load_store(books_dir)
    urls = [(f"{site_url}/", None)]
    for book in store.values():
        if book.get("hidden"):
            continue  # hidden from the site itself -- don't invite crawlers to it either
        urls.append((f"{site_url}/book/{book_slug(book['id'])}/", (book.get("added_at") or "")[:10] or None))

    chunks = [urls[i:i + SITEMAP_MAX_URLS] for i in range(0, len(urls), SITEMAP_MAX_URLS)]
    out_dir = os.path.dirname(sitemap_path) or "."
    os.makedirs(out_dir, exist_ok=True)

    if len(chunks) == 1:
        _write_urlset(sitemap_path, chunks[0])
        return

    sitemap_names = []
    for i, chunk in enumerate(chunks, 1):
        name = f"sitemap-{i}.xml"
        _write_urlset(os.path.join(out_dir, name), chunk)
        sitemap_names.append(name)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for name in sitemap_names:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{html.escape(site_url)}/data/{name}</loc>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# MTM (Myndigheten för tillgängliga medier) editions are talking-book /
# accessible-media reissues, not original comics releases -- hidden by
# default. Publisher text varies ("Inläst för Myndigheten för tillgängliga
# medier, MTM", "Produced by Swedish Agency for Accessible Media, MTM",
# plain "MTM", ...) but "MTM" itself is a reliable, consistent marker.
def is_auto_hidden_publisher(publisher):
    return "MTM" in (publisher or "")


def merge(store, new_records):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for record in new_records:
        rid = record_id(record)
        record["id"] = rid
        existing = store.get(rid)
        if not existing:
            record["hidden"] = is_auto_hidden_publisher(record.get("publisher"))
            record["added_at"] = now
            store[rid] = record
            continue
        for key in ("title", "publisher", "year", "published", "description", "source_url"):
            if not existing.get(key) and record.get(key):
                existing[key] = record[key]
        if record.get("cover_url"):  # freshly (re)downloaded, always the best copy we have
            existing["cover_url"] = record["cover_url"]
        existing["authors"] = sorted(set(existing.get("authors", [])) | set(record.get("authors", [])))
        existing["sources"] = sorted(set(existing.get("sources", [])) | set(record.get("sources", [])))
    return store


# Automated per-store search links for a book detail page -- pure functions of
# title/isbn, computed at render time so they're never stale and never stored.
def title_search_urls(book):
    q = urllib.parse.quote(book.get("isbn") or book["title"])
    qt = urllib.parse.quote(book["title"])
    qt_plus = urllib.parse.quote_plus(book["title"])
    q_plus = urllib.parse.quote_plus(book.get("isbn") or book["title"])
    return {
        "bokus_search_url": f"https://www.bokus.com/cgi-bin/product_search.cgi?ac_used=no&search_word={q}",
        "adlibris_search_url": f"https://www.adlibris.com/sv/sok?q={qt}",
        "bokborsen_search_url": f"https://www.bokborsen.se/?g=0&c=0&q={qt_plus}&qa=&qt=&qi=&qs=&f=1&fi=&fd=&pb=&_s=created_at&_d=desc",
        "seriersant_search_url": f"https://seriersant.se/?s={q_plus}&post_type=product&dgwt_wcas=1",
        "seriekatalogen_search_url": f"https://www.seriekatalogen.se/?q={qt_plus}&page=1",
    }


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def fetch_field_with_progress(items, label, field, fetch_fn, every=50):
    """Run fetch_fn(book) over items, storing non-empty results into book[field],
    printing progress every `every` books so a long update doesn't look stalled."""
    found = 0
    total = len(items)
    for i, b in enumerate(items, 1):
        try:
            value = fetch_fn(b)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"warning: failed to fetch {label} for {b['id']}: {exc}", file=sys.stderr)
            value = ""
        if value:
            b[field] = value
            found += 1
        if i % every == 0 or i == total:
            print(f"  {i}/{total} processed, {found} found so far", file=sys.stderr)
        time.sleep(0.1)  # be polite to the source
    return found


def cmd_update(args):
    # +1 year so already-announced titles for next year (publishers typically
    # announce roughly a year ahead) aren't excluded by the query itself.
    year_to = datetime.date.today().year + 1
    covers_dir = os.path.join(os.path.dirname(args.data) or ".", "covers")
    store = load_store(args.data)

    print("Fetching Libris...", file=sys.stderr)
    libris_records = fetch_libris(START_YEAR, year_to)
    print(f"  {len(libris_records)} records", file=sys.stderr)
    merge(store, libris_records)

    print("Fetching GrandOcean...", file=sys.stderr)
    go_records = fetch_grandocean(covers_dir)
    print(f"  {len(go_records)} records", file=sys.stderr)
    merge(store, go_records)

    print("Fetching Bokinfo covers for books without one yet...", file=sys.stderr)
    needs_cover = [b for b in store.values() if b.get("isbn") and not b.get("cover_url")]
    found = fetch_field_with_progress(
        needs_cover, "bokinfo cover", "cover_url",
        lambda b: fetch_bokinfo_cover(b["isbn"], covers_dir))
    print(f"  found {found}/{len(needs_cover)} covers", file=sys.stderr)

    print("Fetching Bokus covers for books still without one...", file=sys.stderr)
    needs_cover = [b for b in store.values() if b.get("isbn") and not b.get("cover_url")]
    found = fetch_field_with_progress(
        needs_cover, "bokus cover", "cover_url",
        lambda b: fetch_bokus_cover(b["isbn"], covers_dir))
    print(f"  found {found}/{len(needs_cover)} covers", file=sys.stderr)

    print("Fetching Libris descriptions for books without one yet...", file=sys.stderr)
    needs_description = [b for b in store.values() if "libris" in b.get("sources", []) and not b.get("description")]
    found = fetch_field_with_progress(
        needs_description, "libris description", "description",
        lambda b: fetch_libris_description(b["source_url"]))
    print(f"  found {found}/{len(needs_description)} descriptions", file=sys.stderr)

    save_store(args.data, store)
    print(f"Saved {len(store)} books to {args.data}", file=sys.stderr)
    print("Run `python3 cli.py build` to refresh data/books.json for the UI.", file=sys.stderr)


def cmd_fetch_dates(args):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("This command needs Playwright: pip install playwright && playwright install chromium",
              file=sys.stderr)
        sys.exit(1)

    store = load_store(args.data)
    needs_date = [b for b in store.values() if b.get("isbn") and not b.get("published_date")]
    if args.limit:
        needs_date = needs_date[:args.limit]
    print(f"Fetching publication dates for {len(needs_date)} books from amazon.se "
          f"(slow: ~5-10s/book)...", file=sys.stderr)

    found = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=AMAZON_USER_AGENT, locale="sv-SE")
        try:
            for i, b in enumerate(needs_date, 1):
                try:
                    date_iso = fetch_amazon_publication_date(page, b["isbn"])
                except Exception as exc:
                    print(f"warning: failed on {b['isbn']} ({b['title']}): {exc}", file=sys.stderr)
                    date_iso = None
                if date_iso:
                    b["published_date"] = date_iso
                    b["year"] = int(date_iso[:4])  # Amazon's exact date outranks a source's rougher year guess
                    found += 1
                if i % 20 == 0:
                    save_store(args.data, store)
                    print(f"  {i}/{len(needs_date)} processed, {found} dates found so far", file=sys.stderr)
                time.sleep(1.5)  # be polite / reduce block risk
        finally:
            browser.close()

    save_store(args.data, store)
    print(f"Done: found {found}/{len(needs_date)} publication dates", file=sys.stderr)
    print("Run `python3 cli.py build` to refresh data/books.json for the UI.", file=sys.stderr)


def cmd_add_libris(args):
    libris_id = parse_libris_id(args.url_or_id)
    item = fetch_libris_by_id(libris_id)
    if not item:
        print(f"No Libris record found for '{args.url_or_id}' (onr:{libris_id})", file=sys.stderr)
        sys.exit(1)

    record = normalize_libris(item)
    if not record:
        print(f"Found '{item.get('title')}' but it's from before {START_YEAR} (the index's cutoff year) "
              f"-- add it by hand in data/books/ if you still want it (see README.md).", file=sys.stderr)
        sys.exit(1)

    covers_dir = os.path.join(os.path.dirname(args.data) or ".", "covers")
    store = load_store(args.data)
    is_new = record_id(record) not in store
    merge(store, [record])
    book = store[record_id(record)]

    if not book.get("cover_url") and book.get("isbn"):
        book["cover_url"] = fetch_bokinfo_cover(book["isbn"], covers_dir) or fetch_bokus_cover(book["isbn"], covers_dir)
    if not book.get("description") and "libris" in book.get("sources", []):
        try:
            book["description"] = fetch_libris_description(book["source_url"])
        except (urllib.error.URLError, json.JSONDecodeError):
            pass

    save_store(args.data, store)
    print(f"{'Added' if is_new else 'Updated'} '{book['title']}' ({book['id']})", file=sys.stderr)
    print("Run `python3 cli.py build` to refresh data/books.json for the UI.", file=sys.stderr)


def cmd_list(args):
    store = load_store(args.data)
    books = sorted(store.values(),
                   key=lambda b: (b.get("year") or 0, b.get("published_date") or "", b["title"]),
                   reverse=True)
    for b in books:
        flag = "HIDDEN" if b.get("hidden") else "      "
        print(f"{flag}  {b.get('year') or '????'}  {b['id']:<16}  {b['title']} — {', '.join(b.get('authors') or [])}")


def cmd_set_hidden(args, hidden):
    store = load_store(args.data)
    if args.id not in store:
        print(f"No book with id {args.id!r}", file=sys.stderr)
        sys.exit(1)
    store[args.id]["hidden"] = hidden
    save_store(args.data, store)
    print(f"{'Hid' if hidden else 'Unhid'} {store[args.id]['title']}")
    print("Run `python3 cli.py build` to refresh data/books.json for the UI.", file=sys.stderr)


COVER_WEBP_QUALITY = 82


def convert_cover_to_webp(path):
    """Convert one cover image in place to .webp. Returns the new file's
    basename, or None if `path` was already .webp."""
    if os.path.splitext(path)[1].lower() == ".webp":
        return None
    from PIL import Image
    img = Image.open(path)
    img = img.convert("RGBA" if img.mode in ("P", "RGBA", "LA") else "RGB")
    new_path = os.path.splitext(path)[0] + ".webp"
    img.save(new_path, "WEBP", quality=COVER_WEBP_QUALITY, method=6)
    os.remove(path)
    return os.path.basename(new_path)


def cmd_optimize_covers(args):
    """Convert cover images to .webp -- run with no arguments to sweep every
    existing jpg/png in data/covers/, or pass specific file paths to convert
    just-added covers before committing them."""
    covers_dir = os.path.join(os.path.dirname(args.data) or ".", "covers")
    if args.files:
        targets = args.files
    elif os.path.isdir(covers_dir):
        targets = sorted(os.path.join(covers_dir, n) for n in os.listdir(covers_dir)
                          if os.path.splitext(n)[1].lower() in (".jpg", ".jpeg", ".png"))
    else:
        targets = []

    store = load_store(args.data)
    by_cover_filename = {}
    for book in store.values():
        if book.get("cover_url"):
            by_cover_filename.setdefault(os.path.basename(book["cover_url"]), []).append(book)

    converted = 0
    for path in targets:
        old_name = os.path.basename(path)
        new_name = convert_cover_to_webp(path)
        if not new_name:
            continue
        converted += 1
        for book in by_cover_filename.get(old_name, []):
            book["cover_url"] = f"covers/{new_name}"

    save_store(args.data, store)
    print(f"Converted {converted} cover(s) to webp.")
    if converted:
        print("Run `python3 cli.py build` to refresh data/books.json for the UI.", file=sys.stderr)


def cmd_build(args):
    build_json(args.data, args.json_out)
    print(f"Wrote {args.json_out}", file=sys.stderr)
    build_book_pages(args.data, BOOK_PAGES_DIR)
    print(f"Wrote per-book pages to {BOOK_PAGES_DIR}", file=sys.stderr)
    build_sitemap(args.data, SITEMAP_PATH)
    print(f"Wrote {SITEMAP_PATH}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=BOOKS_DIR, help="path to the per-book yaml directory")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("update", help="fetch latest data from all sources and merge into the index")

    p_add = sub.add_parser("add-libris",
        help="fetch a single book from Libris by URL or bare id and add/update it in the index")
    p_add.add_argument("url_or_id", help="e.g. https://libris.kb.se/wh5rw3kft0mf0vkc or just wh5rw3kft0mf0vkc")

    p_dates = sub.add_parser("fetch-dates",
        help="scrape exact publication dates from amazon.se (slow, needs playwright; run separately from update)")
    p_dates.add_argument("--limit", type=int, default=None, help="max number of books to process this run")

    p_build = sub.add_parser("build",
        help="compile the per-book yaml files into data/books.json for the web UI (run this in CI after editing yaml)")
    p_build.add_argument("--json-out", default=JSON_OUTPUT_PATH, help="path to write the combined json file")

    p_covers = sub.add_parser("optimize-covers",
        help="convert cover images to .webp (no args: sweep all of data/covers/; or pass specific files)")
    p_covers.add_argument("files", nargs="*", help="specific cover file(s) to convert, e.g. before committing")

    sub.add_parser("list", help="list all books in the index")

    p_hide = sub.add_parser("hide", help="hide a book from the UI")
    p_hide.add_argument("id", help="book id (isbn, or the id: shown by `list`)")

    p_unhide = sub.add_parser("unhide", help="unhide a book")
    p_unhide.add_argument("id")

    args = parser.parse_args()
    if args.command == "update":
        cmd_update(args)
    elif args.command == "add-libris":
        cmd_add_libris(args)
    elif args.command == "fetch-dates":
        cmd_fetch_dates(args)
    elif args.command == "build":
        cmd_build(args)
    elif args.command == "optimize-covers":
        cmd_optimize_covers(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "hide":
        cmd_set_hidden(args, True)
    elif args.command == "unhide":
        cmd_set_hidden(args, False)


if __name__ == "__main__":
    main()
