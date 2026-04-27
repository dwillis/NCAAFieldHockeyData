"""NCAA women's field hockey player stats scraper.

Reads URLs from url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv and
writes data/ncaa_womens_field_hockey_playerstats_{season}.csv. Navigates the
matchstatsurl (game-by-game page), follows the 'Team Statistics' link, and
parses the #stat_grid table there. Some schools' /team/{id}/stats/{ctl}
URLs return "Invalid path", so we go through matchstatsurl instead.

Usage:
    uv run NCAAFieldHockeyPlayerScraper.py [season] [limit]
"""
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT_URL = "https://stats.ncaa.org"


def clean_value(val: str | None) -> str:
    if val is None:
        return ""
    val = val.strip()
    if val.endswith("/"):
        val = val[:-1].strip()
    return val


def to_numeric(val: object) -> float:
    if val is None:
        return float("nan")
    s = str(val).strip().replace(",", "")
    if s in ("", "-", "/"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def split_name(display: str) -> tuple[str, str, str]:
    """Return (full_name, first_name, last_name). NCAA is 'Last, First'."""
    if "," in display:
        last, first = display.split(",", 1)
        last, first = last.strip(), first.strip()
        return f"{first} {last}", first, last
    parts = display.split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""
    return display.strip(), first, last


def split_height(ht: str) -> tuple[object, object]:
    if not ht or "-" not in ht:
        return pd.NA, pd.NA
    f, i = ht.split("-", 1)
    try:
        return int(f), int(i)
    except ValueError:
        return pd.NA, pd.NA


def extract_team_id(url: str) -> str | None:
    m = re.search(r"/team/(\d+)/stats", url)
    if m:
        return m.group(1)
    return parse_qs(urlparse(url).query).get("org_id", [None])[0]


def school_name(page) -> str:
    el = page.query_selector(
        "xpath=/html/body/div[2]/div/div/div/div/div/div[1]/img"
    )
    if el:
        alt = el.get_attribute("alt")
        if alt:
            return alt.strip()
    card = page.query_selector(".card-header")
    if card:
        m = re.match(r"(.*?)\s*\(\d+-\d+-?\d*\)", card.inner_text().strip())
        if m:
            return m.group(1).strip()
    return ""


def process_team(page, match_url: str, season: str) -> pd.DataFrame | None:
    team_id = extract_team_id(match_url)

    try:
        page.goto(match_url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading match page: {e}")
        return None

    team_stats_link = page.query_selector('a:text("Team Statistics")')
    if not team_stats_link:
        print("  No 'Team Statistics' link found")
        return None
    href = team_stats_link.get_attribute("href")
    if not href:
        print("  Team Statistics link has no href")
        return None

    try:
        page.goto(ROOT_URL + href, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading team stats page: {e}")
        return None

    team_name = school_name(page) or "Unknown"

    grid = page.query_selector("#stat_grid")
    if not grid:
        print(f"  No stat_grid table found for {team_name}")
        return None

    header_row = grid.query_selector("thead tr") or grid.query_selector("tr")
    if not header_row:
        return None
    header_cells = header_row.query_selector_all("th")
    headers = [
        c.inner_text().strip().lower().replace(" ", "_").replace("%", "_pct")
        for c in header_cells
    ]
    col_map = {"#": "jersey", "player": "roster_name"}
    headers = [col_map.get(h, h) for h in headers]

    body_rows = grid.query_selector_all("tbody tr")
    players: list[dict] = []
    for row in body_rows:
        cells = row.query_selector_all("td")
        if len(cells) != len(headers):
            continue
        values = [clean_value(c.inner_text()) for c in cells]
        record = dict(zip(headers, values))

        display = record.get("roster_name", "")
        if display in ("Totals", "Opponent Totals", "TEAM", ""):
            continue
        if record.get("jersey", "") == "-":
            continue

        player_ncaa_id = ""
        if "roster_name" in headers:
            cell = cells[headers.index("roster_name")]
            link = cell.query_selector("a")
            if link:
                lhref = link.get_attribute("href") or ""
                m = re.search(r"stats_player_seq=(\d+)", lhref)
                if m:
                    player_ncaa_id = m.group(1)

        full, first, last = split_name(display)
        record["full_name"] = full
        record["first_name"] = first
        record["last_name"] = last
        ht = record.pop("ht", "")
        feet, inches = split_height(ht)
        record["feet"] = feet
        record["inches"] = inches
        record["team"] = team_name
        record["ncaa_id"] = team_id
        record["player_ncaa_id"] = player_ncaa_id
        record["season"] = season

        players.append(record)

    if not players:
        print(f"  No players found for {team_name}")
        return None

    df = pd.DataFrame(players)

    non_numeric = {
        "season", "team", "ncaa_id", "player_ncaa_id", "jersey",
        "full_name", "roster_name", "first_name", "last_name", "yr", "pos",
    }
    for col in df.columns:
        if col not in non_numeric and col not in ("feet", "inches"):
            df[col] = df[col].apply(to_numeric)

    preferred = [
        "ncaa_id", "team", "season", "jersey", "full_name", "roster_name",
        "last_name", "first_name", "yr", "pos", "feet", "inches",
        "gp", "gs",
        "goals", "assists", "points", "sh_att", "so_g",
        "fouls", "rc", "yc", "gc",
        "ggp", "ggs", "min", "ga", "gaa", "sv", "sv_pct", "sho",
        "g_wins", "g_loss", "d_sv", "corners", "ps", "psa", "gw",
        "player_ncaa_id",
    ]
    ordered = [c for c in preferred if c in df.columns]
    extras = [c for c in df.columns if c not in ordered]
    return df[ordered + extras]


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else "2025"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv"
    output_file = f"data/ncaa_womens_field_hockey_playerstats_{season}.csv"

    print(f"Reading URLs from {urls_file}")
    urls_df = pd.read_csv(urls_file)
    urls = urls_df["matchstatsurl"].tolist()
    if limit:
        urls = urls[:limit]
    print(f"Processing {len(urls)} teams")

    all_players: list[pd.DataFrame] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        for i, url in enumerate(urls):
            print(f"[{i+1}/{len(urls)}] Processing {url}")
            try:
                result = process_team(page, url, season)
                if result is not None and not result.empty:
                    all_players.append(result)
                    print(f"  Fetching {result['team'].iloc[0]} ({len(result)} players)")
                else:
                    print("  Skipped (no data)")
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(1)
        browser.close()

    if all_players:
        final = pd.concat(all_players, ignore_index=True)
        final = final.dropna(how="all").dropna(subset=["full_name"])
        final.to_csv(output_file, index=False)
        print(f"\nWrote {len(final)} players to {output_file}")
    else:
        print("\nNo data collected!")


if __name__ == "__main__":
    main()
