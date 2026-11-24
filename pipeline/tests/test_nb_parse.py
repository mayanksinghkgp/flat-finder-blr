import pathlib

import nb_parse

FX = pathlib.Path(__file__).parent / "fixtures"


def read(name):
    return (FX / name).read_text(encoding="utf-8")


def test_title():
    t = nb_parse.parse_title("3 BHK Flat In Example Elite, Koramangala for Rent  In Koramangala")
    assert t == {"bhk": 3, "rk": False, "kind": "flat", "society": "Example Elite", "locality": "Koramangala", "deal": "rent", "bhk_plus": False}
    assert nb_parse.parse_title("1 RK Flat In Sample House, Hsr Layout for Rent  In Hsr Layout")["bhk"] is None
    h = nb_parse.parse_title("4+ BHK House For Sale  In Ejipura")
    assert (h["bhk"], h["bhk_plus"], h["society"], h["kind"], h["deal"]) == (4, True, None, "house", "sale")
    assert nb_parse.parse_title("1 BHK House for Lease  In Koramangala")["deal"] == "lease"
    for placeholder in ("Standlaone Building", "Standalonebuilding", "Standalone", "Standalone Buidling", "Sb", "Apartment"):
        assert nb_parse.parse_title(f"1 BHK Flat In {placeholder}, Koramangala for Rent  In Koramangala")["society"] is None
    assert nb_parse.parse_title("1 BHK Flat In Sbi Colony Towers, Koramangala for Rent  In Koramangala")["society"] == "Sbi Colony Towers"
    assert nb_parse.parse_title("not a listing") == {}


def test_rent_page():
    ls = nb_parse.parse_rent_page(read("nb_rent.html"))
    assert len(ls) == 2
    a = ls[0]
    assert (a["bhk"], a["price"], a["deposit"], a["society"]) == (3, 45000, 250000, "Example Elite")
    assert round(a["lat"], 4) == 12.9272 and a["id"] == "0" * 31 + "1"
    assert "telephone" not in a and all("0000000000" != str(v) for v in a.values())


def test_sale_page():
    ls = nb_parse.parse_sale_page(read("nb_sale.html"))
    assert len(ls) == 1
    s = ls[0]
    assert (s["bhk"], s["price"], s["sqft"], s["psf"], s["posted"]) == (2, 8500000, 1070, 7944, "2026-11-03")
    assert s["society"] == "Example Jasmine Apartments" and round(s["lng"], 3) == 77.634
    assert s["url"].startswith("https://www.nobroker.in/property/buy/") and "Owner Name" not in str(s)


def test_blocked():
    assert nb_parse.blocked("<html>Please complete the CAPTCHA</html>")
    assert not nb_parse.blocked(read("nb_rent.html"))
