"""Export all listings for the public GitHub Pages viewer (client-side filters)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import database as db
from settings_store import load_settings

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
DATA_PATH = DOCS / "data.json"


def _public_row(row: dict) -> dict:
    title = row.get("title") or ""
    description = row.get("description") or ""
    property_type = row.get("property_type") or ""
    blob = f"{title} {description} {property_type}".lower()
    is_unit = (
        property_type == "יחידת דיור"
        or "יחיד" in title
        or "יחיד" in description
        or "יחידת דיור" in title
        or "יחידת דיור" in description
    )
    is_garden = (
        property_type == "דירת גן"
        or "דירת גן" in title
        or "דירת גן" in description
        or "קרקע" in title
        or "קרקע" in description
    )
    return {
        "id": row.get("id"),
        "title": title or "ללא כותרת",
        "description": description,
        "city": row.get("city") or "",
        "neighborhood": row.get("neighborhood") or "",
        "price": row.get("price"),
        "rooms": row.get("rooms"),
        "floor": row.get("floor"),
        "property_type": property_type,
        "source": row.get("source") or "",
        "url": row.get("url") or "",
        "summary": row.get("summary") or "",
        "is_realtor": bool(row.get("is_realtor")),
        "is_favorite": bool(row.get("is_favorite")),
        "is_unit": bool(is_unit),
        "is_garden": bool(is_garden),
        "search_blob": blob,
        "updated_at": row.get("updated_at") or row.get("created_at") or "",
    }


def export_public_data() -> dict:
    settings = load_settings()
    cities = settings.get("cities") or ["רמלה", "לוד"]

    # Export the full catalog (non-hidden) so the public page can filter live.
    all_rows = db.search_apartments(include_hidden=False)
    listings = [_public_row(dict(r)) for r in all_rows]

    defaults = {
        "city_keyword": settings.get("city_keyword") or " ".join(cities),
        "focus_region": bool(settings.get("focus_region", True)),
        "include_apartments": bool(settings.get("include_apartments", True)),
        "include_units": bool(settings.get("include_units", True)),
        "ground_floor_only": bool(settings.get("ground_floor_only", False)),
        "min_price": int(settings.get("min_price") or 0),
        "max_price": int(settings.get("max_price") or 3500),
        "min_rooms": float(settings.get("min_rooms") or 3),
        "max_rooms": float(settings.get("max_rooms") or 0),
        "min_floor": int(settings.get("min_floor") or 0),
        "max_floor": int(settings.get("max_floor") or 0),
        "private_only": bool(settings.get("private_only", False)),
        "favorites_only": False,
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cities": cities,
        "defaults": defaults,
        "count": len(listings),
        "db_total": db.count_apartments(),
        "listings": listings,
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    data = export_public_data()
    print(f"Exported {data['count']} listings to {DATA_PATH}")
