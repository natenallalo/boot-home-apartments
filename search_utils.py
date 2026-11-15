"""Smart Hebrew search-query parsing for apartment filters."""

from __future__ import annotations

import re
from typing import Any

KNOWN_CITIES: list[str] = sorted(
    [
        "תל אביב יפו",
        "תל אביב",
        "רמת גן",
        "גבעתיים",
        "רמת השרון",
        "פתח תקווה",
        "פתח תקוה",
        "ראשון לציון",
        "באר שבע",
        "ירושלים",
        "חיפה",
        "חולון",
        "בת ים",
        "רמלה",
        "לוד",
        "נתניה",
        "הרצליה",
        "כפר סבא",
        "רעננה",
        "מודיעין",
        "אשדוד",
        "אשקלון",
        "אילת",
        "טבריה",
        "קריית אונו",
        "קרית אונו",
        "רחובות",
        "הוד השרון",
        "נס ציונה",
        "יבנה",
        "בני ברק",
    ],
    key=len,
    reverse=True,
)

STOPWORDS = {
    "דירה",
    "דירות",
    "דירת",
    "יחידה",
    "יחידת",
    "דיור",
    "או",
    "ב",
    "של",
    "להשכרה",
    "השכרה",
    "שכירות",
    "לשכירות",
    "עם",
    "עד",
    "חדרים",
    "חדר",
    "חד",
    "מחפש",
    "מחפשת",
    "רוצה",
    "בקשה",
    "אני",
    "על",
    "את",
    "לי",
    "באזור",
    "באזור",
    "שח",
    "₪",
    "אלף",
}


def clean_hebrew(text: str) -> str:
    """Remove Hebrew cantillation/niqqud and odd control marks."""
    value = text or ""
    value = re.sub(r"[\u0591-\u05C7]+", "", value)
    value = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


FOCUS_REGION_CITIES = ["רמלה", "לוד"]


def _canonical_city(city: str) -> str:
    if city in {"תל אביב יפו", "תל אביב"}:
        return "תל אביב"
    if city == "פתח תקוה":
        return "פתח תקווה"
    if city == "קרית אונו":
        return "קריית אונו"
    return city


def extract_city(text: str) -> str | None:
    cities = extract_cities(text)
    return cities[0] if cities else None


def extract_cities(text: str) -> list[str]:
    cleaned = clean_hebrew(text)
    found: list[str] = []
    for city in KNOWN_CITIES:
        if city in cleaned:
            canonical = _canonical_city(city)
            if canonical not in found:
                found.append(canonical)
    return found


def parse_search_query(text: str) -> dict[str, Any]:
    """
    Parse a free-text Hebrew search into structured filters.
    Example: 'דירה או יחידת דיור ברמלה' -> city=רמלה, types=[דירה, יחידת דיור]
    """
    raw = clean_hebrew(text or "")
    cities = extract_cities(raw)
    city = cities[0] if cities else None

    types: list[str] = []
    if re.search(r"יחיד(?:ה|ת)\s*דיור|יחידת\s*דיור", raw):
        types.extend(["יחידת דיור", "יחידה"])
    if re.search(r"\bדיר(?:ה|ת|ות)\b", raw) or "דירה" in raw or "דירת" in raw:
        types.append("דירה")
    if "וילה" in raw:
        types.append("וילה")
    if "פנטהאוז" in raw or "פנטאוז" in raw:
        types.append("פנטהאוז")

    # Deduplicate types while preserving order
    seen: set[str] = set()
    uniq_types: list[str] = []
    for item in types:
        if item not in seen:
            seen.add(item)
            uniq_types.append(item)

    leftover = raw
    for c in sorted(cities, key=len, reverse=True):
        leftover = leftover.replace(c, " ")
        if c == "תל אביב":
            leftover = leftover.replace("תל אביב יפו", " ")
    for stop in sorted(STOPWORDS, key=len, reverse=True):
        leftover = leftover.replace(stop, " ")
    for t in uniq_types:
        leftover = leftover.replace(t, " ")

    tokens = [t for t in re.split(r"\s+", leftover) if t and t not in STOPWORDS]

    # Natural-language rooms / price hints (optional extras)
    rooms = None
    rooms_match = re.search(r"(\d+(?:\.\d)?)\s*חדר", raw)
    if rooms_match:
        try:
            rooms = float(rooms_match.group(1))
        except ValueError:
            rooms = None

    max_price = None
    price_match = re.search(r"עד\s*(\d{1,2}(?:,\d{3})?|\d{3,5})", raw)
    if price_match:
        try:
            max_price = int(price_match.group(1).replace(",", ""))
            if max_price < 100:  # e.g. "עד 3 אלף"
                max_price *= 1000
        except ValueError:
            max_price = None
    elif "אלף" in raw:
        thousands = re.search(r"(\d+)\s*אלף", raw)
        if thousands:
            max_price = int(thousands.group(1)) * 1000

    return {
        "raw": raw,
        "city": city,
        "cities": cities,
        "types": uniq_types,
        "tokens": tokens,
        "rooms": rooms,
        "max_price": max_price,
    }
