"""Apartment listing scraper: live web sources + Apify social + mock fallback."""

from __future__ import annotations

import os
import re
import uuid
from html import unescape
from typing import Any, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CITY_ALIASES = {
    "תל אביב": ["תל אביב", "תל אביב יפו", "ת\"א", "תא"],
    "רמת גן": ["רמת גן"],
    "גבעתיים": ["גבעתיים"],
    "חיפה": ["חיפה"],
    "ירושלים": ["ירושלים"],
    "חולון": ["חולון"],
    "בת ים": ["בת ים"],
    "פתח תקווה": ["פתח תקווה", "פתח תקוה"],
    "רמלה": ["רמלה", "Ramla", "Ramle", "ramla"],
    "לוד": ["לוד", "Lod", "lod"],
    "באר שבע": ["באר שבע"],
    "נתניה": ["נתניה"],
    "הרצליה": ["הרצליה"],
    "ראשון לציון": ["ראשון לציון", "ראשל\"צ"],
    "אשדוד": ["אשדוד"],
    "אשקלון": ["אשקלון"],
    "בני ברק": ["בני ברק"],
    "מודיעין": ["מודיעין"],
    "כפר סבא": ["כפר סבא"],
    "רעננה": ["רעננה"],
}

MOCK_LISTINGS: list[dict[str, Any]] = [
    {
        "external_id": "mock-001",
        "url": "https://www.facebook.com/groups/tlv.apartments/posts/1001001",
        "title": "דירת 3 חדרים מוארת בתל אביב – בעל דירה",
        "description": (
            "שלום! אני בעל הדירה (לא תיווך). משכיר דירת 3 חדרים ברחוב דיזנגוף, "
            "קומה 3 עם מרפסת שמש. מחיר 7,800 ₪ כולל ועד בית. כניסה מיידית. "
            "מתאים לזוג או שותפים שקטים. בלי עמלות!"
        ),
        "city": "תל אביב",
        "neighborhood": "לב העיר",
        "price": 7800,
        "rooms": 3.0,
        "floor": 3,
        "source": "Facebook Groups",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "דירת 3 חדרים מבעל דירה בלב תל אביב, קומה 3, ללא תיווך.",
    },
    {
        "external_id": "mock-002",
        "url": "https://www.facebook.com/marketplace/item/2202002",
        "title": "2.5 חדרים ברמת גן – בלעדיות למשרד",
        "description": (
            "משרד תיווך 'נדל״ן פלוס' מציע דירת 2.5 חדרים ברחוב ביאליק, רמת גן. "
            "קומה 2 בבניין עם מעלית. מחיר 6,200 ₪. יש בלעדיות לדירה. "
            "עמלת תיווך חודש שכירות. לפרטים נוספים התקשרו למשרד."
        ),
        "city": "רמת גן",
        "neighborhood": "ביאליק",
        "price": 6200,
        "rooms": 2.5,
        "floor": 2,
        "source": "Facebook Marketplace",
        "is_realtor": True,
        "realtor_reason": "משרד תיווך עם בלעדיות ועמלת תיווך",
        "summary": "דירת 2.5 חדרים ברמת גן דרך משרד תיווך, קומה 2.",
    },
    {
        "external_id": "mock-003",
        "url": "https://www.yad2.co.il/realestate/rent/3303003",
        "title": "דירת גן 4 חדרים בגבעתיים",
        "description": (
            "אנחנו הזוג שגר בדירה ועוברים לחו״ל – משכירים ישירות בלי מתווך. "
            "4 חדרים + גינה פרטית קטנה ברחוב כצנלסון, גבעתיים. קומת קרקע. "
            "מחיר 9,500 ₪. חניה פרטית כלולה. כניסה לחודש הבא."
        ),
        "city": "גבעתיים",
        "neighborhood": "כצנלסון",
        "price": 9500,
        "rooms": 4.0,
        "floor": 0,
        "source": "Yad2",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "דירת גן 4 חדרים בגבעתיים ישירות מהשוכרים הנוכחיים, ללא תיווך.",
    },
    {
        "external_id": "mock-004",
        "url": "https://www.facebook.com/groups/haifa.rentals/posts/4404004",
        "title": "סטודיו בחיפה – נוף לים",
        "description": (
            "דירת סטודיו משופצת בכרמל, חיפה. קומה 5 עם נוף פתוח לים. "
            "מחיר 4,200 ₪. אני המשכיר הפרטי, אפשר לתאם ביקור בסופ״ש. "
            "מתאים לסטודנט/ית או איש/אשת מקצוע יחיד/ה."
        ),
        "city": "חיפה",
        "neighborhood": "כרמל",
        "price": 4200,
        "rooms": 1.0,
        "floor": 5,
        "source": "Facebook Groups",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "סטודיו משופץ בכרמל עם נוף לים, משכיר פרטי.",
    },
    {
        "external_id": "mock-005",
        "url": "https://www.yad2.co.il/realestate/rent/5505005",
        "title": "3 חדרים בתל אביב – אזור פלורנטין",
        "description": (
            "סוכן נדל״ן מורשה מציע דירה מקסימה בפלורנטין. 3 חדרים, קומה 1, "
            "משופצת לאחרונה. מחיר 8,900 ₪. יש עמלת תיווך. "
            "הדירה בבלעדיות של המשרד שלנו. לתיאום סיורים בלבד דרך הסוכן."
        ),
        "city": "תל אביב",
        "neighborhood": "פלורנטין",
        "price": 8900,
        "rooms": 3.0,
        "floor": 1,
        "source": "Yad2",
        "is_realtor": True,
        "realtor_reason": "סוכן נדל״ן עם עמלת תיווך ובלעדיות",
        "summary": "דירת 3 חדרים בפלורנטין דרך סוכן נדל״ן, קומה 1.",
    },
    {
        "external_id": "mock-006",
        "url": "https://www.facebook.com/marketplace/item/6606006",
        "title": "דירת שותפים 5 חדרים ברמת גן",
        "description": (
            "מחפשים שותף/ה לחדר גדול בדירת 5 חדרים ברמת גן (רחוב הרצל). "
            "קומה 4. החדר פנוי – שכירות 2,800 ₪ + חשבונות. "
            "אנחנו שוכרים ישירות מבעל הבית, בלי תיווך בכלל. אווירה טובה ושקטה."
        ),
        "city": "רמת גן",
        "neighborhood": "הרצל",
        "price": 2800,
        "rooms": 5.0,
        "floor": 4,
        "source": "Facebook Marketplace",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "חדר בשותפות בדירת 5 חדרים ברמת גן, ללא תיווך.",
    },
    {
        "external_id": "mock-007",
        "url": "https://www.facebook.com/groups/givatayim.housing/posts/7707007",
        "title": "2 חדרים בגבעתיים – קרוב לרכבת",
        "description": (
            "דירת 2 חדרים קומפקטית ברחוב בורוכוב, גבעתיים. קומה 2. "
            "מחיר 5,900 ₪. בעלת הדירה מדברת עברית ואנגלית. "
            "אין מתווכים – רק פניות ישירות. כניסה גמישה."
        ),
        "city": "גבעתיים",
        "neighborhood": "בורוכוב",
        "price": 5900,
        "rooms": 2.0,
        "floor": 2,
        "source": "Facebook Groups",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "דירת 2 חדרים בגבעתיים מבעלת דירה, קרוב לרכבת.",
    },
    {
        "external_id": "mock-008",
        "url": "https://www.yad2.co.il/realestate/rent/8808008",
        "title": "פנטהאוז 4.5 חדרים בחיפה",
        "description": (
            "משרד 'חיפה נכסים' מציג פנטהאוז מרהיב בנווה שאנן. "
            "4.5 חדרים, קומה 8 + גג פרטי. מחיר 11,000 ₪. "
            "כולל חניה ומחסן. יש עמלת תיווך כמקובל. לתיאום סיור עם נציג המשרד."
        ),
        "city": "חיפה",
        "neighborhood": "נווה שאנן",
        "price": 11000,
        "rooms": 4.5,
        "floor": 8,
        "source": "Yad2",
        "is_realtor": True,
        "realtor_reason": "משרד נכסים עם עמלת תיווך",
        "summary": "פנטהאוז 4.5 חדרים בנווה שאנן דרך משרד תיווך.",
    },
    {
        "external_id": "mock-009",
        "url": "https://www.facebook.com/marketplace/item/9909009",
        "title": "דירת 3.5 חדרים בתל אביב – צפון ישן",
        "description": (
            "שלום לכולם 🙂 משכירים את הדירה שלנו לפני מעבר לחו״ל. "
            "3.5 חדרים בצפון הישן, רחוב בן יהודה. קומה 4 עם מעלית. "
            "מחיר 8,200 ₪. ריהוט חלקי נשאר. בבקשה בלי מתווכים – רק שוכרים רציניים."
        ),
        "city": "תל אביב",
        "neighborhood": "צפון ישן",
        "price": 8200,
        "rooms": 3.5,
        "floor": 4,
        "source": "Facebook Marketplace",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "דירת 3.5 חדרים בצפון הישן ישירות מהשוכרים, ללא מתווכים.",
    },
    {
        "external_id": "mock-010",
        "url": "https://www.facebook.com/groups/tlv.apartments/posts/1010010",
        "title": "יחידת דיור ברמת גן – מאחורי בית פרטי",
        "description": (
            "יחידת דיור נפרדת מאחורי בית פרטי ברמת גן (אזור הבילויים). "
            "חדר + מטבחון ושירותים, כניסה נפרדת. מחיר 3,900 ₪ כולל חשמל ומים. "
            "אני בעלת הבית – אין תיווך ואין עמלות. מתאים לסטודנט/ית שקטה."
        ),
        "city": "רמת גן",
        "neighborhood": "הבילויים",
        "price": 3900,
        "rooms": 1.5,
        "floor": 0,
        "source": "Facebook Groups",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "יחידת דיור פרטית ברמת גן מבעלת הבית, כולל חשבונות.",
    },
    {
        "external_id": "mock-011",
        "url": "https://www.yad2.co.il/realestate/rent/1111011",
        "title": "4 חדרים בגבעתיים – דירת משפחה",
        "description": (
            "דירת משפחה מרווחת ברחוב קפלן, גבעתיים. 4 חדרים, קומה 3, "
            "מרפסת שירות + מרפסת שמש. מחיר 10,200 ₪. "
            "הדירה משווקת דרך סוכנות תיווך מקומית עם בלעדיות. "
            "לתיאום ביקור יש ליצור קשר עם המשרד."
        ),
        "city": "גבעתיים",
        "neighborhood": "קפלן",
        "price": 10200,
        "rooms": 4.0,
        "floor": 3,
        "source": "Yad2",
        "is_realtor": True,
        "realtor_reason": "סוכנות תיווך עם בלעדיות",
        "summary": "דירת משפחה 4 חדרים בגבעתיים דרך סוכנות תיווך.",
    },
    {
        "external_id": "mock-012",
        "url": "https://www.facebook.com/groups/haifa.rentals/posts/1212012",
        "title": "2 חדרים בחיפה – הדר הכרמל",
        "description": (
            "דירה חמודה של 2 חדרים בהדר, חיפה. קומה 1 בבניין ישן ומקסים. "
            "מחיר 3,600 ₪. אני גרה בקומה מעל ומחפשת שוכר/ת שקט/ה. "
            "אין משרד תיווך באמצע – הכל ישירות מולי. אפשר לבוא לראות מחר."
        ),
        "city": "חיפה",
        "neighborhood": "הדר",
        "price": 3600,
        "rooms": 2.0,
        "floor": 1,
        "source": "Facebook Groups",
        "is_realtor": False,
        "realtor_reason": "",
        "summary": "דירת 2 חדרים בהדר מבעלת דירה שגרה בבניין, ללא תיווך.",
    },
]


