## Prosper ISD Lunch Calendars (Nutrislice → iCal)

This repository generates iCalendar (.ics) files for all Prosper ISD schools by fetching data from the Nutrislice API and converting each school day’s lunch menu into an all‑day calendar event.

Each school gets its own `.ics` file in `docs/`, and the GitHub Pages site at `docs/index.md` provides a simple selector so parents can subscribe to their school’s lunch calendar via a stable URL.

### What this repo does

- Discovers all Prosper ISD schools from Nutrislice.
- Fetches lunch menus for a rolling one‑year window starting today.
- Creates one all‑day event per date; the description lists the menu items.
- Writes an `.ics` per school to `docs/<school-slug>_lunch.ics`.
- Writes/refreshes `docs/index.md` with a list of schools and subscribe links.
- Optionally maintains a legacy `windsong_lunch.ics` at repo root for continuity.

## Quick start (local)

1) Use Python 3.12+ (matches CI). Create a virtual environment and install deps:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Generate all school calendars:

```bash
python generate_calendar.py
```

This creates one `.ics` per school in `docs/` and refreshes `docs/index.md`. You can import an `.ics` into your calendar app, or host it via GitHub Pages and subscribe by URL.

### Subscribe by URL

If this repo is hosted on GitHub, you can subscribe directly to each school’s file using the Pages URL. Replace placeholders with your org/user and repo:

- Pages link example: `https://<org-or-user>.github.io/<repo>/<school-slug>_lunch.ics`
- The site index at `https://<org-or-user>.github.io/<repo>/` lists all schools with direct links.

Most calendar apps support adding a calendar by URL. Paste the link; updates are pulled automatically when your workflow or manual runs commit new content.

## How it works

- Script: `generate_calendar.py`
  - Discovers schools from `https://<district>.api.nutrislice.com/menu/api/schools/`.
  - For each school, finds a working `lunch` menu type (tries common alternates if needed).
  - Fetches week JSON and collects day menus for dates within the next year.
  - Produces standards‑compliant `.ics` with one all‑day event per date:
    - `SUMMARY`: “<School Name> Lunch – Mon DD”
    - `DESCRIPTION`: bullet‑style list of menu items (wrapped to safe line lengths)
    - If no items are listed by Nutrislice, the event notes that explicitly.

- Dependencies: `requests`
  - See `requirements.txt`. Install with `pip install -r requirements.txt`.

- Output:
  - `docs/<school-slug>_lunch.ics` for each discovered school
  - `docs/index.md` (selector page)
  - (Optional) `windsong_lunch.ics` at repo root for the Windsong Elementary legacy link

## Scheduled updates (GitHub Actions)

Workflow (suggested): `.github/workflows/update-calendars.yml`

- Runs on a schedule (e.g., weekly) and on demand.
- Steps:
  - Checkout
  - Set up Python 3.12
  - `pip install -r requirements.txt`
  - `python generate_calendar.py`
  - Commit updates if files changed

This keeps the calendar current without manual intervention.

## Configuration

Adjust these in `generate_calendar.py` if needed:

- `DISTRICT_SUBDOMAIN`: Nutrislice district subdomain (e.g., `"prosperisd"`).
- `DEFAULT_MEAL_TYPE`: Menu type path segment to try first (commonly `"lunch"`).
- `PRODID`: iCal producer identifier string used in all outputs.

If the Nutrislice deployment uses different meal slugs, the script tries several common alternates. You can customize `alternates` in `choose_meal_type_slug`.

## Notes and limitations

- Time zone: Events are all‑day, so no time zone handling is required by consumers.
- Coverage: The script targets a rolling 365‑day window from today.
- Gaps: If Nutrislice returns no items for a date, the event clarifies “No Menu Listed”.
- API reliability: Network hiccups are logged with a warning; missing weeks are skipped.
- Formatting: Lines are wrapped in the iCal description to remain RFC‑friendly.

## Project structure

- `generate_calendar.py` — main script (discover schools; fetch, parse; build `.ics`).
- `requirements.txt` — Python dependencies (minimal: `requests`).
- `.github/workflows/update-calendars.yml` — optional weekly auto‑update workflow.
- `docs/index.md` — GitHub Pages site with school selector and subscribe links.
- `docs/<school-slug>_lunch.ics` — per‑school calendars served by GitHub Pages.
- `windsong_lunch.ics` — legacy Windsong Elementary calendar (kept in sync if present).

## Contributing

PRs welcome for:

- Better handling of school‑specific menu type slugs.
- Alternative districts via config.
- Better error handling or richer event metadata.

Open an issue if Nutrislice changes break the endpoint format; include the district and a sample working API URL from your browser network tab.

## GitHub Pages

To host a small site with subscribe instructions and a stable link:

- In repository Settings → Pages, set “Source” to “Deploy from a branch”.
- Choose Branch: `main`, Folder: `/docs`.
- Save. Your site will be available at a URL like:
  - `https://<org-or-user>.github.io/<repo>/`
  - Calendar files will be at: `https://<org-or-user>.github.io/<repo>/<school-slug>_lunch.ics`

The generator keeps `docs/` current. The `docs/index.md` page includes a school selector and quick subscribe steps for Google Calendar, Apple Calendar, iOS, and Outlook.
