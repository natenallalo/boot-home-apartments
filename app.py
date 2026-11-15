"""Hebrew RTL Streamlit UI for the rental apartment finder."""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv, set_key

import ai_filter
import database as db
from scraper import FOCUS_REGION_CITIES, fetch_listings
from search_utils import extract_city, extract_cities, parse_search_query
from match_filter import filter_matches
from notify import notify_new_listings, send_telegram_message, telegram_configured
from settings_store import load_settings, save_settings

ENV_PATH = Path(__file__).resolve().parent / ".env"
STATUS_PATH = Path(__file__).resolve().parent / "scan_status.json"
load_dotenv(ENV_PATH)
SAVED = load_settings()

st.set_page_config(
    page_title="מאתר דירות להשכרה",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

RTL_CSS = """
<style>
    html, body, [class*="css"]  {
        direction: rtl;
        text-align: right;
        font-family: "Segoe UI", Tahoma, Arial, sans-serif;
    }
    .stApp {
        background: linear-gradient(180deg, #f7f9fc 0%, #eef3f8 100%);
    }
    section[data-testid="stSidebar"] {
        direction: rtl;
        text-align: right;
        background: #ffffff;
    }
    .block-container {
        padding-top: 1.5rem;
        max-width: 1100px;
    }
    h1, h2, h3, h4, p, label, span, div {
        text-align: right;
    }
    .listing-card {
        background: #ffffff;
        border: 1px solid #e5eaf0;
        border-radius: 16px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
    }
    .badge {
        display: inline-block;
        padding: 0.25rem 0.7rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-left: 0.35rem;
        margin-bottom: 0.35rem;
    }
    .badge-private {
        background: #e8f8ef;
        color: #137333;
        border: 1px solid #b7e4c7;
    }
    .badge-realtor {
        background: #fdecea;
        color: #b3261e;
        border: 1px solid #f5c2c0;
    }
    .badge-source {
        background: #eef2ff;
        color: #3730a3;
        border: 1px solid #c7d2fe;
    }
    .meta-row {
        color: #475569;
        font-size: 0.95rem;
        margin: 0.45rem 0 0.7rem 0;
    }
    .summary-text {
        color: #0f172a;
        font-size: 1rem;
        line-height: 1.55;
        margin-bottom: 0.75rem;
    }
    .reason-text {
        color: #9a3412;
        font-size: 0.9rem;
        margin-bottom: 0.5rem;
    }
    .hero-sub {
        color: #64748b;
        margin-top: -0.5rem;
        margin-bottom: 1.25rem;
    }
</style>
"""

st.markdown(RTL_CSS, unsafe_allow_html=True)


def _clean_env_value(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


def save_keys_to_env(
    openai_key: str,
    apify_token: str,
    telegram_bot_token: str = "",
    telegram_chat_id: str = "",
) -> None:
    ENV_PATH.touch(exist_ok=True)
    set_key(str(ENV_PATH), "OPENAI_API_KEY", _clean_env_value(openai_key))
    set_key(str(ENV_PATH), "APIFY_API_TOKEN", _clean_env_value(apify_token))
    if telegram_bot_token is not None:
        set_key(
            str(ENV_PATH),
            "TELEGRAM_BOT_TOKEN",
            _clean_env_value(telegram_bot_token),
        )
        os.environ["TELEGRAM_BOT_TOKEN"] = _clean_env_value(telegram_bot_token)
    if telegram_chat_id is not None:
        set_key(
            str(ENV_PATH),
            "TELEGRAM_CHAT_ID",
            _clean_env_value(telegram_chat_id),
        )
        os.environ["TELEGRAM_CHAT_ID"] = _clean_env_value(telegram_chat_id)
    os.environ["OPENAI_API_KEY"] = _clean_env_value(openai_key)
    os.environ["APIFY_API_TOKEN"] = _clean_env_value(apify_token)
    load_dotenv(ENV_PATH, override=True)


def format_price(price) -> str:
    if price is None:
        return "לא צוין"
    try:
        return f"₪{int(price):,}"
    except (TypeError, ValueError):
        return str(price)


def format_rooms(rooms) -> str:
    if rooms is None:
        return "—"
    try:
        value = float(rooms)
        return str(int(value)) if value.is_integer() else str(value)
    except (TypeError, ValueError):
        return str(rooms)


def format_floor(floor) -> str:
    if floor is None:
        return "—"
    try:
        value = int(floor)
        return "קרקע" if value == 0 else str(value)
    except (TypeError, ValueError):
        return str(floor)


def render_listing_card(item: dict) -> None:
    is_realtor = bool(item.get("is_realtor"))
    if is_realtor:
        badge = '<span class="badge badge-realtor">תיווך</span>'
    else:
        badge = '<span class="badge badge-private">פרטי - ללא תיווך</span>'

    source = item.get("source") or "לא ידוע"
    source_badge = f'<span class="badge badge-source">{source}</span>'
    ptype = item.get("property_type") or ""
    if not ptype:
        blob = f"{item.get('title') or ''} {item.get('description') or ''}"
        if "יחיד" in blob:
            ptype = "יחידת דיור"
        elif "דירת גן" in blob:
            ptype = "דירת גן"
        else:
            ptype = "דירה"
    type_badge = f'<span class="badge badge-source">{ptype}</span>'
    floor_badge = ""
    if item.get("floor") == 0 or "קרקע" in (item.get("description") or "") or ptype == "דירת גן":
        floor_badge = '<span class="badge badge-private">קומת קרקע</span>'
    title = item.get("title") or "דירה להשכרה"
    summary = item.get("summary") or item.get("description") or ""
    reason = item.get("realtor_reason") or ""
    city = item.get("city") or ""
    neighborhood = item.get("neighborhood") or ""
    location = " · ".join(x for x in [city, neighborhood] if x)

    reason_html = (
        f'<div class="reason-text">סיבה: {reason}</div>' if is_realtor and reason else ""
    )

    st.markdown(
        (
            f'<div class="listing-card">'
            f"<div>{badge}{type_badge}{floor_badge}{source_badge}</div>"
            f'<h3 style="margin: 0.35rem 0 0.15rem 0;">{title}</h3>'
            f'<div class="meta-row">'
            f"<strong>{format_price(item.get('price'))}</strong>"
            f"&nbsp;|&nbsp; {format_rooms(item.get('rooms'))} חדרים"
            f"&nbsp;|&nbsp; קומה {format_floor(item.get('floor'))}"
            f"{'&nbsp;|&nbsp; ' + location if location else ''}"
            f"</div>"
            f"{reason_html}"
            f'<div class="summary-text">{summary}</div>'
            f"</div>"
        ),
        unsafe_allow_html=True,
    )

    cols = st.columns([2, 1, 1, 1])
    url = item.get("url") or ""
    with cols[0]:
        if url:
            st.link_button("למעבר למודעה המקורית", url, use_container_width=True)
    with cols[1]:
        fav = bool(item.get("is_favorite"))
        if st.button(
            "הסר ממועדפים" if fav else "מועדף",
            key=f"fav_{item['id']}",
            use_container_width=True,
        ):
            db.set_favorite(item["id"], not fav)
            st.rerun()
    with cols[2]:
        if st.button("הסתר", key=f"hide_{item['id']}", use_container_width=True):
            db.set_hidden(item["id"], True)
            st.rerun()


def ensure_seed_data() -> None:
    if db.count_apartments() == 0:
        listings, _mode, _meta = fetch_listings(mock_mode=True)
        enriched = ai_filter.enrich_listings(listings, use_openai=False)
        db.upsert_many(enriched)


def run_scan(
    *,
    city: str,
    cities: list[str] | None = None,
    mock_mode: bool,
    use_web: bool,
    use_social: bool,
    use_yad2: bool,
    focus_region: bool,
    trigger: str,
) -> None:
    """Fetch listings, analyze, store, and update session status."""
    target_cities = cities or extract_cities(city) or list(FOCUS_REGION_CITIES)
    listings, mode, meta = fetch_listings(
        mock_mode=mock_mode,
        city=city or "רמלה",
        cities=target_cities,
        use_web=use_web,
        use_social=use_social,
        use_yad2=use_yad2,
        focus_region=focus_region,
        max_items=100,
    )
    use_openai = bool(_clean_env_value(os.getenv("OPENAI_API_KEY", "")))
    enriched = ai_filter.enrich_listings(listings, use_openai=use_openai)
    upsert_result = db.upsert_many(enriched)
    if isinstance(upsert_result, tuple):
        inserted, new_rows = upsert_result
    else:
        inserted, new_rows = int(upsert_result or 0), []
    settings_now = load_settings()
    new_matches = filter_matches(new_rows, settings_now)
    alerts = {"sent": 0, "matched": 0, "other": 0}
    if new_rows and settings_now.get("notify_enabled", True):
        alerts = notify_new_listings(new_rows, settings=settings_now)
    meta = dict(meta or {})
    meta["trigger"] = trigger
    meta["scan_cities"] = target_cities
    meta["new_matches"] = len(new_matches)
    meta["new_other"] = max(0, len(new_rows) - len(new_matches))
    meta["alerts_sent"] = alerts.get("sent", 0)
    st.session_state["last_fetch_mode"] = mode
    st.session_state["last_inserted"] = inserted
    st.session_state["last_fetch_meta"] = meta
    st.session_state["last_fetch_total"] = len(enriched)
    st.session_state["last_scan_ts"] = time.time()
    st.session_state["last_scan_city"] = " ".join(target_cities)


ensure_seed_data()

st.title("🏠 מאתר דירות להשכרה")
st.markdown(
    '<p class="hero-sub">מיקוד נוכחי: <strong>רמלה ולוד</strong> · סריקה מקומית + ענן (גם כשהמחשב כבוי)</p>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("פילטרים")
    focus_region = st.toggle(
        "מיקוד רמלה + לוד בלבד",
        value=bool(SAVED.get("focus_region", True)),
        help="כשפעיל: סורק ומציג רק דירות ברמלה ובלוד",
    )
    city_keyword = st.text_input(
        "עיר / מילת מפתח",
        value=str(SAVED.get("city_keyword") or "רמלה לוד"),
        placeholder="רמלה לוד / דירה ברמלה...",
        help="ברירת מחדל: רמלה ולוד. אפשר לכתוב משפט חופשי.",
    )
    parsed_query = parse_search_query(city_keyword)
    scan_cities = parsed_query.get("cities") or extract_cities(city_keyword)
    if focus_region:
        # Always scan both focus cities while region mode is on.
        scan_cities = list(FOCUS_REGION_CITIES)
        if city_keyword.strip() in {"", "רמלה", "לוד"}:
            city_keyword = "רמלה לוד"
    if not scan_cities:
        scan_cities = list(FOCUS_REGION_CITIES) if focus_region else ["רמלה"]
    scan_city = " ".join(scan_cities)
    st.caption(f"ערים לסריקה: {', '.join(scan_cities)}")

    st.subheader("סוג נכס")
    include_apartments = st.checkbox(
        "דירות", value=bool(SAVED.get("include_apartments", True))
    )
    include_units = st.checkbox(
        "יחידות דיור",
        value=bool(SAVED.get("include_units", True)),
        help="כולל יחידות דיור גם אם מספר החדרים קטן מסינון החדרים של דירות",
    )
    ground_floor_only = st.toggle(
        "קומת קרקע / דירת גן בלבד",
        value=bool(SAVED.get("ground_floor_only", False)),
        help="מציג רק נכסים בקומת קרקע או דירות גן",
    )

    st.caption("השאר 0 = ללא הגבלה")
    c1, c2 = st.columns(2)
    with c1:
        min_price = st.number_input(
            "מחיר מינ׳",
            min_value=0,
            value=int(SAVED.get("min_price") or 0),
            step=100,
        )
    with c2:
        max_price = st.number_input(
            "מחיר מקס׳",
            min_value=0,
            value=int(SAVED.get("max_price") or 3500),
            step=100,
        )

    r1, r2 = st.columns(2)
    with r1:
        min_rooms = st.number_input(
            "חדרים מינ׳ (לדירות)",
            min_value=0.0,
            value=float(SAVED.get("min_rooms") or 3.0),
            step=0.5,
            help="חל על דירות. יחידות דיור יוצגו גם עם פחות חדרים אם מסומן למעלה.",
        )
    with r2:
        max_rooms = st.number_input(
            "חדרים מקס׳",
            min_value=0.0,
            value=float(SAVED.get("max_rooms") or 0.0),
            step=0.5,
        )

    f1, f2 = st.columns(2)
    with f1:
        min_floor = st.number_input(
            "קומה מינ׳",
            min_value=0,
            value=int(SAVED.get("min_floor") or 0),
            step=1,
        )
    with f2:
        max_floor = st.number_input(
            "קומה מקס׳",
            min_value=0,
            value=int(SAVED.get("max_floor") or 0),
            step=1,
        )

    private_only = st.toggle(
        "הצג דירות ללא תיווך בלבד (פרטי)",
        value=bool(SAVED.get("private_only", False)),
        help="מציג רק מודעות שסווגו כפרטיות ללא תיווך",
    )
    favorites_only = st.toggle("הצג מועדפים בלבד", value=False)

    st.divider()
    st.subheader("סריקה אוטומטית")
    auto_scan = st.toggle(
        "הפעל סריקה אוטומטית (מקומית)",
        value=bool(SAVED.get("enabled", True)),
        help="עובד רק כשהאפליקציה פתוחה במחשב. לסריקה גם כשהמחשב כבוי — שמור לענן למטה.",
    )
    auto_interval_min = st.number_input(
        "כל כמה דקות לסרוק (מקומי)",
        min_value=1,
        max_value=120,
        value=min(120, max(1, int(SAVED.get("interval_minutes") or 60))),
        step=1,
        help="במחשב המקומי. בענן GitHub Actions רץ כל שעה.",
    )
    auto_include_facebook = st.checkbox(
        "כלול פייסבוק Marketplace בסריקה האוטומטית",
        value=bool(SAVED.get("use_social", True)),
        help="מומלץ — סורק Facebook Marketplace לרמלה/לוד דרך Apify. קבוצות פייסבוק דורשות התחברות ולכן Marketplace הוא המקור העיקרי.",
    )
    st.caption("טיפ: סריקת פייסבוק לוקחת ~1–2 דקות. אם מופיע Forbidden — חכו כמה דקות וסירקו ידנית.")

    st.divider()
    st.subheader("מקורות סריקה")
    use_web = st.checkbox(
        "אינטרנט (Homeless + Ad.co.il)",
        value=bool(SAVED.get("use_web", True)),
    )
    use_social = st.checkbox(
        "פייסבוק Marketplace (Apify)",
        value=bool(SAVED.get("use_social", True)),
        help="סורק דירות/יחידות דיור להשכרה ברמלה ולוד מפייסבוק",
    )
    use_yad2 = st.checkbox(
        "Yad2 דרך Apify", value=bool(SAVED.get("use_yad2", False))
    )
    mock_mode = st.checkbox(
        "Mock Mode (נתוני דמו בלבד)",
        value=bool(SAVED.get("mock_mode", False)),
    )
    if use_social and not _clean_env_value(os.getenv("APIFY_API_TOKEN", "")):
        st.warning("לפייסבוק חסר APIFY_API_TOKEN — הדבק בהגדרות למטה")

    st.divider()
    st.subheader("☁️ סריקה בענן (גם כשהמחשב כבוי)")
    st.caption(
        "שמירת ההגדרות כאן מעדכנת את settings.json שהענן קורא ממנו כל ~30 דקות."
    )
    notify_enabled = st.toggle(
        "שלח התראות Telegram על מודעות חדשות",
        value=bool(SAVED.get("notify_enabled", True)),
    )
    notify_non_matching = st.toggle(
        "כולל גם מודעות שלא תואמות לסינון (מסומן ❌)",
        value=bool(SAVED.get("notify_non_matching", True)),
        help="תואמות מסומנות ✅, לא תואמות מסומנות ❌",
    )
    if st.button("💾 שמור הגדרות לענן", use_container_width=True, type="primary"):
        save_settings(
            {
                "focus_region": focus_region,
                "cities": list(scan_cities),
                "city_keyword": city_keyword,
                "use_web": use_web,
                "use_social": use_social,
                "use_yad2": use_yad2,
                "mock_mode": mock_mode,
                "include_apartments": include_apartments,
                "include_units": include_units,
                "ground_floor_only": ground_floor_only,
                "min_price": int(min_price),
                "max_price": int(max_price),
                "min_rooms": float(min_rooms),
                "max_rooms": float(max_rooms),
                "min_floor": int(min_floor),
                "max_floor": int(max_floor),
                "private_only": private_only,
                "interval_minutes": int(auto_interval_min),
                "enabled": True,
                "notify_enabled": notify_enabled,
                "notify_non_matching": notify_non_matching,
                "telegram_chat_id": _clean_env_value(
                    os.getenv("TELEGRAM_CHAT_ID", "")
                )
                or str(SAVED.get("telegram_chat_id") or ""),
            }
        )
        st.success("ההגדרות נשמרו — הענן יסרוק וישלח התראות גם כשהמחשב כבוי")
        st.rerun()

    if STATUS_PATH.exists():
        try:
            import json as _json

            cloud_status = _json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            finished = cloud_status.get("finished_at", "")
            st.info(
                f"סריקת ענן אחרונה: {finished}\n\n"
                f"נמצאו {cloud_status.get('found', 0)} · "
                f"חדשים {cloud_status.get('inserted', 0)} · "
                f"התאמות חדשות {cloud_status.get('new_matches', 0)} · "
                f"התראות {cloud_status.get('alerts_sent', 0)}"
            )
        except Exception:
            pass

    st.divider()
    with st.expander(
        "⚙️ הגדרות מפתחות API + Telegram",
        expanded=not telegram_configured(SAVED),
    ):
        st.caption(
            "סריקת אינטרנט עובדת בלי מפתחות. לפייסבוק נדרש APIFY. "
            "להתראות בטלגרם: צרו בוט ב-@BotFather, העתיקו את הטוקן, "
            "שלחו הודעה לבוט, והדביקו כאן גם את ה-Chat ID (מ-@userinfobot)."
        )
        current_openai = _clean_env_value(os.getenv("OPENAI_API_KEY", ""))
        current_apify = _clean_env_value(os.getenv("APIFY_API_TOKEN", ""))
        current_tg_token = _clean_env_value(
            os.getenv("TELEGRAM_BOT_TOKEN", "")
        ) or str(SAVED.get("telegram_bot_token") or "")
        current_tg_chat = _clean_env_value(
            os.getenv("TELEGRAM_CHAT_ID", "")
        ) or str(SAVED.get("telegram_chat_id") or "")

        openai_input = st.text_input(
            "OPENAI_API_KEY",
            value=current_openai,
            type="password",
            placeholder="sk-...",
        )
        apify_input = st.text_input(
            "APIFY_API_TOKEN",
            value=current_apify,
            type="password",
            placeholder="apify_api_...",
        )
        tg_token_input = st.text_input(
            "TELEGRAM_BOT_TOKEN",
            value=current_tg_token,
            type="password",
            placeholder="123456:ABC...",
        )
        tg_chat_input = st.text_input(
            "TELEGRAM_CHAT_ID",
            value=current_tg_chat,
            placeholder="לדוגמה 712345678",
        )
        c_save, c_test = st.columns(2)
        with c_save:
            if st.button("שמור מפתחות", use_container_width=True):
                save_keys_to_env(
                    openai_input,
                    apify_input,
                    tg_token_input,
                    tg_chat_input,
                )
                save_settings(
                    {
                        "telegram_chat_id": _clean_env_value(tg_chat_input),
                        "notify_enabled": True,
                    }
                )
                st.success("המפתחות נשמרו ל-.env ולענן")
                st.rerun()
        with c_test:
            if st.button("בדיקת Telegram", use_container_width=True):
                save_keys_to_env(
                    openai_input,
                    apify_input,
                    tg_token_input,
                    tg_chat_input,
                )
                ok, detail = send_telegram_message(
                    "✅ בדיקת התראות מאתר הדירות — אם קיבלת את זה, זה עובד.",
                    token=tg_token_input,
                    chat_id=tg_chat_input,
                )
                if ok:
                    st.success("הודעת בדיקה נשלחה לטלגרם")
                else:
                    st.error(f"שליחה נכשלה: {detail}")

        st.caption(
            "סטטוס: "
            + ("OpenAI ✓ · " if current_openai else "OpenAI חסר · ")
            + ("Apify ✓ · " if current_apify else "Apify חסר · ")
            + (
                "Telegram ✓"
                if telegram_configured(
                    {
                        "telegram_bot_token": current_tg_token,
                        "telegram_chat_id": current_tg_chat,
                    }
                )
                else "Telegram לא מוגדר"
            )
        )

    st.divider()
    manual_scan = st.button(
        "🔍 סריקה ידנית עכשיו", type="primary", use_container_width=True
    )

# Decide whether an automatic scan should run now.
now = time.time()
last_scan_ts = float(st.session_state.get("last_scan_ts") or 0)
last_scan_city = st.session_state.get("last_scan_city")
interval_sec = int(auto_interval_min) * 60
city_changed = bool(last_scan_city) and last_scan_city != scan_city
due_for_auto = auto_scan and (
    last_scan_ts == 0 or (now - last_scan_ts) >= interval_sec or city_changed
)

if manual_scan:
    with st.spinner(f"סורק לעומק מודעות ב{', '.join(scan_cities)}..."):
        run_scan(
            city=scan_city,
            cities=scan_cities,
            mock_mode=mock_mode,
            use_web=use_web,
            use_social=use_social,
            use_yad2=use_yad2,
            focus_region=focus_region,
            trigger="ידני",
        )
    st.rerun()

if due_for_auto and not st.session_state.get("_scanning"):
    st.session_state["_scanning"] = True
    with st.spinner(f"סריקה אוטומטית ל{', '.join(scan_cities)}..."):
        run_scan(
            city=scan_city,
            cities=scan_cities,
            mock_mode=mock_mode,
            use_web=use_web,
            use_social=use_social if auto_include_facebook else False,
            use_yad2=False,
            focus_region=focus_region,
            trigger="אוטומטי",
        )
    st.session_state["_scanning"] = False
    st.rerun()


def _render_auto_status() -> None:
    if not auto_scan:
        st.caption("סריקה אוטומטית כבויה")
        return
    last = float(st.session_state.get("last_scan_ts") or 0)
    if last <= 0:
        st.caption("ממתין לסריקה אוטומטית ראשונה...")
        return
    elapsed = int(time.time() - last)
    remaining = max(0, interval_sec - elapsed)
    mins, secs = divmod(remaining, 60)
    st.caption(f"סריקה אוטומטית פעילה · הבאה בעוד {mins}:{secs:02d} דק׳")


if auto_scan:

    @st.fragment(run_every=timedelta(seconds=30))
    def _auto_scan_ticker() -> None:
        """Rerun every 30s so interval-based auto scans can fire without a click."""
        last = float(st.session_state.get("last_scan_ts") or 0)
        if last > 0 and (time.time() - last) >= interval_sec:
            st.session_state.pop("_scanning", None)
            st.rerun()
        _render_auto_status()

    _auto_scan_ticker()
else:
    _render_auto_status()

if "last_fetch_meta" in st.session_state:
    meta = st.session_state["last_fetch_meta"]
    sources = meta.get("sources") or {}
    source_txt = ", ".join(f"{k}: {v}" for k, v in sources.items()) or "אין"
    notes = list(meta.get("notes") or [])
    trigger = meta.get("trigger") or ""
    inserted = int(st.session_state.get("last_inserted", 0) or 0)
    total_found = int(st.session_state.get("last_fetch_total", 0) or 0)
    if total_found > 0 and inserted == 0:
        notes.append("כל המודעות כבר היו בבסיס (אין כפילויות חדשות)")
    st.info(
        f"סריקה אחרונה ({st.session_state.get('last_fetch_mode')}"
        f"{' · ' + trigger if trigger else ''}): "
        f"{total_found} מודעות נמצאו, "
        f"{inserted} חדשות נוספו לבסיס. "
        f"מקורות: {source_txt}"
        + ((" | " + " · ".join(notes)) if notes else "")
    )

# Merge UI filters with hints parsed from free text (e.g. "3 חדרים עד 3000").
effective_min_rooms = min_rooms if min_rooms > 0 else parsed_query.get("rooms")
effective_max_price = max_price if max_price > 0 else parsed_query.get("max_price")
search_keyword = " ".join(scan_cities) if focus_region else city_keyword

results = db.search_apartments(
    city_keyword=search_keyword,
    min_price=min_price if min_price > 0 else None,
    max_price=effective_max_price if effective_max_price else None,
    min_rooms=effective_min_rooms if effective_min_rooms else None,
    max_rooms=max_rooms if max_rooms > 0 else None,
    min_floor=min_floor if min_floor > 0 else None,
    max_floor=max_floor if max_floor > 0 else None,
    private_only=private_only,
    favorites_only=favorites_only,
    include_apartments=include_apartments,
    include_units=include_units,
    ground_floor_only=ground_floor_only,
    rooms_flexible_for_units=True,
)

private_count = sum(1 for r in results if not r.get("is_realtor"))
realtor_count = sum(1 for r in results if r.get("is_realtor"))

m1, m2, m3 = st.columns(3)
m1.metric("תוצאות", len(results))
m2.metric("פרטי", private_count)
m3.metric("תיווך", realtor_count)

if not results:
    st.info("לא נמצאו דירות התואמות לפילטרים. נסו להרחיב את החיפוש או לרענן מודעות.")
else:
    for item in results:
        render_listing_card(item)
