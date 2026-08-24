#!/usr/bin/env python3
"""CLI to build/update the index of Swedish comics & graphic novels published since 2024.

Sources:
  - Libris (libris.kb.se xsearch API) - authoritative catalog of published books.
    Query: SAB class Hci (tecknade serier) in Swedish, published from 2024 onward.
  - GrandOcean "På gång" shop category - upcoming/small-press titles, often ahead
    of Libris cataloguing. Gives cover image + full description text.

Bokus itself (www.bokus.com) sits behind a Vercel bot-protection checkpoint
(JS challenge) and can't be scraped with a plain HTTP request. Its image CDN
(image.bokus.com) is unprotected though, so it's used as a fallback cover
source for books that GrandOcean doesn't stock. A "view on Bokus" search link
is generated per ISBN regardless.
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

DATA_PATH = "data/books.json"
USER_AGENT = "Mozilla/5.0 (compatible; tecknade-serier-index/1.0)"
GRANDOCEAN_CATEGORY_ID = 21  # "På gång"
# image.bokus.com serves this exact image for any isbn/size it has no cover for.
BOKUS_PLACEHOLDER_MD5 = "1de746945c6a95329b1bf40f9e2992be"


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

def fetch_libris(year_from, year_to):
    records = []
    start = 1
    query = f"SAB:Hci år:{year_from}-{year_to} språk:swe"
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
            records.append(normalize_libris(item))
        if data["to"] >= data["records"]:
            break
        start = data["to"] + 1
    return [r for r in records if r]


def normalize_libris(item):
    isbn = re.sub(r"[^0-9Xx]", "", first(item.get("isbn", "")))
    year = extract_year(item.get("date"))
    if year is not None and year < 2024:
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
        "language": item.get("language", ""),
        "description": "",
        "cover_url": "",
        "source_url": item.get("identifier", ""),
        "sources": ["libris"],
    }


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


def fetch_grandocean(covers_dir, category_id=GRANDOCEAN_CATEGORY_ID):
    summaries = []
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
        summaries.extend(products)
        if len(summaries) >= data.get("amount", 0):
            break
        page += 1

    records = []
    for product in summaries:
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
# Store
# ---------------------------------------------------------------------------

def record_id(record):
    return record["isbn"] if record["isbn"] else \
        f"go:{record['grandocean_id']}" if "grandocean_id" in record else \
        f"libris:{record['source_url'].rsplit('/', 1)[-1]}"


def load_store(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {b["id"]: b for b in json.load(f)}
    except FileNotFoundError:
        return {}


def save_store(path, store):
    books = sorted(store.values(), key=lambda b: (b.get("year") or 0, b["title"]), reverse=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)


def merge(store, new_records):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for record in new_records:
        rid = record_id(record)
        record["id"] = rid
        record["bokus_search_url"] = (
            "https://www.bokus.com/cgi-bin/product_search.cgi?ac_used=no&search_word="
            + urllib.parse.quote(record["isbn"] or record["title"])
        )
        existing = store.get(rid)
        if not existing:
            record["hidden"] = False
            record["added_at"] = now
            store[rid] = record
            continue
        for key in ("title", "publisher", "year", "published", "description"):
            if not existing.get(key) and record.get(key):
                existing[key] = record[key]
        if record.get("cover_url"):  # freshly (re)downloaded, always the best copy we have
            existing["cover_url"] = record["cover_url"]
        existing["authors"] = sorted(set(existing.get("authors", [])) | set(record.get("authors", [])))
        existing["sources"] = sorted(set(existing.get("sources", [])) | set(record.get("sources", [])))
        existing["source_url"] = existing.get("source_url") or record.get("source_url")
        existing["bokus_search_url"] = record["bokus_search_url"]
    return store


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_update(args):
    current_year = datetime.date.today().year
    covers_dir = os.path.join(os.path.dirname(args.data) or ".", "covers")
    store = load_store(args.data)

    print("Fetching Libris...", file=sys.stderr)
    libris_records = fetch_libris(2024, current_year)
    print(f"  {len(libris_records)} records", file=sys.stderr)
    merge(store, libris_records)

    print("Fetching GrandOcean...", file=sys.stderr)
    go_records = fetch_grandocean(covers_dir)
    print(f"  {len(go_records)} records", file=sys.stderr)
    merge(store, go_records)

    print("Fetching Bokus covers for books without one yet...", file=sys.stderr)
    needs_cover = [b for b in store.values() if b.get("isbn") and not b.get("cover_url")]
    found = 0
    for b in needs_cover:
        cover = fetch_bokus_cover(b["isbn"], covers_dir)
        if cover:
            b["cover_url"] = cover
            found += 1
        time.sleep(0.1)  # be polite to the CDN
    print(f"  found {found}/{len(needs_cover)} covers", file=sys.stderr)

    save_store(args.data, store)
    print(f"Saved {len(store)} books to {args.data}", file=sys.stderr)


def cmd_list(args):
    store = load_store(args.data)
    books = sorted(store.values(), key=lambda b: (b.get("year") or 0, b["title"]), reverse=True)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=DATA_PATH, help="path to books.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("update", help="fetch latest data from all sources and merge into the index")

    sub.add_parser("list", help="list all books in the index")

    p_hide = sub.add_parser("hide", help="hide a book from the UI")
    p_hide.add_argument("id", help="book id (isbn, or the id: shown by `list`)")

    p_unhide = sub.add_parser("unhide", help="unhide a book")
    p_unhide.add_argument("id")

    args = parser.parse_args()
    if args.command == "update":
        cmd_update(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "hide":
        cmd_set_hidden(args, True)
    elif args.command == "unhide":
        cmd_set_hidden(args, False)


if __name__ == "__main__":
    main()