def _token_present(token: Optional[str]) -> bool:
    return bool(token and token.strip() and token.strip() not in {'""', "''"})


def get_apify_token() -> str:
    return (os.getenv("APIFY_API_TOKEN") or "").strip().strip('"').strip("'")


def fetch_mock_listings() -> list[dict[str, Any]]:
    return [dict(item) for item in MOCK_LISTINGS]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def _parse_int_price(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw == "":
        return None
    text = str(raw)
    # Prefer explicit currency amounts in free text.
    match = re.search(
        r"(\d{1,2}(?:[,\.]\d{3})|\d{3,5})(?:\.\d+)?\s*(?:₪|ש\"?ח|ILS)?",
        text.replace(" ", ""),
    )
    candidate = match.group(1) if match else text
    candidate = (
        candidate.replace(",", "")
        .replace("₪", "")
        .replace('ש"ח', "")
        .replace("שח", "")
        .strip()
    )
    try:
        value = int(float(candidate))
    except (TypeError, ValueError):
        return None
    if 1000 <= value <= 40000:
        return value
    return None


def _parse_rooms(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d)?)\s*חדר", text or "")
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


def _parse_floor(text: str) -> Optional[int]:
    if re.search(r"קומת?\s*קרקע|דירת\s*גן", text or ""):
        return 0
    match = re.search(r"קומה\s*(\d{1,2})", text or "")
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def _city_matches(text: str, city: str) -> bool:
    if not city or not city.strip():
        return True
    hay = text or ""
    needle = city.strip()
    if needle in hay:
        return True
    for canonical, aliases in CITY_ALIASES.items():
        if needle == canonical or needle in aliases:
            return any(alias in hay for alias in aliases)
    return needle in hay


