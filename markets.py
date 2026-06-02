import re


SKAGIT_VALLEY = {
    "slug": "skagit-valley-wa",
    "name": "Skagit Valley",
    "label": "Skagit Valley, WA",
    "center": [48.45, -122.34],
    "zoom": 10,
    "cities": [
        "Anacortes",
        "Bow",
        "Burlington",
        "Clear Lake",
        "Concrete",
        "Conway",
        "Hamilton",
        "La Conner",
        "Lyman",
        "Marblemount",
        "Mount Vernon",
        "Rockport",
        "Sedro-Woolley",
    ],
}

MARKETS = [SKAGIT_VALLEY]


def normalize_location(value):
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def resolve_market(location):
    requested = location.strip()
    if not requested:
        return SKAGIT_VALLEY, None

    normalized = normalize_location(requested)
    city_lookup = {normalize_location(city): city for city in SKAGIT_VALLEY["cities"]}
    if normalized in {"skagit", "skagit county", "skagit valley", "skagit valley wa"}:
        return SKAGIT_VALLEY, None
    if normalized in city_lookup:
        return SKAGIT_VALLEY, city_lookup[normalized]
    return None, None
