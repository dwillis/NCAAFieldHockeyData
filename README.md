# NCAA Field Hockey Data

Scrapers and data for NCAA Division I women's field hockey, sourced from
[stats.ncaa.org](https://stats.ncaa.org).

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run playwright install chromium
```

The team URL generator reads from `~/.ncaa_stats_py/schools.csv`. If that
file does not yet exist, run any `ncaa_stats_py` call once to populate it.

## Usage

Generate the team URL CSV for a given season (year is the calendar year the
season starts in, e.g. 2025 for the 2025–26 academic year):

```bash
uv run generate_team_urls.py 2025
```

Then run the scrapers, which read that CSV and write to `data/`:

```bash
uv run NCAAFieldHockeyMatchScraper.py 2025
uv run NCAAFieldHockeyPlayerScraper.py 2025
uv run NCAAFieldHockeyReportScraper.py 2025
```

Each scraper accepts an optional `[limit]` second arg for testing against
a small number of teams.

## Outputs

- `url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv` — per-team
  player- and match-stats URLs.
- `data/ncaa_womens_field_hockey_matchstats_{season}.csv` — game-by-game
  team stats with merged opponent (defensive) totals.
- `data/ncaa_womens_field_hockey_playerstats_{season}.csv` — season player
  stats per team.
- `data/ncaa_womens_field_hockey_{report}_{season}.csv` — season-level
  reports (attendance, toughest schedule, streaks, etc).

## Legacy R scripts

The original R scrapers (`*.R`) are kept for reference but are no longer
the primary path.