def _clean_city_value(text: str) -> str:
    value = re.sub(r"[\u0591-\u05C7\u200e\u200f\u202a-\u202e]+", "", text or "")
    return re.sub(r"\s+", " ", value).strip()


def _normalize_city_from_text(text: str, fallback: str = "") -> str:
    cleaned = _clean_city_value(text)
    # Prefer exact/alias matches on longer names first.
    for canonical, aliases in sorted(
        CITY_ALIASES.items(), key=lambda kv: max(len(a) for a in kv[1]), reverse=True
    ):
        for alias in aliases:
            if alias and alias in cleaned:
                return canonical
    return _clean_city_value(fallback)


def _city_from_homeless_title(title: str, fallback: str = "") -> tuple[str, str]:
    """Parse 'type, rooms, street, city' titles. Returns (city, neighborhood)."""
    parts = [_clean_city_value(p) for p in (title or "").split(",") if _clean_city_value(p)]
    if not parts:
        return _normalize_city_from_text(title, fallback), ""
    last = parts[-1]
    city = _normalize_city_from_text(last, "")
    if not city and last:
        city = last
    if not city:
        city = _normalize_city_from_text(title, fallback)
    neighborhood = parts[-2] if len(parts) >= 3 else ""
    return city, neighborhood


def _http_get(url: str, timeout: int = 35) -> Optional[str]:
    try:
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=timeout)
        if response.status_code == 200 and response.text:
            return response.text
    except requests.RequestException:
        return None
    return None


FOCUS_REGION_CITIES = ["רמלה", "לוד"]

REGION_QUERY_VARIANTS = {
    "רמלה": [
        "רמלה",
        "רמלה דירה",
        "יחידת דיור רמלה",
        "יחידה רמלה",
        "דירת גן רמלה",
        "קומת קרקע רמלה",
        "קריית מנחם רמלה",
        "נווה מאיר רמלה",
        "רמלה להשכרה",
    ],
    "לוד": [
        "לוד",
        "לוד דירה",
        "יחידת דיור לוד",
        "יחידה לוד",
        "דירת גן לוד",
        "קומת קרקע לוד",
        "גני אביב לוד",
        "נווה זית לוד",
        "לוד רסקו",
        "לוד להשכרה",
    ],
}


