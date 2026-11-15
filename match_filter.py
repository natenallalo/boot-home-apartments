"""Apply saved search settings to listing dicts (shared by worker alerts + UI)."""

from __future__ import annotations

from typing import Any


def _is_unit(item: dict[str, Any]) -> bool:
    prop = item.get("property_type") or ""
    blob = f"{item.get('title') or ''} {item.get('description') or ''} {prop}"
    return prop == "יחידת דיור" or "יחיד" in blob


def _is_commercial(item: dict[str, Any]) -> bool:
    blob = f"{item.get('title') or ''} {item.get('description') or ''}"
    return any(w in blob for w in ("חנות", "משרד", "מחסן", "עסק"))


def _is_sale(item: dict[str, Any]) -> bool:
    blob = f"{item.get('title') or ''} {item.get('description') or ''}"
    return "למכירה" in blob and "להשכרה" not in blob


def _is_ground(item: dict[str, Any]) -> bool:
    if item.get("floor") == 0:
        return True
    blob = f"{item.get('title') or ''} {item.get('description') or ''} {item.get('property_type') or ''}"
    return "קרקע" in blob or "דירת גן" in blob or item.get("property_type") == "דירת גן"


def listing_matches_settings(item: dict[str, Any], settings: dict[str, Any]) -> bool:
    if _is_sale(item) or _is_commercial(item):
        return False

    cities = settings.get("cities") or ["רמלה", "לוד"]
    focus = bool(settings.get("focus_region", True))
    hay = (
        f"{item.get('city') or ''} {item.get('neighborhood') or ''} "
        f"{item.get('title') or ''} {item.get('description') or ''} {item.get('summary') or ''}"
    )
    if focus:
        if not any(c in hay for c in cities):
            return False

    include_apartments = bool(settings.get("include_apartments", True))
    include_units = bool(settings.get("include_units", True))
    unit = _is_unit(item)
    if unit and not include_units:
        return False
    if (not unit) and not include_apartments:
        return False

    if settings.get("ground_floor_only") and not _is_ground(item):
        return False
    if settings.get("private_only") and item.get("is_realtor"):
        return False

    min_price = int(settings.get("min_price") or 0)
    max_price = int(settings.get("max_price") or 0)
    price = item.get("price")
    if min_price > 0 and (price is None or price < min_price):
        return False
    if max_price > 0 and (price is None or price > max_price):
        return False

    min_rooms = float(settings.get("min_rooms") or 0)
    max_rooms = float(settings.get("max_rooms") or 0)
    rooms = item.get("rooms")
    if max_rooms > 0 and rooms is not None and rooms > max_rooms:
        return False
    if min_rooms > 0:
        if unit and include_units:
            pass
        elif rooms is None or rooms < min_rooms:
            return False

    min_floor = int(settings.get("min_floor") or 0)
    max_floor = int(settings.get("max_floor") or 0)
    floor = item.get("floor")
    if floor is not None:
        if min_floor > 0 and floor < min_floor:
            return False
        if max_floor > 0 and floor > max_floor:
            return False

    return True


def filter_matches(
    listings: list[dict[str, Any]], settings: dict[str, Any]
) -> list[dict[str, Any]]:
    return [item for item in listings if listing_matches_settings(item, settings)]
