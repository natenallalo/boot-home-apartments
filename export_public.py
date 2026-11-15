"""Export filtered listings for the public GitHub Pages viewer."""

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
    return {
        "id": row.get("id"),
        "title": row.get("title") or "ללא כותרת",
        "city": row.get("city") or "",
        "neighborhood": row.get("neighborhood") or "",
        "price": row.get("price"),
        "rooms": row.get("rooms"),
        "floor": row.get("floor"),
        "property_type": row.get("property_type") or "",
        "source": row.get("source") or "",
        "url": row.get("url") or "",
        "summary": row.get("summary") or "",
        "is_realtor": bool(row.get("is_realtor")),
        "is_favorite": bool(row.get("is_favorite")),
        "updated_at": row.get("updated_at") or row.get("created_at") or "",
    }


def export_public_data() -> dict:
    settings = load_settings()
    cities = settings.get("cities") or ["רמלה", "לוד"]
    min_rooms = settings.get("min_rooms") or 0
    max_price = settings.get("max_price") or 0

    matches = db.search_apartments(
        city_keyword=" ".join(cities),
        min_price=settings.get("min_price") or None,
        max_price=max_price if max_price else None,
        min_rooms=min_rooms if min_rooms else None,
        max_rooms=settings.get("max_rooms") or None,
        include_apartments=bool(settings.get("include_apartments", True)),
        include_units=bool(settings.get("include_units", True)),
        ground_floor_only=bool(settings.get("ground_floor_only", False)),
        rooms_flexible_for_units=True,
        private_only=bool(settings.get("private_only", False)),
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cities": cities,
        "filters": {
            "max_price": max_price or None,
            "min_rooms": min_rooms or None,
            "include_units": bool(settings.get("include_units", True)),
            "ground_floor_only": bool(settings.get("ground_floor_only", False)),
        },
        "count": len(matches),
        "db_total": db.count_apartments(),
        "listings": [_public_row(dict(r)) for r in matches],
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
