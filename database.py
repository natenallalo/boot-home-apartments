"""SQLite database handler for apartment listings."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

DB_PATH = Path(__file__).resolve().parent / "apartments.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db_session() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apartments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id TEXT,
                url TEXT UNIQUE,
                title TEXT,
                description TEXT,
                city TEXT,
                neighborhood TEXT,
                price INTEGER,
                rooms REAL,
                floor INTEGER,
                source TEXT,
                is_realtor INTEGER DEFAULT 0,
                realtor_reason TEXT,
                summary TEXT,
                property_type TEXT,
                is_favorite INTEGER DEFAULT 0,
                is_hidden INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Lightweight migrations for existing DBs
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(apartments)").fetchall()
        }
        if "property_type" not in cols:
            conn.execute("ALTER TABLE apartments ADD COLUMN property_type TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_apartments_url ON apartments(url)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_apartments_external_id ON apartments(external_id)"
        )


def upsert_apartment(listing: dict[str, Any]) -> bool:
    """
    Insert a listing, or refresh an existing one with richer fields.
    Returns True if a new row was inserted, False if an existing row was updated/skipped.
    """
    url = (listing.get("url") or "").strip()
    external_id = (listing.get("external_id") or "").strip() or None
    if not url and not external_id:
        return False

    with db_session() as conn:
        existing = None
        if url:
            existing = conn.execute(
                "SELECT id FROM apartments WHERE url = ?", (url,)
            ).fetchone()
        if not existing and external_id:
            existing = conn.execute(
                "SELECT id FROM apartments WHERE external_id = ?", (external_id,)
            ).fetchone()

        values = (
            external_id,
            url or f"mock://{external_id}",
            listing.get("title"),
            listing.get("description"),
            listing.get("city"),
            listing.get("neighborhood"),
            listing.get("price"),
            listing.get("rooms"),
            listing.get("floor"),
            listing.get("source"),
            1 if listing.get("is_realtor") else 0,
            listing.get("realtor_reason"),
            listing.get("summary"),
            listing.get("property_type"),
            1 if listing.get("is_favorite") else 0,
            1 if listing.get("is_hidden") else 0,
        )

        if existing:
            conn.execute(
                """
                UPDATE apartments SET
                    external_id = COALESCE(?, external_id),
                    title = COALESCE(?, title),
                    description = COALESCE(?, description),
                    city = COALESCE(?, city),
                    neighborhood = COALESCE(?, neighborhood),
                    price = COALESCE(?, price),
                    rooms = COALESCE(?, rooms),
                    floor = COALESCE(?, floor),
                    source = COALESCE(?, source),
                    is_realtor = COALESCE(?, is_realtor),
                    realtor_reason = COALESCE(?, realtor_reason),
                    summary = COALESCE(?, summary),
                    property_type = COALESCE(?, property_type),
                    is_hidden = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    external_id,
                    listing.get("title"),
                    listing.get("description"),
                    listing.get("city"),
                    listing.get("neighborhood"),
                    listing.get("price"),
                    listing.get("rooms"),
                    listing.get("floor"),
                    listing.get("source"),
                    1 if listing.get("is_realtor") else 0,
                    listing.get("realtor_reason"),
                    listing.get("summary"),
                    listing.get("property_type"),
                    existing["id"],
                ),
            )
            return False

        conn.execute(
            """
            INSERT INTO apartments (
                external_id, url, title, description, city, neighborhood,
                price, rooms, floor, source, is_realtor, realtor_reason,
                summary, property_type, is_favorite, is_hidden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        return True


def upsert_many(listings: list[dict[str, Any]]) -> int:
    inserted = 0
    for listing in listings:
        if upsert_apartment(listing):
            inserted += 1
    return inserted


def set_favorite(apartment_id: int, is_favorite: bool) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE apartments SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if is_favorite else 0, apartment_id),
        )


def set_hidden(apartment_id: int, is_hidden: bool) -> None:
    with db_session() as conn:
        conn.execute(
            "UPDATE apartments SET is_hidden = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if is_hidden else 0, apartment_id),
        )


def update_analysis(
    apartment_id: int,
    *,
    is_realtor: bool,
    realtor_reason: str,
    price: Optional[int] = None,
    rooms: Optional[float] = None,
    floor: Optional[int] = None,
    city: Optional[str] = None,
    neighborhood: Optional[str] = None,
    summary: Optional[str] = None,
) -> None:
    with db_session() as conn:
        conn.execute(
            """
            UPDATE apartments SET
                is_realtor = ?,
                realtor_reason = ?,
                price = COALESCE(?, price),
                rooms = COALESCE(?, rooms),
                floor = COALESCE(?, floor),
                city = COALESCE(?, city),
                neighborhood = COALESCE(?, neighborhood),
                summary = COALESCE(?, summary),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                1 if is_realtor else 0,
                realtor_reason,
                price,
                rooms,
                floor,
                city,
                neighborhood,
                summary,
                apartment_id,
            ),
        )


