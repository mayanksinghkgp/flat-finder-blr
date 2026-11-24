"""Polite, cached, resumable crawler for NoBroker's public rent and sale search pages.

usage: python nb_crawl.py <city>   -> out/<city>/nb_listings.json
<city> is a key in data/cities.json with a "nobroker" block:
    "nobroker": {"city": "bangalore", "localities": ["koramangala", "hsr_layout"], "max_pages": 30}
Only /flats-for-<rent|sale>-in-<locality>_<city> pages are fetched (allowed by robots.txt); the /api/ paths are
disallowed and never used. If a page looks like a bot check the crawl stops and says so; it never works around one.
"""
import gzip
import hashlib
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

import nb_parse

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / "cache" / "nb"
CITIES = json.loads((ROOT.parent / "data" / "cities.json").read_text(encoding="utf-8"))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
DELAY = 1.0


class Blocked(Exception):
    pass


def fetch(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html.gz")
    if f.exists() and f.stat().st_size > 2000:
        return gzip.decompress(f.read_bytes()).decode("utf-8", "ignore")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
            time.sleep(DELAY)
            if nb_parse.blocked(html):
                raise Blocked(url)
            f.write_bytes(gzip.compress(html.encode("utf-8"), 9))
            return html
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise Blocked(f"{url} (HTTP {e.code})")
            if e.code in (404, 410):  # unknown locality slug
                return None
            print("  retry", attempt + 1, url, e, flush=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print("  retry", attempt + 1, url, e, flush=True)
        time.sleep(5 * (attempt + 1))
    return None


def crawl(city):
    cfg = CITIES[city].get("nobroker")
    if not cfg:
        raise SystemExit(f'{city} has no "nobroker" block in data/cities.json')
    out_dir = ROOT / "out" / city
    out_dir.mkdir(parents=True, exist_ok=True)
    found = {}
    max_pages = cfg.get("max_pages", 30)
    try:
        for loc in cfg["localities"]:
            for deal, parse in (("rent", nb_parse.parse_rent_page), ("sale", nb_parse.parse_sale_page)):
                # sale search pages ignore ?pageNo: further results only come from the disallowed /api/, so stop at page 1
                for n in range(1, (max_pages if deal == "rent" else 1) + 1):
                    url = f"{nb_parse.BASE}/flats-for-{deal}-in-{loc}_{cfg['city']}" + (f"?pageNo={n}" if n > 1 else "")
                    html = fetch(url)
                    listings = parse(html) if html else []
                    new = [l for l in listings if l["id"] not in found]
                    for l in listings:
                        found.setdefault(l["id"], {**l, "searched": loc})
                    print(f"{loc} {deal} page {n}: {len(listings)} listings, {len(new)} new, {len(found)} total", flush=True)
                    if not new:  # past the last page, or the site repeats itself
                        break
    except Blocked as e:
        print("STOPPED: NoBroker served a bot check or refused the request at", e, "- not working around it.", flush=True)
    (out_dir / "nb_listings.json").write_text(json.dumps(list(found.values()), indent=0), encoding="utf-8")
    print("saved", len(found), "listings to", out_dir / "nb_listings.json")


if __name__ == "__main__":
    crawl(next((a for a in sys.argv[1:] if a in CITIES), "koramangala"))
