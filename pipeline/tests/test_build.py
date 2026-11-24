import build_city
import geo


def area(name, center, r=150):
    return {"type": "Feature", "properties": {"osm": "way/" + name, "name": name},
            "geometry": {"type": "Polygon", "coordinates": [geo.circle(center, r)]}}


def test_match_area_inside_and_by_name():
    areas = [area("Heritage One", (77.0891, 28.4027)), area("Skyon", (77.0966, 28.3995))]
    g = build_city.Grid(areas, lambda a: geo.centroid(a["geometry"]["coordinates"][0]))
    p = {"name": "Conscient Heritage One", "lng": 77.0893, "lat": 28.4030}
    assert build_city.match_area(p, g)["properties"]["name"] == "Heritage One"
    near = {"name": "Ireo Skyon", "lng": 77.0966 + 0.0025, "lat": 28.3995}  # ~245 m east, outside
    assert build_city.match_area(near, g)["properties"]["name"] == "Skyon"
    far = {"name": "Random Homes", "lng": 77.2, "lat": 28.5}
    assert build_city.match_area(far, g) is None


def test_dedupe_merges_phases_close_by():
    a = {"name": "Heritage One", "lng": 77.0890, "lat": 28.4034, "url": "a"}
    b = {"name": "Heritage One", "lng": 77.0891, "lat": 28.4021, "url": "b"}
    c = {"name": "Heritage One", "lng": 77.2, "lat": 28.5, "url": "c"}
    out = build_city.dedupe([a, b, c])
    assert len(out) == 2 and out[0]["merged"] == ["b"]


def test_kind_of():
    assert build_city.kind_of({"config_text": "2, 3, 4 BHK Multistorey Apartments"}) == "apartment"
    assert build_city.kind_of({"config_text": "Residential Plot"}) == "plot"
    assert build_city.kind_of({"config_text": "4 BHK Villa"}) == "villa"


def test_neighbourhood_sized_area_is_not_a_society_site():
    big = area("DLF Phase 4", (77.08, 28.46), r=700)  # ~1.5 km2
    g = build_city.Grid([big], lambda a: geo.centroid(a["geometry"]["coordinates"][0]))
    p = {"name": "Some Apartments", "lng": 77.08, "lat": 28.46, "acres": 5}
    assert build_city.match_area(p, g) is None


def test_kind_from_unit_codes_when_text_missing():
    assert build_city.kind_of({"configs": {"units": [{"kind": "10000"}]}}) == "plot"
    assert build_city.kind_of({"configs": {"units": [{"kind": "10008"}, {"kind": "10002"}]}}) == "apartment"
    assert build_city.kind_of({}) == "apartment~"


def test_kind_from_card_type_codes():
    assert build_city.kind_of({"type_codes": ["10000"]}) == "plot"
    assert build_city.kind_of({"card_units": [{"kind": "10003", "bhk": 3, "sqft": 1900.0}]}) == "builder floor"


def test_infer_kind_from_name():
    assert build_city.kind_of({"name": "Sai Ram Apartment"}) == "apartment~"
    assert build_city.kind_of({"name": "Rzone Land Plot"}) == "plot~"
    assert build_city.kind_of({"name": "Emaar Business District 114"}) == "commercial~"
    assert build_city.kind_of({"name": "Ashiana Villas"}) == "villa~"


def test_match_verified_needs_whole_name_and_sector():
    ps = [{"mb_id": 1, "name": "M3M", "locality": "Sector 65"},
          {"mb_id": 2, "name": "M3M Heights", "locality": "Sector 65"},
          {"mb_id": 3, "name": "M3M St Andrews at SCDA", "locality": "Sector 113"},
          {"mb_id": 4, "name": "M3M St. Andrews", "locality": "Sector 65"}]
    assert build_city.match_verified({"match": ["M3M Heights"], "sector": "65"}, ps)["mb_id"] == 2
    assert build_city.match_verified({"match": ["M3M St Andrews"], "sector": "65"}, ps)["mb_id"] == 4
    assert build_city.match_verified({"match": ["M3M Heights"], "sector": "65"}, ps, taken={2}) is None


def test_attach_nobroker_by_name_only():
    sobha = {"name": "Sobha Infinia", "lng": 77.6249, "lat": 12.9249, "rent_listings": [{"bhk": 3, "price": 90000, "sqft": None}]}
    kristal = {"name": "Kristal Sunstone", "lng": 77.6345, "lat": 12.9380}
    base = {"kind": "flat", "bhk_plus": False, "sqft": None, "psf": None, "url": "u"}
    ls = [
        {**base, "deal": "rent", "bhk": 3, "price": 95000, "society": "Sobha Infinia", "lng": 77.6252, "lat": 12.9251},
        {**base, "deal": "rent", "bhk": 3, "price": 90000, "society": "Sobha Infinia", "lng": 77.6252, "lat": 12.9251},  # already on Magicbricks
        {**base, "deal": "sale", "bhk": 2, "price": 1.4e7, "society": "Kristal Sun Stone", "lng": 77.6346, "lat": 12.9381},
        {**base, "deal": "rent", "bhk": 2, "price": 30000, "society": "Some Other Residency", "lng": 77.6250, "lat": 12.9250},  # close, wrong name
        {**base, "deal": "rent", "bhk": 2, "price": 30000, "society": None, "kind": "house", "lng": 77.6250, "lat": 12.9250},
        {**base, "deal": "lease", "bhk": 2, "price": 900000, "society": "Sobha Infinia", "lng": 77.6250, "lat": 12.9250},
        {**base, "deal": "sale", "bhk": 4, "bhk_plus": True, "price": 6e7, "society": "Sobha Infinia", "lng": 77.6250, "lat": 12.9250},
        {**base, "deal": "rent", "bhk": 3, "price": 80000, "society": "Sobha Infinia", "lng": 77.70, "lat": 12.99},  # same name, ~10 km away
    ]
    stats = build_city.attach_nobroker([sobha, kristal], ls)
    assert stats == {"attached_rent": 1, "duplicate": 1, "attached_sale": 1, "unmatched": 2, "not_a_society_flat": 3}
    assert [l["price"] for l in sobha["rent_listings"]] == [90000, 95000] and sobha["rent_listings"][1]["source"] == "nobroker"
    assert kristal["nb"] == {"rent": 0, "sale": 1, "links": [{"deal": "sale", "bhk": 2, "price": 1.4e7, "url": "u"}]}
