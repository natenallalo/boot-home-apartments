"""Telegram notifications for new apartment listings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

from match_filter import listing_matches_settings

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def _clean(value: Optional[str]) -> str:
    return (value or "").strip().strip('"').strip("'")


def _read_dotenv_fallback(key: str) -> str:
    """Read a key from .env even if the process env was not refreshed."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return ""
    try:
        from dotenv import dotenv_values

        values = dotenv_values(env_path)
        return _clean(values.get(key))
    except Exception:
        return ""


def get_telegram_config(
    settings: Optional[dict[str, Any]] = None,
) -> tuple[str, str]:
    settings = settings or {}
    token = (
        _clean(os.getenv("TELEGRAM_BOT_TOKEN"))
        or _clean(str(settings.get("telegram_bot_token") or ""))
        or _read_dotenv_fallback("TELEGRAM_BOT_TOKEN")
    )
    chat_id = (
        _clean(os.getenv("TELEGRAM_CHAT_ID"))
        or _clean(str(settings.get("telegram_chat_id") or ""))
        or _read_dotenv_fallback("TELEGRAM_CHAT_ID")
    )
    return token, chat_id


def telegram_configured(settings: Optional[dict[str, Any]] = None) -> bool:
    token, chat_id = get_telegram_config(settings)
    return bool(token and chat_id)


def format_listing_message(
    item: dict[str, Any],
    *,
    matches_filter: bool = True,
) -> str:
    title = item.get("title") or "מודעה חדשה"
    city = item.get("city") or ""
    neighborhood = item.get("neighborhood") or ""
    loc = " · ".join(p for p in [city, neighborhood] if p)
    price = item.get("price")
    rooms = item.get("rooms")
    floor = item.get("floor")
    source = item.get("source") or ""
    url = item.get("url") or ""
    summary = (item.get("summary") or "").strip()

    price_txt = f"{price:,} ₪" if isinstance(price, int) else "מחיר לא צוין"
    rooms_txt = f"{rooms} חדרים" if rooms is not None else "חדרים לא צוינו"
    if floor is None:
        floor_txt = "קומה לא צוינה"
    elif int(floor) == 0:
        floor_txt = "קומת קרקע"
    else:
        floor_txt = f"קומה {floor}"

    if matches_filter:
        header = "✅ תואם לסינון שלך"
    else:
        header = "❌ לא תואם לסינון (מודעה חדשה בכל זאת)"

    lines = [
        header,
        "",
        title,
        loc or "מיקום לא צוין",
        f"{price_txt} · {rooms_txt} · {floor_txt}",
    ]
    if source:
        lines.append(f"מקור: {source}")
    if summary:
        lines.append("")
        lines.append(summary[:280])
    if url:
        lines.append("")
        lines.append(url)
    return "\n".join(lines)


def send_telegram_message(
    text: str,
    *,
    token: str = "",
    chat_id: str = "",
    settings: Optional[dict[str, Any]] = None,
) -> tuple[bool, str]:
    cfg_token, cfg_chat = get_telegram_config(settings)
    token = _clean(token) or cfg_token
    chat_id = _clean(chat_id) or cfg_chat
    if not token or not chat_id:
        return False, "חסר TELEGRAM_BOT_TOKEN או TELEGRAM_CHAT_ID"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": False,
            },
            timeout=30,
        )
        if resp.status_code >= 400:
            return False, f"Telegram HTTP {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        if not data.get("ok"):
            return False, str(data.get("description") or data)
        return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def notify_new_matches(
    listings: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    max_messages: int = 15,
) -> dict[str, Any]:
    """Backward-compatible: notify only listings already known to match."""
    return notify_new_listings(
        listings,
        settings=settings,
        max_match_messages=max_messages,
        max_other_messages=0,
        assume_all_match=True,
    )


def notify_new_listings(
    listings: list[dict[str, Any]],
    *,
    settings: Optional[dict[str, Any]] = None,
    max_match_messages: int = 12,
    max_other_messages: int = 12,
    assume_all_match: bool = False,
) -> dict[str, Any]:
    """
    Send Telegram alerts for new listings.
    Matching filter → category "✅ תואם לסינון"
    Non-matching → category "❌ לא תואם לסינון"
    """
    settings = settings or {}
    if not settings.get("notify_enabled", True):
        return {"sent": 0, "skipped": True, "reason": "disabled"}
    if not listings:
        return {"sent": 0, "skipped": False, "matched": 0, "other": 0}
    if not telegram_configured(settings):
        return {"sent": 0, "skipped": True, "reason": "not_configured"}

    notify_other = bool(settings.get("notify_non_matching", True))

    matched: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    if assume_all_match:
        matched = list(listings)
    else:
        for item in listings:
            if listing_matches_settings(item, settings):
                matched.append(item)
            else:
                other.append(item)

    sent = 0
    errors: list[str] = []

    def _send_batch(
        items: list[dict[str, Any]],
        *,
        matches_filter: bool,
        limit: int,
        overflow_label: str,
    ) -> None:
        nonlocal sent
        if limit <= 0 or not items:
            return
        for item in items[:limit]:
            ok, detail = send_telegram_message(
                format_listing_message(item, matches_filter=matches_filter),
                settings=settings,
            )
            if ok:
                sent += 1
            else:
                errors.append(detail)
        leftover = len(items) - limit
        if leftover > 0:
            send_telegram_message(
                f"{overflow_label}: עוד {leftover} מודעות שלא נשלחו בפירוט.",
                settings=settings,
            )

    if matched or (notify_other and other):
        send_telegram_message(
            "📬 סריקה חדשה\n"
            f"✅ תואם לסינון: {len(matched)}\n"
            f"❌ לא תואם לסינון: {len(other)}",
            settings=settings,
        )

    _send_batch(
        matched,
        matches_filter=True,
        limit=max_match_messages,
        overflow_label="✅ תואם לסינון",
    )
    if notify_other:
        _send_batch(
            other,
            matches_filter=False,
            limit=max_other_messages,
            overflow_label="❌ לא תואם לסינון",
        )

    return {
        "sent": sent,
        "errors": errors,
        "matched": len(matched),
        "other": len(other),
        "total_candidates": len(listings),
    }
