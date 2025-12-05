#!/usr/bin/env python3
import datetime as dt
import json
import os
import textwrap
from typing import Dict, Iterable, List, Optional, Tuple

import requests

# District configuration
DISTRICT_SUBDOMAIN = "prosperisd"
DEFAULT_MEAL_TYPE = "lunch"
PRODID = "-//Family//Prosper ISD Lunch Calendars//EN"

# Output configuration
DOCS_DIR = "docs"
OUTPUT_SUFFIX = "_lunch.ics"


def build_weeks_url(school_slug: str, meal_type_slug: str, date: dt.date) -> str:
    """
    Nutrislice weeks endpoint. If this 404s for a given school, the school may
    not have that menu type; callers should try a different meal_type or skip.
    """
    return (
        f"https://{DISTRICT_SUBDOMAIN}.api.nutrislice.com/menu/api/weeks/"
        f"school/{school_slug}/menu-type/{meal_type_slug}/"
        f"{date.year}/{date.month}/{date.day}/?format=json"
    )


def fetch_week(school_slug: str, meal_type_slug: str, date: dt.date) -> dict:
    url = build_weeks_url(school_slug, meal_type_slug, date)
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return resp.json()


def extract_day_items(day: dict) -> List[str]:
    """
    Extract a simple list of menu item names from a Nutrislice 'day' object.
    """
    items: List[str] = []
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


def collect_menus(
    school_slug: str,
    meal_type_slug: str,
    start: dt.date,
    end: dt.date,
) -> Dict[dt.date, List[str]]:
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
                data = fetch_week(school_slug, meal_type_slug, week_monday)
            except Exception as e:
                print(
                    f"[WARN] {school_slug}: Failed to fetch week {week_monday} for '{meal_type_slug}': {e}"
                )
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


def build_ics(
    school_name: str,
    school_slug: str,
    meal_type_slug: str,
    menus: Dict[dt.date, List[str]],
) -> str:
    now_utc = format_ics_datetime(dt.datetime.utcnow())

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{school_name} Lunch",
    ]

    for day_date in sorted(menus.keys()):
        # Skip weekends: 5 = Saturday, 6 = Sunday
        if day_date.weekday() >= 5:
            continue
        items = menus[day_date]
        ymd = day_date.strftime("%Y%m%d")
        dtend = (day_date + dt.timedelta(days=1)).strftime("%Y%m%d")

        if items:
            summary = f"{school_name} Lunch – {day_date.strftime('%b %d')}"
            desc_text = "Menu:\n" + "\n".join(f"- {i}" for i in items)
        else:
            summary = f"{school_name} Lunch – {day_date.strftime('%b %d')} (No Menu Listed)"
            desc_text = "No lunch menu items were listed for this date."

        description_wrapped = "\\n".join(
            textwrap.wrap(desc_text.replace("\n", "\\n"), width=70)
        )

        uid = f"{school_slug}-{meal_type_slug}-{ymd}@{DISTRICT_SUBDOMAIN}.nutrislice"

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


def fetch_all_schools() -> List[dict]:
    """
    Fetch all schools for the district from Nutrislice.
    """
    url = f"https://{DISTRICT_SUBDOMAIN}.api.nutrislice.com/menu/api/schools/?format=json"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "results" in data:
        # In case of paginated format
        return data.get("results", [])
    if isinstance(data, list):
        return data
    # Unexpected format
    return []


def choose_meal_type_slug(
    school_slug: str, candidate: str = DEFAULT_MEAL_TYPE
) -> Optional[str]:
    """
    Return a meal_type slug to use for a school.
    Strategy:
      1) Try the default 'lunch' slug.
      2) If that fails for the current week, try some common alternates.
    """
    today = dt.date.today()
    start_of_week = today - dt.timedelta(days=today.weekday())

    def try_slug(slug: str) -> bool:
        try:
            _ = fetch_week(school_slug, slug, start_of_week)
            return True
        except Exception:
            return False

    if try_slug(candidate):
        return candidate

    alternates = [
        "elementary-lunch",
        "middle-school-lunch",
        "high-school-lunch",
        "secondary-lunch",
        "ms-lunch",
        "hs-lunch",
        "es-lunch",
    ]
    for alt in alternates:
        if try_slug(alt):
            return alt
    return None


def ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def write_docs_index(schools: Iterable[Tuple[str, str]]) -> None:
    """
    Write docs/index.md with a searchable list of school ICS links and quick instructions.
    """
    ensure_dir(DOCS_DIR)
    sorted_schools = sorted(schools, key=lambda x: x[0].lower())

    lines: List[str] = []
    lines.append("## Prosper ISD Lunch Calendars")
    lines.append("")
    lines.append("Find your school and subscribe to its lunch calendar.")
    lines.append("")
    lines.append('<input id="schoolSearch" type="text" placeholder="Search schools…" style="max-width: 480px; width: 100%; padding: 8px; font-size: 16px; margin: 8px 0;">')
    lines.append("")
    lines.append('<ul id="schoolList">')
    for school_name, school_slug in sorted_schools:
        ics_filename = f"{school_slug}{OUTPUT_SUFFIX}"
        # Each item includes a Subscribe link and a Copy URL button
        lines.append(
            f'  <li data-name="{school_name.lower()}" data-slug="{school_slug}">'
            f'<a href="{ics_filename}">{school_name}</a> '
            f'<button data-href="{ics_filename}" onclick="copyLink(this)" style="margin-left:6px;">Copy URL</button>'
            f"</li>"
        )
    lines.append("</ul>")
    lines.append("")
    lines.append("<script>")
    lines.append("(function(){")
    lines.append("  const input = document.getElementById('schoolSearch');")
    lines.append("  const list = document.getElementById('schoolList');")
    lines.append("  function filter() {")
    lines.append("    const q = (input.value || '').trim().toLowerCase();")
    lines.append("    for (const li of list.querySelectorAll('li')) {")
    lines.append("      const name = li.getAttribute('data-name') || '';")
    lines.append("      const slug = li.getAttribute('data-slug') || '';")
    lines.append("      const show = !q || name.includes(q) || slug.includes(q);")
    lines.append("      li.style.display = show ? '' : 'none';")
    lines.append("    }")
    lines.append("  }")
    lines.append("  input.addEventListener('input', filter);")
    lines.append("  window.copyLink = function(btn){")
    lines.append("    try {")
    lines.append("      const href = btn.getAttribute('data-href');")
    lines.append("      const absolute = new URL(href, window.location.href).href;")
    lines.append("      navigator.clipboard.writeText(absolute);")
    lines.append("      btn.textContent = 'Copied!';")
    lines.append("      setTimeout(()=>{ btn.textContent = 'Copy URL'; }, 1500);")
    lines.append("    } catch (e) {")
    lines.append("      alert('Copy failed. You can right-click the link and copy its address.');")
    lines.append("    }")
    lines.append("  }")
    lines.append("})();")
    lines.append("</script>")
    lines.append("")
    lines.append("### How to subscribe")
    lines.append("- **Google Calendar (web)**: Other calendars → + → From URL → paste the school link → Add")
    lines.append("- **Apple Calendar (macOS)**: File → New Calendar Subscription… → paste the school link → Subscribe")
    lines.append("- **iPhone/iPad**: Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar → paste the school link")
    lines.append("- **Outlook (web)**: Add calendar → Subscribe from web → paste the school link → Import")
    lines.append("")
    content = "\n".join(lines) + "\n"

    with open(os.path.join(DOCS_DIR, "index.md"), "w", encoding="utf-8") as f:
        f.write(content)


def main():
    today = dt.date.today()
    end = today + dt.timedelta(days=365)  # rolling one year window
    print(f"Building menus from {today} to {end}...")

    # Discover all schools
    try:
        schools = fetch_all_schools()
    except Exception as e:
        print(f"[ERROR] Failed to fetch schools: {e}")
        return

    # Normalize schools to (name, slug)
    school_pairs: List[Tuple[str, str]] = []
    for s in schools:
        name = s.get("name") or s.get("title") or ""
        slug = s.get("slug") or ""
        if name and slug:
            school_pairs.append((name.strip(), slug.strip()))
    if not school_pairs:
        print("[ERROR] No schools discovered.")
        return

    ensure_dir(DOCS_DIR)

    generated: List[Tuple[str, str]] = []
    skipped: List[Tuple[str, str]] = []

    for school_name, school_slug in school_pairs:
        meal_type_slug = choose_meal_type_slug(school_slug, DEFAULT_MEAL_TYPE)
        if not meal_type_slug:
            print(f"[WARN] {school_slug}: No working lunch menu type found; skipping.")
            skipped.append((school_name, school_slug))
            continue

        print(f"[INFO] Generating: {school_name} ({school_slug}) using '{meal_type_slug}'")
        menus = collect_menus(school_slug, meal_type_slug, today, end)
        ics_content = build_ics(school_name, school_slug, meal_type_slug, menus)

        ics_filename = f"{school_slug}{OUTPUT_SUFFIX}"
        output_path = os.path.join(DOCS_DIR, ics_filename)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ics_content)

        size_kb = len(ics_content.encode("utf-8")) / 1024.0
        print(f"[OK] Wrote {output_path} ({size_kb:.1f} KB).")
        generated.append((school_name, school_slug))

    # Also keep a legacy single-file at repo root for Windsong if present, for continuity.
    legacy_slug = "windsong-elementary"
    for school_name, school_slug in generated:
        if school_slug == legacy_slug:
            legacy_src = os.path.join(DOCS_DIR, f"{school_slug}{OUTPUT_SUFFIX}")
            legacy_dst = "windsong_lunch.ics"
            try:
                with open(legacy_src, "r", encoding="utf-8") as src, open(
                    legacy_dst, "w", encoding="utf-8"
                ) as dst:
                    dst.write(src.read())
                print(f"[OK] Updated legacy file {legacy_dst} for {school_name}.")
            except Exception as e:
                print(f"[WARN] Could not update legacy file {legacy_dst}: {e}")
            break

    # Refresh docs index to list all generated schools
    if generated:
        write_docs_index(generated)
        print(f"[OK] Updated docs/index.md with {len(generated)} schools.")
    else:
        print("[WARN] No calendars generated; docs/index.md not updated.")


if __name__ == "__main__":
    main()
