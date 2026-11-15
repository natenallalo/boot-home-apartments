"""Hebrew listing analyzer with OpenAI structured outputs + keyword fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

REALTOR_KEYWORDS = [
    "תיווך",
    "מתווך",
    "מתווכת",
    "בלעדיות",
    "עמלת תיווך",
    "עמלת מתווך",
    "משרד תיווך",
    "משרד נדל",
    "סוכן נדל",
    "סוכנות",
    "נדל״ן",
    'נדל"ן',
    "רישיון תיווך",
    "נציג המשרד",
    "דרך המשרד",
    "לתיאום סיור עם",
]

PRIVATE_KEYWORDS = [
    "ללא תיווך",
    "בלי תיווך",
    "בלי מתווך",
    "בלי מתווכים",
    "אין תיווך",
    "בעל הדירה",
    "בעלת הדירה",
    "בעל הבית",
    "בעלת הבית",
    "משכיר פרטי",
    "ישירות ממני",
    "רק פניות ישירות",
]


class ListingAnalysis(BaseModel):
    is_realtor: bool = Field(description="True if listing is from a realtor/agency")
    realtor_reason: str = Field(description="Short Hebrew reason for realtor classification")
    price: Optional[int] = Field(default=None, description="Monthly rent in ILS")
    rooms: Optional[float] = Field(default=None, description="Number of rooms")
    floor: Optional[int] = Field(default=None, description="Floor number, 0 for ground")
    city: Optional[str] = Field(default=None, description="City name in Hebrew")
    neighborhood: Optional[str] = Field(default=None, description="Neighborhood in Hebrew")
    summary: str = Field(description="One-sentence Hebrew summary of the listing")


def get_openai_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'")


def _token_present(token: Optional[str]) -> bool:
    return bool(token and token.strip() and token.strip() not in {'""', "''"})


def _combined_text(listing: dict[str, Any]) -> str:
    parts = [
        listing.get("title") or "",
        listing.get("description") or "",
        listing.get("summary") or "",
    ]
    return "\n".join(p for p in parts if p).strip()


def rule_based_detect_realtor(text: str) -> tuple[bool, str]:
    """Smart Hebrew keyword fallback for realtor vs private landlord."""
    if not text:
        return False, ""

    lowered = text  # Hebrew matching is case-insensitive by nature for these terms

    private_hits = [kw for kw in PRIVATE_KEYWORDS if kw in lowered]
    realtor_hits = [kw for kw in REALTOR_KEYWORDS if kw in lowered]

    # Explicit private statements outweigh generic realtor words.
    if private_hits and not any(k in lowered for k in ("עמלת תיווך", "בלעדיות", "משרד תיווך")):
        return False, f"סימנים לפרטי: {', '.join(private_hits[:2])}"

    if realtor_hits:
        return True, f"זוהה תיווך לפי: {', '.join(realtor_hits[:3])}"

    return False, "לא נמצאו סימני תיווך"


def _extract_price(text: str) -> Optional[int]:
    patterns = [
        r"(\d{1,2}[,.]?\d{3})\s*₪",
        r"₪\s*(\d{1,2}[,.]?\d{3})",
        r"מחיר\s*[:=]?\s*(\d{1,2}[,.]?\d{3})",
        r"(\d{1,2}[,.]?\d{3})\s*ש[\"״]?ח",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            raw = match.group(1).replace(",", "").replace(".", "")
            try:
                value = int(raw)
                if 1500 <= value <= 50000:
                    return value
            except ValueError:
                continue
    return None


def _extract_rooms(text: str) -> Optional[float]:
    patterns = [
        r"(\d+(?:\.\d)?)\s*חדרים",
        r"דירת\s+(\d+(?:\.\d)?)\s*חדרים",
        r"(\d+(?:\.\d)?)\s*חד['׳']",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                value = float(match.group(1))
                if 1 <= value <= 10:
                    return value
            except ValueError:
                continue
    if "סטודיו" in text:
        return 1.0
    return None


def _extract_floor(text: str) -> Optional[int]:
    if re.search(r"קומת\s*קרקע|דירת\s*גן", text):
        return 0
    match = re.search(r"קומה\s*(\d{1,2})", text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _extract_city(text: str) -> Optional[str]:
    cities = ["תל אביב", "רמת גן", "גבעתיים", "חיפה", "ירושלים", "באר שבע", "חולון", "בת ים"]
    for city in cities:
        if city in text:
            return city
    return None


def rule_based_analyze(listing: dict[str, Any]) -> ListingAnalysis:
    text = _combined_text(listing)
    is_realtor, reason = rule_based_detect_realtor(text)

    price = listing.get("price")
    if price is None:
        price = _extract_price(text)

    rooms = listing.get("rooms")
    if rooms is None:
        rooms = _extract_rooms(text)

    floor = listing.get("floor")
    if floor is None:
        floor = _extract_floor(text)

    city = listing.get("city") or _extract_city(text)
    neighborhood = listing.get("neighborhood") or None

    title = listing.get("title") or "דירה להשכרה"
    summary = listing.get("summary") or f"{title}" + (f" ב{city}" if city else "") + "."

    if is_realtor and not reason:
        reason = "זוהה כתיווך לפי מילות מפתח"
    if not is_realtor:
        reason = reason if "פרטי" in (reason or "") else ""

    return ListingAnalysis(
        is_realtor=is_realtor,
        realtor_reason=reason if is_realtor else (reason or ""),
        price=int(price) if price is not None else None,
        rooms=float(rooms) if rooms is not None else None,
        floor=int(floor) if floor is not None else None,
        city=city,
        neighborhood=neighborhood,
        summary=summary.strip(),
    )


def openai_analyze(listing: dict[str, Any]) -> Optional[ListingAnalysis]:
    api_key = get_openai_key()
    if not _token_present(api_key):
        return None

    try:
        from openai import OpenAI
    except ImportError:
        return None

    text = _combined_text(listing)
    if not text:
        return None

    client = OpenAI(api_key=api_key)
    system_prompt = (
        "אתה מנתח מודעות דירות להשכרה בעברית. "
        "סווג אם המודעה מתיווך/משרד נדל״ן או מבעל דירה פרטי. "
        "חלץ מחיר, חדרים, קומה, עיר, שכונה, וכתוב סיכום בעברית במשפט אחד. "
        "realtor_reason קצר בעברית רק אם is_realtor=true, אחרת מחרוזת ריקה."
    )
    user_prompt = f"נתח את המודעה הבאה:\n\n{text}"

    try:
        # Prefer Structured Outputs / json_schema when available.
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "listing_analysis",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "is_realtor": {"type": "boolean"},
                            "realtor_reason": {"type": "string"},
                            "price": {"type": ["integer", "null"]},
                            "rooms": {"type": ["number", "null"]},
                            "floor": {"type": ["integer", "null"]},
                            "city": {"type": ["string", "null"]},
                            "neighborhood": {"type": ["string", "null"]},
                            "summary": {"type": "string"},
                        },
                        "required": [
                            "is_realtor",
                            "realtor_reason",
                            "price",
                            "rooms",
                            "floor",
                            "city",
                            "neighborhood",
                            "summary",
                        ],
                        "additionalProperties": False,
                    },
                },
            },
            temperature=0,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        return ListingAnalysis.model_validate(data)
    except Exception:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt + " החזר JSON בלבד."},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            return ListingAnalysis.model_validate(data)
        except Exception:
            return None


def analyze_listing(listing: dict[str, Any], *, use_openai: bool = True) -> ListingAnalysis:
    """Analyze a listing with OpenAI when available, else Hebrew keyword fallback."""
    if use_openai:
        ai_result = openai_analyze(listing)
        if ai_result is not None:
            # Fill gaps from existing listing / rules if model omitted fields.
            fallback = rule_based_analyze(listing)
            return ListingAnalysis(
                is_realtor=ai_result.is_realtor,
                realtor_reason=ai_result.realtor_reason
                or (fallback.realtor_reason if ai_result.is_realtor else ""),
                price=ai_result.price if ai_result.price is not None else fallback.price,
                rooms=ai_result.rooms if ai_result.rooms is not None else fallback.rooms,
                floor=ai_result.floor if ai_result.floor is not None else fallback.floor,
                city=ai_result.city or fallback.city,
                neighborhood=ai_result.neighborhood or fallback.neighborhood,
                summary=ai_result.summary or fallback.summary,
            )

    return rule_based_analyze(listing)


def enrich_listings(
    listings: list[dict[str, Any]], *, use_openai: bool = True
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for listing in listings:
        analysis = analyze_listing(listing, use_openai=use_openai)
        merged = dict(listing)
        merged.update(
            {
                "is_realtor": analysis.is_realtor,
                "realtor_reason": analysis.realtor_reason,
                "price": analysis.price if analysis.price is not None else listing.get("price"),
                "rooms": analysis.rooms if analysis.rooms is not None else listing.get("rooms"),
                "floor": analysis.floor if analysis.floor is not None else listing.get("floor"),
                "city": analysis.city or listing.get("city"),
                "neighborhood": analysis.neighborhood or listing.get("neighborhood"),
                "summary": analysis.summary or listing.get("summary"),
            }
        )
        enriched.append(merged)
    return enriched