def search_apartments(
    *,
    city_keyword: str = "",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    min_rooms: Optional[float] = None,
    max_rooms: Optional[float] = None,
    min_floor: Optional[int] = None,
    max_floor: Optional[int] = None,
    private_only: bool = False,
    include_hidden: bool = False,
    favorites_only: bool = False,
    include_apartments: bool = True,
    include_units: bool = True,
    ground_floor_only: bool = False,
    rooms_flexible_for_units: bool = True,
) -> list[dict[str, Any]]:
    from search_utils import parse_search_query

    clauses = ["1=1"]
    params: list[Any] = []

    if not include_hidden:
        clauses.append("is_hidden = 0")
    if favorites_only:
        clauses.append("is_favorite = 1")
    if private_only:
        clauses.append("is_realtor = 0")

    # Property type filters (דירה / יחידת דיור)
    type_parts = []
    if include_apartments:
        type_parts.append(
            "(COALESCE(property_type, '') = '' OR property_type = 'דירה' OR property_type = 'דירת גן' "
            "OR title LIKE '%דירה%' OR description LIKE '%דירה%')"
        )
    if include_units:
        type_parts.append(
            "(property_type = 'יחידת דיור' OR title LIKE '%יחיד%' OR description LIKE '%יחיד%' "
            "OR title LIKE '%יחידת דיור%' OR description LIKE '%יחידת דיור%')"
        )
    if type_parts and not (include_apartments and include_units):
        clauses.append("(" + " OR ".join(type_parts) + ")")
    elif include_apartments and include_units:
        pass  # both => no type restriction
    elif not include_apartments and not include_units:
        clauses.append("1=0")

    if ground_floor_only:
        clauses.append(
            "(floor = 0 OR title LIKE '%קרקע%' OR description LIKE '%קרקע%' "
            "OR title LIKE '%דירת גן%' OR description LIKE '%דירת גן%' "
            "OR property_type = 'דירת גן')"
        )

    keyword = (city_keyword or "").strip()
    parsed = parse_search_query(keyword) if keyword else {}
    cities = parsed.get("cities") or ([] if not parsed.get("city") else [parsed.get("city")])
    types = parsed.get("types") or []
    tokens = parsed.get("tokens") or []

    text_fields = "(city LIKE ? OR neighborhood LIKE ? OR title LIKE ? OR description LIKE ? OR summary LIKE ?)"

    if cities:
        city_parts = []
        for city in cities:
            city_parts.append(text_fields)
            like_city = f"%{city}%"
            params.extend([like_city, like_city, like_city, like_city, like_city])
        clauses.append("(" + " OR ".join(city_parts) + ")")
    elif keyword and not types and not tokens:
        # Fallback: whole phrase only when we couldn't parse anything smarter
        like = f"%{keyword}%"
        clauses.append(text_fields)
        params.extend([like, like, like, like, like])

    # Generic housing words shouldn't hide results; only specific types filter.
    specific_types = [
        t for t in types if t not in {"דירה", "יחידה", "יחידת דיור"}
    ]
    if specific_types:
        type_parts = []
        for t in specific_types:
            type_parts.append(text_fields)
            like_t = f"%{t}%"
            params.extend([like_t, like_t, like_t, like_t, like_t])
        clauses.append("(" + " OR ".join(type_parts) + ")")

    for token in tokens:
        like_tok = f"%{token}%"
        clauses.append(text_fields)
        params.extend([like_tok, like_tok, like_tok, like_tok, like_tok])

    # Numeric filters: allow NULL floor (unknown) so we don't hide valid ads.
    if min_price is not None:
        clauses.append("price IS NOT NULL AND price >= ?")
        params.append(min_price)
    if max_price is not None:
        clauses.append("price IS NOT NULL AND price <= ?")
        params.append(max_price)

    unit_expr = (
        "(property_type = 'יחידת דיור' OR title LIKE '%יחיד%' OR description LIKE '%יחיד%')"
    )
    if min_rooms is not None and max_rooms is not None:
        if rooms_flexible_for_units and include_units:
            clauses.append(
                f"((NOT {unit_expr} AND rooms IS NOT NULL AND rooms >= ? AND rooms <= ?) OR {unit_expr})"
            )
            params.extend([min_rooms, max_rooms])
        else:
            clauses.append("rooms IS NOT NULL AND rooms >= ? AND rooms <= ?")
            params.extend([min_rooms, max_rooms])
    elif min_rooms is not None:
        if rooms_flexible_for_units and include_units:
            clauses.append(
                f"((NOT {unit_expr} AND rooms IS NOT NULL AND rooms >= ?) OR {unit_expr})"
            )
            params.append(min_rooms)
        else:
            clauses.append("rooms IS NOT NULL AND rooms >= ?")
            params.append(min_rooms)
    elif max_rooms is not None:
        clauses.append("(rooms IS NULL OR rooms <= ?)")
        params.append(max_rooms)

    if min_floor is not None:
        clauses.append("(floor IS NULL OR floor >= ?)")
        params.append(min_floor)
    if max_floor is not None:
        clauses.append("(floor IS NULL OR floor <= ?)")
        params.append(max_floor)

    query = f"""
        SELECT * FROM apartments
        WHERE {' AND '.join(clauses)}
        ORDER BY is_favorite DESC, price ASC, id DESC
    """

    with db_session() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def count_apartments() -> int:
    with db_session() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM apartments").fetchone()
        return int(row["c"]) if row else 0


def clear_all() -> None:
    with db_session() as conn:
        conn.execute("DELETE FROM apartments")


init_db()