def scrape_homeless(city: str = "תל אביב", max_items: int = 40) -> list[dict[str, Any]]:
    """Scrape live rental ads from homeless.co.il (Israeli classifieds board)."""
    city_q = (city or "תל אביב").strip() or "תל אביב"
    urls = [
        f"https://www.homeless.co.il/rent/city={quote(city_q)}",
        f"https://www.homeless.co.il/rent/?city={quote(city_q)}",
        f"https://www.homeless.co.il/rent/{quote(city_q.replace(' ', '_'))}/",
    ]

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    priced_pattern = re.compile(
        r'href="(/rent/viewad,(\d+)\.aspx)" title="([^"]+)"'
        r'[\s\S]{0,1200}?<div class="price">\s*([\d,]+)\s*₪'
        r'(?:[\s\S]{0,500}?<h3 class="desc"[^>]*>([\s\S]*?)</h3>)?',
        re.I,
    )
    title_only_pattern = re.compile(
        r'href="(/rent/viewad,(\d+)\.aspx)" title="([^"]+)"',
        re.I,
    )

    for url in urls:
        html = _http_get(url)
        if not html or "viewad," not in html:
            continue

        matches = list(priced_pattern.finditer(html))
        if not matches:
            # Fallback: titles without a reliably-parsed price block.
            for match in title_only_pattern.finditer(html):
                path, ad_id, title = match.groups()
                if ad_id in seen:
                    continue
                title = _clean_text(title)
                if city_q and not _city_matches(title, city_q):
                    continue
                detected_city, neighborhood = _city_from_homeless_title(title, city_q)
                listing = {
                    "external_id": f"homeless-{ad_id}",
                    "url": f"https://www.homeless.co.il{path}",
                    "title": title or f"דירה להשכרה ב{detected_city}",
                    "description": title,
                    "city": detected_city or city_q,
                    "neighborhood": neighborhood,
                    "price": None,
                    "rooms": _parse_rooms(title),
                    "floor": _parse_floor(title),
                    "source": "Homeless",
                    "is_realtor": None,
                    "realtor_reason": "",
                    "summary": "",
                }
                results.append(listing)
                seen.add(ad_id)
                if len(results) >= max_items:
                    return results
            continue

        for match in matches:
            path, ad_id, title, price_raw, desc_html = match.groups()
            if ad_id in seen:
                continue
            title = _clean_text(title)
            desc = _clean_text(desc_html or "")
            blob = f"{title} {desc}"
            detected_city, neighborhood = _city_from_homeless_title(title, "")
            if not detected_city:
                detected_city = _normalize_city_from_text(blob, "")

            if city_q and city_q not in ("", "ישראל"):
                if not (
                    _city_matches(detected_city, city_q) or _city_matches(blob, city_q)
                ):
                    continue

            listing = {
                "external_id": f"homeless-{ad_id}",
                "url": f"https://www.homeless.co.il{path}",
                "title": title or f"דירה להשכרה ב{detected_city}",
                "description": desc or title,
                "city": detected_city or city_q,
                "neighborhood": neighborhood,
                "price": _parse_int_price(price_raw),
                "rooms": _parse_rooms(blob),
                "floor": _parse_floor(blob),
                "source": "Homeless",
                "is_realtor": None,
                "realtor_reason": "",
                "summary": "",
            }
            results.append(listing)
            seen.add(ad_id)
            if len(results) >= max_items:
                return results

    return results


