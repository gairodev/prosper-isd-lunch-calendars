#!/usr/bin/env python3
import datetime as dt
import textwrap
from typing import Dict, List

import requests

# Basic config
DISTRICT_SUBDOMAIN = "prosperisd"
SCHOOL_SLUG = "windsong-elementary"
MEAL_TYPE = "lunch"  # adjust if Prosper uses a custom slug
CALENDAR_NAME = "Windsong ES Lunch"
PRODID = "-//Family//Windsong Lunch//EN"


def build_weeks_url(date: dt.date) -> str:
    """
    Nutrislice weeks endpoint. This pattern is based on common Nutrislice deployments.
    If it 404s, you may need to tweak MEAL_TYPE or inspect the real URL via browser dev tools.
    """
    return (
        f"https://{DISTRICT_SUBDOMAIN}.api.nutrislice.com/menu/api/weeks/"
        f"school/{SCHOOL_SLUG}/menu-type/{MEAL_TYPE}/"
        f"{date.year}/{date.month}/{date.day}/?format=json"
    )


def fetch_week(date: dt.date) -> dict:
    url = build_weeks_url(date)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def extract_day_items(day: dict) -> List[str]:
    """
    Extract a simple list of menu item names from a Nutrislice 'day' object.
    """
    items = []
    for item in day.get("menu_items", []):
        if item.get("is_section_title"):
            continue

        food = item.get("food")
        if isinstance(food, dict):
            name = food.get("name")
            if name:
                items.append(name.strip())
                continue

        text = item.get("text")
        if text:
            items.append(text.strip())

    seen = set()
    unique_items: List[str] = []
    for name in items:
        if name not in seen:
            seen.add(name)
            unique_items.append(name)
    return unique_items


def collect_menus(start: dt.date, end: dt.date) -> Dict[dt.date, List[str]]:
    """
    Collect menus for each date in [start, end] by calling the weeks API.
    """
    menus: Dict[dt.date, List[str]] = {}
    current = start
    fetched_weeks = set()

    while current <= end:
        week_monday = current - dt.timedelta(days=current.weekday())
        if week_monday not in fetched_weeks:
            fetched_weeks.add(week_monday)
            try:
                data = fetch_week(week_monday)
            except Exception as e:
                print(f"[WARN] Failed to fetch week for {week_monday}: {e}")
                current += dt.timedelta(days=7)
                continue

            for day in data.get("days", []):
                date_str = day.get("date")
                if not date_str:
                    continue
                try:
                    day_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if start <= day_date <= end:
                    menus[day_date] = extract_day_items(day)

        current += dt.timedelta(days=7)

    return menus


def format_ics_datetime(dt_obj: dt.datetime) -> str:
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=dt.timezone.utc)
    else:
        dt_obj = dt_obj.astimezone(dt.timezone.utc)
    return dt_obj.strftime("%Y%m%dT%H%M%SZ")


def build_ics(menus: Dict[dt.date, List[str]]) -> str:
    now_utc = format_ics_datetime(dt.datetime.utcnow())

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{CALENDAR_NAME}",
    ]

    for day_date in sorted(menus.keys()):
        # Skip weekends: 5 = Saturday, 6 = Sunday
        if day_date.weekday() >= 5:
            continue
        items = menus[day_date]
        ymd = day_date.strftime("%Y%m%d")
        dtend = (day_date + dt.timedelta(days=1)).strftime("%Y%m%d")

        if items:
            summary = f"Windsong Lunch – {day_date.strftime('%b %d')}"
            desc_text = "Menu:\n" + "\n".join(f"- {i}" for i in items)
        else:
            summary = f"Windsong Lunch – {day_date.strftime('%b %d')} (No Menu Listed)"
            desc_text = "No lunch menu items were listed for this date."

        description_wrapped = "\\n".join(
            textwrap.wrap(desc_text.replace("\n", "\\n"), width=70)
        )

        uid = f"{SCHOOL_SLUG}-{MEAL_TYPE}-{ymd}@{DISTRICT_SUBDOMAIN}.nutrislice"

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"DTSTART;VALUE=DATE:{ymd}",
                f"DTEND;VALUE=DATE:{dtend}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description_wrapped}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    today = dt.date.today()
    end = today + dt.timedelta(days=365)  # rolling one year window
    print(f"Building menus from {today} to {end}...")
    menus = collect_menus(today, end)
    print(f"Found menus for {len(menus)} days.")

    ics_content = build_ics(menus)

    output_path = "windsong_lunch.ics"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ics_content)

    size_kb = len(ics_content.encode("utf-8")) / 1024.0
    print(f"Wrote {output_path} ({size_kb:.1f} KB).")


if __name__ == "__main__":
    main()
