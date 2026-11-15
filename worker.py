"""
Headless apartment scanner for cloud / cron / GitHub Actions.

Runs without Streamlit, using settings.json + environment secrets.
Safe to run while the user's PC is offline (when hosted in the cloud).
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

import ai_filter
import database as db
from export_public import export_public_data
from match_filter import filter_matches
from notify import notify_new_listings, send_telegram_message, telegram_configured
from scraper import FOCUS_REGION_CITIES, fetch_listings
from settings_store import load_settings, save_settings

ROOT = Path(__file__).resolve().parent
STATUS_PATH = ROOT / "scan_status.json"
load_dotenv(ROOT / ".env")


def _log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{stamp}] {message}", flush=True)


def run_once() -> dict:
    settings = load_settings()
    if not settings.get("enabled", True):
        _log("Scanning disabled in settings.json (enabled=false)")
        return {"ok": False, "reason": "disabled"}

    cities = settings.get("cities") or list(FOCUS_REGION_CITIES)
    focus_region = bool(settings.get("focus_region", True))
    use_web = bool(settings.get("use_web", True))
    use_social = bool(settings.get("use_social", True))
    mock_mode = bool(settings.get("mock_mode", False))

    _log(
        f"Starting scan cities={cities} web={use_web} facebook={use_social} mock={mock_mode}"
    )
    started = time.time()

    listings, mode, meta = fetch_listings(
        mock_mode=mock_mode,
        city=" ".join(cities),
        cities=list(cities),
        use_web=use_web,
        use_social=use_social,
        use_yad2=bool(settings.get("use_yad2", False)),
        focus_region=focus_region,
        max_items=100,
    )

    use_openai = bool((os.getenv("OPENAI_API_KEY") or "").strip().strip('"').strip("'"))
    enriched = ai_filter.enrich_listings(listings, use_openai=use_openai)
    inserted, new_rows = db.upsert_many(enriched)

    # Apply default search filters and count matches for status.
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

    new_matches = filter_matches(new_rows, settings)
    notify_result: dict = {"sent": 0, "matched": 0, "other": 0}
    if new_rows and settings.get("notify_enabled", True):
        _log(
            f"New listings: {len(new_rows)} "
            f"(match={len(new_matches)}, other={len(new_rows) - len(new_matches)})"
        )
        notify_result = notify_new_listings(new_rows, settings=settings)
        _log(f"Telegram notify: {notify_result}")
    elif inserted and telegram_configured(settings):
        _log(f"Inserted {inserted} but notifications disabled/not configured")

    elapsed = round(time.time() - started, 1)
    status = {
        "ok": True,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "elapsed_sec": elapsed,
        "found": len(enriched),
        "inserted": inserted,
        "new_matches": len(new_matches),
        "new_other": max(0, len(new_rows) - len(new_matches)),
        "alerts_sent": notify_result.get("sent", 0),
        "matching_filters": len(matches),
        "sources": (meta or {}).get("sources", {}),
        "notes": (meta or {}).get("notes", []),
        "cities": cities,
        "db_total": db.count_apartments(),
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        public = export_public_data()
        status["public_export"] = public.get("count", 0)
        _log(f"Public viewer export: {public.get('count', 0)} listings")
    except Exception as exc:
        _log(f"Public export failed: {type(exc).__name__}: {exc}")
    _log(
        f"Done mode={mode} found={len(enriched)} inserted={inserted} "
        f"new_matches={len(new_matches)} alerts={notify_result.get('sent', 0)} "
        f"matches={len(matches)} elapsed={elapsed}s sources={status['sources']}"
    )
    return status


def run_loop() -> None:
    """Continuous loop for always-on cloud workers."""
    while True:
        settings = load_settings()
        interval = max(5, int(settings.get("interval_minutes") or 30))
        try:
            run_once()
        except Exception as exc:
            _log(f"Scan failed: {type(exc).__name__}: {exc}")
        _log(f"Sleeping {interval} minutes until next scan")
        time.sleep(interval * 60)


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if "--loop" in args:
        run_loop()
        return 0
    if "--save-defaults" in args:
        save_settings({})
        _log(f"Wrote defaults to {Path('settings.json').resolve()}")
        return 0
    if "--test-telegram" in args:
        settings = load_settings()
        ok, detail = send_telegram_message(
            "✅ בדיקת התראות מאתר הדירות — אם קיבלת את זה, ההתראות עובדות.",
            settings=settings,
        )
        _log(f"Telegram test: ok={ok} detail={detail}")
        return 0 if ok else 1
    status = run_once()
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
