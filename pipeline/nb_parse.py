"""Parse NoBroker public search pages (rent and sale) into listings.

Rent pages carry each listing as schema.org JSON-LD (`Apartment` with rent, deposit, geo).
Sale pages carry each listing as an HTML card with schema.org microdata (price, geo) and a built-up area.
Only public SEO search pages are parsed; NoBroker's /api/ paths are disallowed by robots.txt and never used.
Owner names and phone numbers on the page are ignored and never stored.
"""
import html as H
import json
import re

BASE = "https://www.nobroker.in"
TITLE = re.compile(r"^\s*(?:(\d+)\+?\s*BHK|(\d+)\s*RK)\s+(.+?)(?:\s+In\s+(.+?))?\s+For\s+(Rent|Sale|Lease)\b(?:\s+In\s+(.+?))?\s*$", re.I)


def _num(v):
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_title(title):
    """'3 BHK Flat In Vandana Elite, Koramangala for Rent  In Koramangala' -> bhk, kind, society, locality, deal."""
    m = TITLE.match(H.unescape(title or ""))
    if not m:
        return {}
    bhk = int(m.group(1)) if m.group(1) else None  # an RK (one room + kitchen) has no bedroom count: left as None
    society = (m.group(4) or "").split(",")[0].strip() or None  # independent houses have no society
    # placeholders owners type instead of a society name ("Standalone Building", "Sb", "Apartment")
    if society and re.fullmatch(r"stand\s*a?l\w*(\s*bu\w*)?|sb|apartments?|building|independent(\s+\w+)*", society, re.I):
        society = None
    # "4+ BHK" is a lower bound: keep the 4 but say so; a lease is a lump sum, not a monthly rent
    return {"bhk": bhk, "rk": bool(m.group(2)), "kind": m.group(3).strip().lower(), "society": society,
            "locality": (m.group(6) or "").strip() or None, "deal": m.group(5).lower(), "bhk_plus": "+" in m.group(0)[:6]}


def listing_id(url):
    m = re.search(r"/([0-9a-f]{32})/detail", url or "")
    return m.group(1) if m else None


def _ld_blocks(html):
    for m in re.finditer(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            b = json.loads(m.group(1))
        except ValueError:
            continue
        yield from (b if isinstance(b, list) else [b])


def parse_rent_page(html):
    out = []
    for x in _ld_blocks(html or ""):
        if not isinstance(x, dict) or x.get("@type") != "Apartment":
            continue
        t = parse_title(x.get("description"))
        props = {p.get("name"): p.get("value") for p in x.get("additionalProperty") or [] if isinstance(p, dict)}
        geo = x.get("geo") or {}
        url = x.get("url") or ""
        if not t or t["deal"] == "sale" or not props.get("Rent") or not listing_id(url):
            continue
        out.append({"id": listing_id(url), "deal": t["deal"], "bhk": t["bhk"], "bhk_plus": t["bhk_plus"], "kind": t["kind"], "society": t["society"],
                    "locality": t["locality"], "price": _num(props.get("Rent")), "deposit": _num(props.get("Deposit")),
                    "sqft": None, "psf": None, "lat": _num(geo.get("latitude")), "lng": _num(geo.get("longitude")),
                    "url": url, "source": "nobroker"})
    return out


def _prop(card, name):
    m = re.search(rf'itemProp="{name}"[^>]*?(?:content="([^"]*)"[^>]*)?>([^<]*)', card)
    if not m:
        return None
    return H.unescape((m.group(1) or m.group(2) or "").replace("<!-- -->", "")).strip() or None


def parse_sale_page(html):
    out = []
    for card in re.split(r"<article\b", html or "")[1:]:
        card = card[:card.find("</article>")] if "</article>" in card else card
        href = re.search(r'href="(/property/buy/[^"#]+/detail)"', card)
        title = re.search(r'title="([^"]+)"\s+itemProp="description"', card) or re.search(r'itemProp="description"[^>]*title="([^"]+)"', card)
        if not href or not title:
            continue
        t = parse_title(title.group(1))
        price = _num(re.sub(r"<!--.*?-->", "", (re.search(r'itemProp="price">(.*?)</span>', card, re.S) or [None, ""])[1]))
        sqft = re.search(r">\s*([\d,]+)\s*sqft\s*<", card)
        posted = _prop(card, "startDate")
        lat, lng = _num(_prop(card, "latitude")), _num(_prop(card, "longitude"))
        if not t or not price:
            continue
        sq = _num(sqft.group(1)) if sqft else None
        url = BASE + href.group(1)
        out.append({"id": listing_id(url), "deal": "sale", "bhk": t["bhk"], "bhk_plus": t["bhk_plus"], "kind": t["kind"], "society": t["society"],
                    "locality": t["locality"], "price": price, "deposit": None, "sqft": sq,
                    "psf": round(price / sq) if sq else None, "posted": posted, "lat": lat, "lng": lng,
                    "url": url, "source": "nobroker"})
    return out


def blocked(html):
    """True when the page looks like a bot check rather than results; the crawler stops instead of working around it."""
    h = (html or "")[:200_000].lower()
    return "captcha" in h or "access denied" in h or "unusual traffic" in h