def _parse_ad_cards_from_html(
    html: str,
    *,
    preferred_city: str = "",
    allowed_cities: Optional[list[str]] = None,
    seen: Optional[set[str]] = None,
    max_items: int = 80,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen = seen if seen is not None else set()
    allowed = allowed_cities or ([preferred_city] if preferred_city else [])

    for match in re.finditer(r'<div class="card-block"[^>]*data-id="(\d+)"', html):
        ad_id = match.group(1)
        if ad_id in seen:
            continue
        chunk = html[match.start() : match.start() + 2500]

        title_m = re.search(
            rf'<a href="/ad/{ad_id}"[\s\S]*?<h2[^>]*>([\s\S]*?)</h2>', chunk
        )
        price_m = re.search(r'class="price[^"]*">\s*([\d,]+)\s*₪', chunk)
        rooms_m = re.search(
            r'<i class="fa fa-bed"></i>\s*<span class="ms-1">(\d+(?:\.\d)?)', chunk
        )
        addr_m = re.search(r'<p class="[^"]*mb-1 mt-0[^"]*">\s*([^<]+)', chunk)

        title = _clean_text(title_m.group(1)) if title_m else ""
        addr = _clean_text(addr_m.group(1)) if addr_m else ""
        blob = f"{title} {addr}"

        detected_city = _normalize_city_from_text(blob, "")
        neighborhood = ""
        if title:
            for canonical, aliases in CITY_ALIASES.items():
                for alias in aliases:
                    if title.startswith(alias):
                        neighborhood = title[len(alias) :].strip(" ;|-")
                        detected_city = canonical
                        break

        if allowed:
            # Match against title/city only (not full HTML chunk — avoids bleed from neighbors).
            if not any(
                _city_matches(detected_city, c) or _city_matches(title, c) for c in allowed
            ):
                if preferred_city and not detected_city and not _normalize_city_from_text(title, ""):
                    detected_city = preferred_city
                else:
                    continue
        elif preferred_city and not detected_city:
            detected_city = preferred_city

        rooms = float(rooms_m.group(1)) if rooms_m else _parse_rooms(blob)
        description = " · ".join(
            x for x in [title, addr, f"{rooms} חדרים" if rooms else ""] if x
        )
        listing = {
            "external_id": f"ad-{ad_id}",
            "url": f"https://www.ad.co.il/ad/{ad_id}",
            "title": title or f"דירה להשכרה ב{detected_city or 'ישראל'}",
            "description": description,
            "city": detected_city or preferred_city,
            "neighborhood": neighborhood or addr,
            "price": _parse_int_price(price_m.group(1) if price_m else None),
            "rooms": rooms,
            "floor": None,
            "source": "Ad.co.il",
            "is_realtor": None,
            "realtor_reason": "",
            "summary": "",
        }
        results.append(listing)
        seen.add(ad_id)
        if len(results) >= max_items:
            break

    return results


def scrape_ad_co_il(city: str = "תל אביב", max_items: int = 40) -> list[dict[str, Any]]:
    """Scrape live rental ads from ad.co.il for one city (with query variants)."""
    city_q = (city or "").strip()
    queries = REGION_QUERY_VARIANTS.get(city_q, [city_q] if city_q else [""])
    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    for q in queries:
        url = (
            f"https://www.ad.co.il/nadlanrent?q={quote(q)}"
            if q
            else "https://www.ad.co.il/nadlanrent"
        )
        html = _http_get(url)
        if not html:
            continue
        batch = _parse_ad_cards_from_html(
            html,
            preferred_city=city_q,
            allowed_cities=[city_q] if city_q else None,
            seen=seen,
            max_items=max_items,
        )
        results.extend(batch)
        if len(results) >= max_items:
            break

    return results[:max_items]


def _infer_property_type(text: str) -> str:
    value = text or ""
    if "יחידת דיור" in value or "יחידה" in value:
        return "יחידת דיור"
    if "דירת גן" in value:
        return "דירת גן"
    if "דירה" in value:
        return "דירה"
    return ""


def enrich_listing_from_detail(listing: dict[str, Any]) -> dict[str, Any]:
    """Fetch Ad.co.il/Homeless detail page to fill floor/property_type/rooms."""
    url = listing.get("url") or ""
    if not url.startswith("http"):
        return listing

    html = _http_get(url, timeout=25)
    if not html:
        return listing

    plain = _clean_text(html)
    updated = dict(listing)

    # Floor
    if updated.get("floor") is None:
        if re.search(r"קומת?\s*קרקע|דירת\s*גן", plain):
            updated["floor"] = 0
        else:
            floor_match = re.search(r"קומה\s*(\d{1,2})", plain)
            if floor_match:
                try:
                    updated["floor"] = int(floor_match.group(1))
                except ValueError:
                    pass

    # Rooms — prefer explicit "X חדרים" near the start of the page title area
    if updated.get("rooms") is None:
        rooms_match = re.search(r"(\d+(?:\.\d)?)\s*חדרים", plain)
        if rooms_match:
            try:
                updated["rooms"] = float(rooms_match.group(1))
            except ValueError:
                pass

    # Property type
    ptype = _infer_property_type(plain) or _infer_property_type(
        f"{updated.get('title') or ''} {updated.get('description') or ''}"
    )
    if ptype:
        updated["property_type"] = ptype
        # Keep type visible in title for UI badges/search
        title = updated.get("title") or ""
        if ptype == "יחידת דיור" and "יחיד" not in title:
            updated["title"] = f"יחידת דיור · {title}" if title else "יחידת דיור"
        if ptype == "דירת גן" and "גן" not in title:
            updated["title"] = f"דירת גן · {title}" if title else "דירת גן"

    # Price fallback from detail text
    if updated.get("price") is None:
        price_match = re.search(r"([\d,]{3,5})\s*₪", plain)
        if price_match:
            updated["price"] = _parse_int_price(price_match.group(1))

    # Append a short detail snippet into description for keyword search
    snippet_bits = []
    if updated.get("property_type"):
        snippet_bits.append(updated["property_type"])
    if updated.get("floor") == 0:
        snippet_bits.append("קומת קרקע")
    elif updated.get("floor") is not None:
        snippet_bits.append(f"קומה {updated['floor']}")
    if snippet_bits:
        base = updated.get("description") or updated.get("title") or ""
        updated["description"] = f"{base} · " + " · ".join(snippet_bits)

    return updated


def enrich_listings_details(
    listings: list[dict[str, Any]], *, limit: int = 40
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for idx, item in enumerate(listings):
        if idx < limit and (item.get("source") in {"Ad.co.il", "Homeless"}):
            enriched.append(enrich_listing_from_detail(item))
        else:
            # Still infer type from existing text
            ptype = item.get("property_type") or _infer_property_type(
                f"{item.get('title') or ''} {item.get('description') or ''}"
            )
            copy = dict(item)
            if ptype:
                copy["property_type"] = ptype
            if copy.get("floor") is None:
                copy["floor"] = _parse_floor(
                    f"{copy.get('title') or ''} {copy.get('description') or ''}"
                )
            enriched.append(copy)
    return enriched


def scrape_focus_region(
    cities: Optional[list[str]] = None,
    max_items_per_city: int = 50,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Deep scrape for a focus region (default: Ramla + Lod)."""
    target_cities = cities or FOCUS_REGION_CITIES
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    stats: dict[str, int] = {}

    for city in target_cities:
        before = len(combined)
        for item in scrape_homeless(city=city, max_items=max_items_per_city):
            key = item.get("url") or item.get("external_id")
            if key in seen:
                continue
            seen.add(key)
            combined.append(item)
        homeless_added = len(combined) - before

        before = len(combined)
        for item in scrape_ad_co_il(city=city, max_items=max_items_per_city):
            key = item.get("url") or item.get("external_id")
            if key in seen:
                continue
            seen.add(key)
            combined.append(item)
        ad_added = len(combined) - before
        stats[city] = homeless_added + ad_added
        stats[f"{city}-Homeless"] = homeless_added
        stats[f"{city}-Ad"] = ad_added

    # Enrich with floor / unit type from detail pages
    combined = enrich_listings_details(combined, limit=min(60, len(combined)))
    stats["enriched_details"] = min(60, len(combined))
    return combined, stats


def _extract_run_dataset_id(run: Any) -> Optional[str]:
    if run is None:
        return None
    if isinstance(run, dict):
        return run.get("defaultDatasetId") or run.get("default_dataset_id")
    dataset_id = getattr(run, "default_dataset_id", None) or getattr(
        run, "defaultDatasetId", None
    )
    if dataset_id:
        return dataset_id
    dump = getattr(run, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data.get("default_dataset_id") or data.get("defaultDatasetId")
    return None


def _normalize_apify_item(item: dict[str, Any], source: str) -> dict[str, Any]:
    description_raw = item.get("description")
    if isinstance(description_raw, dict):
        text = description_raw.get("text") or ""
    else:
        text = (
            description_raw
            or item.get("text")
            or item.get("title")
            or item.get("listingTitle")
            or item.get("caption")
            or ""
        )

    title = (
        item.get("listingTitle")
        or item.get("title")
        or item.get("name")
        or (text[:80] if text else "מודעה מפייסבוק")
    )

    url = (
        item.get("itemUrl")
        or item.get("listingUrl")
        or item.get("url")
        or item.get("postUrl")
        or item.get("facebookUrl")
        or f"https://www.facebook.com/marketplace/item/{item.get('id') or uuid.uuid4().hex[:8]}"
    )

    external_id = str(
        item.get("id")
        or item.get("postId")
        or item.get("adId")
        or item.get("listingId")
        or url
    )

    price_raw = item.get("listingPrice") or item.get("price") or item.get("amount")
    if isinstance(price_raw, dict):
        price_raw = price_raw.get("amount") or price_raw.get("formatted_amount")
    price = _parse_int_price(str(price_raw) if price_raw not in (None, "") else None)
    if price is None:
        price = _parse_int_price(f"{title} {text}")

    location = item.get("location") or {}
    city = ""
    if isinstance(location, dict):
        geo = location.get("reverse_geocode_detailed") or location.get("reverse_geocode") or {}
        if isinstance(geo, dict):
            city = geo.get("city") or ""
        if not city:
            city = location.get("city") or location.get("name") or ""
    elif isinstance(location, str):
        city = location
    # Prefer city mentioned in the Hebrew text for local ads.
    city = _normalize_city_from_text(f"{title} {text}", "") or _normalize_city_from_text(
        city, city or ""
    )

    rooms = item.get("rooms") or item.get("bedrooms")
    if rooms is None:
        rooms = _parse_rooms(f"{title} {text}")
    # Marketplace often uses "X beds"
    if rooms is None:
        beds = re.search(r"(\d+)\s*beds?", f"{title} {text}", re.I)
        if beds:
            try:
                rooms = float(beds.group(1))
            except ValueError:
                rooms = None

    floor = item.get("floor")
    if floor is None:
        floor = _parse_floor(f"{title} {text}")

    property_type = _infer_property_type(f"{title} {text}")
    blob_lower = f"{title} {text}"
    # Skip obvious non-rentals when possible
    if re.search(r"למכירה|for\s*sale", blob_lower, re.I) and not re.search(
        r"להשכרה|for\s*rent", blob_lower, re.I
    ):
        return {}
    if re.search(r"חנות|משרד|מחסן|עסק", blob_lower) and not re.search(
        r"דירה|יחיד|חדרים", blob_lower
    ):
        return {}

    return {
        "external_id": f"fb-{external_id}",
        "url": url,
        "title": title,
        "description": text or title,
        "city": city,
        "neighborhood": item.get("neighborhood") or item.get("area") or "",
        "price": price,
        "rooms": rooms,
        "floor": floor,
        "property_type": property_type,
        "source": source,
        "is_realtor": None,
        "realtor_reason": "",
        "summary": "",
    }


def _facebook_query_variants(cities: list[str]) -> list[str]:
    """Broad Hebrew/English query set so we miss fewer Marketplace ads."""
    english = {"רמלה": ["Ramla", "Ramle"], "לוד": ["Lod", "Lydda"]}
    queries: list[str] = []
    for city in cities:
        queries.extend(
            [
                f"דירה להשכרה {city}",
                f"דירה {city} להשכרה",
                f"יחידת דיור {city}",
                f"יחידה להשכרה {city}",
                f"דירת גן {city}",
                f"קומת קרקע {city}",
                f"דירת 3 חדרים {city}",
                f"3 חדרים להשכרה {city}",
                f"להשכרה {city}",
                f"דירה עד 3500 {city}",
                f"השכרה פרטי {city}",
            ]
        )
        for en in english.get(city, []):
            queries.extend(
                [
                    f"apartment for rent {en}",
                    f"rent {en}",
                    f"apartment {en}",
                    f"studio {en}",
                ]
            )
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def _facebook_marketplace_urls(cities: list[str]) -> list[dict[str, str]]:
    """Build many Marketplace search URLs across nearby hubs."""
    hubs = [
        "telaviv",
        "jerusalem",
        "rishonlezion",
        "rehovot",
        "modiin",
    ]
    urls: list[dict[str, str]] = []
    for q in _facebook_query_variants(cities):
        encoded = quote(q)
        for hub in hubs:
            urls.append(
                {"url": f"https://www.facebook.com/marketplace/{hub}/search/?query={encoded}"}
            )
            urls.append(
                {
                    "url": (
                        f"https://www.facebook.com/marketplace/{hub}/propertyrentals"
                        f"?query={encoded}"
                    )
                }
            )
    return urls


def _run_facebook_marketplace_batch(
    client: Any,
    start_urls: list[dict[str, str]],
    *,
    results_limit: int,
    wait_secs: int = 300,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Run one Apify Marketplace actor batch and return raw items + notes."""
    from datetime import timedelta

    notes: list[str] = []
    run_input = {
        "startUrls": start_urls,
        "resultsLimit": results_limit,
        "includeListingDetails": True,
        "searchCount": results_limit,
    }
    try:
        run = client.actor("apify/facebook-marketplace-scraper").call(
            run_input=run_input,
            wait_duration=timedelta(seconds=wait_secs),
            run_timeout=timedelta(seconds=wait_secs),
            memory_mbytes=2048,
        )
    except Exception as exc:
        err_name = type(exc).__name__
        notes.append(f"שגיאת Apify Marketplace: {err_name}")
        if "Forbidden" in err_name or "Rate" in err_name:
            notes.append("Apify חסם זמנית (מכסה/קצב). נסה שוב בעוד כמה דקות.")
        return [], notes

    dataset_id = _extract_run_dataset_id(run)
    if not dataset_id:
        notes.append("Apify Marketplace רץ אך לא החזיר dataset")
        return [], notes

    items: list[dict[str, Any]] = []
    for item in client.dataset(dataset_id).iterate_items(limit=max(results_limit * 3, 100)):
        if isinstance(item, dict):
            items.append(item)
    return items, notes


def scrape_facebook_marketplace(
    *,
    cities: Optional[list[str]] = None,
    max_items: int = 120,
    focus_region: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Scrape Facebook Marketplace via Apify for the focus cities (deep scan)."""
    meta: dict[str, Any] = {"notes": [], "count": 0, "batches": 0}
    token = get_apify_token()
    if not _token_present(token):
        meta["notes"].append("חסר APIFY_API_TOKEN לסריקת פייסבוק")
        return [], meta

    try:
        from apify_client import ApifyClient
    except ImportError:
        meta["notes"].append("חסרה חבילת apify-client")
        return [], meta

    target_cities = cities or list(FOCUS_REGION_CITIES)
    client = ApifyClient(token)
    all_urls = _facebook_marketplace_urls(target_cities)
    # Prefer high-signal hubs first (telaviv/propertyrentals + search).
    preferred = [u for u in all_urls if "/telaviv/" in u.get("url", "")]
    ordered = preferred + [u for u in all_urls if u not in preferred]
    # 3 batches × 8 URLs balances coverage vs Apify rate limits.
    batch_size = 8
    max_urls = 24
    batches = [
        ordered[i : i + batch_size]
        for i in range(0, min(len(ordered), max_urls), batch_size)
    ]
    if not batches:
        batches = [ordered[:8]]

    raw_items: list[dict[str, Any]] = []
    for batch in batches:
        items, notes = _run_facebook_marketplace_batch(
            client,
            batch,
            results_limit=max(max_items, 100),
            wait_secs=280,
        )
        meta["batches"] += 1
        meta["notes"].extend(notes)
        raw_items.extend(items)
        if any("Forbidden" in n or "Rate" in n for n in notes):
            # Stop early on rate-limit to preserve quota; keep what we have.
            break

    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = _normalize_apify_item(item, "Facebook Marketplace")
        if not normalized:
            continue
        if focus_region:
            blob = (
                f"{normalized.get('city') or ''} "
                f"{normalized.get('title') or ''} "
                f"{normalized.get('description') or ''} "
                f"{normalized.get('neighborhood') or ''}"
            )
            if not any(_city_matches(blob, c) for c in target_cities):
                continue
        key = normalized.get("url") or normalized.get("external_id")
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(normalized)
        if len(results) >= max_items:
            break

    meta["count"] = len(results)
    meta["notes"].append(
        f"פייסבוק: {meta['batches']} סבבים · {len(raw_items)} גולמי · {len(results)} באזור"
    )
    if not results:
        meta["notes"].append("Marketplace לא החזיר מודעות באזור רמלה/לוד")
    return results, meta


def scrape_with_apify(
    *,
    city: str = "רמלה",
    cities: Optional[list[str]] = None,
    max_items: int = 40,
    sources: Optional[set[str]] = None,
    focus_region: bool = True,
) -> list[dict[str, Any]]:
    """Scrape Facebook Marketplace (and optionally other Apify sources)."""
    wanted = sources or {"facebook_marketplace"}
    target_cities = cities or (
        list(FOCUS_REGION_CITIES)
        if focus_region or city in FOCUS_REGION_CITIES
        else [city]
    )
    results: list[dict[str, Any]] = []

    if "facebook_marketplace" in wanted or "facebook_groups" in wanted:
        # Groups often require login; Marketplace works with the official actor.
        fb_items, _meta = scrape_facebook_marketplace(
            cities=target_cities,
            max_items=max_items,
            focus_region=focus_region,
        )
        results.extend(fb_items)

    return results


def scrape_web_sources(
    *,
    city: str = "רמלה",
    cities: Optional[list[str]] = None,
    max_items: int = 50,
    include_homeless: bool = True,
    include_ad: bool = True,
    focus_region: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Fetch listings from public Israeli classified websites."""
    target_cities = cities or []
    if not target_cities:
        if focus_region or city in FOCUS_REGION_CITIES or city in {"רמלה לוד", "לוד רמלה"}:
            target_cities = list(FOCUS_REGION_CITIES)
        elif city:
            target_cities = [city]
        else:
            target_cities = list(FOCUS_REGION_CITIES)

    # Deep region scrape when focusing on Ramla/Lod.
    if focus_region and set(target_cities).issubset(set(FOCUS_REGION_CITIES)):
        return scrape_focus_region(
            cities=target_cities, max_items_per_city=max_items
        )

    results: list[dict[str, Any]] = []
    stats: dict[str, int] = {}
    seen: set[str] = set()

    for target in target_cities:
        if include_homeless:
            for item in scrape_homeless(city=target, max_items=max_items):
                key = item.get("url") or item.get("external_id")
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
                stats["Homeless"] = stats.get("Homeless", 0) + 1
        if include_ad:
            for item in scrape_ad_co_il(city=target, max_items=max_items):
                key = item.get("url") or item.get("external_id")
                if key in seen:
                    continue
                seen.add(key)
                results.append(item)
                stats["Ad.co.il"] = stats.get("Ad.co.il", 0) + 1

    return results, stats


def fetch_listings(
    *,
    mock_mode: bool = False,
    city: str = "רמלה",
    cities: Optional[list[str]] = None,
    max_items: int = 50,
    use_web: bool = True,
    use_social: bool = True,
    use_yad2: bool = True,
    focus_region: bool = True,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """
    Fetch listings from the internet / social networks.
    Returns (listings, mode_label, meta).
    """
    meta: dict[str, Any] = {"sources": {}, "notes": []}

    if mock_mode:
        return fetch_mock_listings(), "mock", {
            "sources": {"Mock": 12},
            "notes": ["מצב דמו פעיל"],
        }

    combined: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def _extend(items: list[dict[str, Any]]) -> None:
        for item in items:
            url = (item.get("url") or "").strip()
            ext = (item.get("external_id") or "").strip()
            key = url or ext
            if key and key in seen_urls:
                continue
            if key:
                seen_urls.add(key)
            combined.append(item)

    if use_web:
        web_items, web_stats = scrape_web_sources(
            city=city,
            cities=cities,
            max_items=max_items,
            focus_region=focus_region,
        )
        meta["sources"].update(web_stats)
        _extend(web_items)
        if focus_region:
            meta["notes"].append("מיקוד אזור: רמלה + לוד")

    if use_social:
        if _token_present(get_apify_token()):
            target = cities or (
                list(FOCUS_REGION_CITIES) if focus_region else [city]
            )
            fb_items, fb_meta = scrape_facebook_marketplace(
                cities=target,
                max_items=max(max_items, 120),
                focus_region=focus_region,
            )
            meta["sources"]["Facebook Marketplace"] = len(fb_items)
            meta["notes"].extend(fb_meta.get("notes") or [])
            _extend(fb_items)
            if not fb_items:
                meta["notes"].append(
                    "פייסבוק Marketplace לא החזיר מודעות באזור — נסו סריקה ידנית שוב"
                )
        else:
            meta["notes"].append(
                "לסריקת פייסבוק יש להזין APIFY_API_TOKEN בהגדרות (יש לך מפתח? בדוק שנשמר)"
            )

    if not combined:
        meta["notes"].append("לא נמצאו מודעות חיות – מוצג דמו זמני")
        return fetch_mock_listings(), "mock-fallback", {
            **meta,
            "sources": {**meta.get("sources", {}), "Mock": 12},
        }

    mode = "live"
    return combined, mode, meta
