"""
Generate a teamurls CSV for NCAA D1 women's field hockey.

Fetches the ncaa_stats_py-style team list (team_id + school_name) from the
NCAA rankings page directly via Playwright, then looks up school_id from
~/.ncaa_stats_py/schools.csv (populated by ncaa_stats_py). Finally scrapes
the current game_sport_year_ctl_id from a team page and writes:

    url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv

Usage:
    uv run generate_team_urls.py <season>

    season: year (e.g. 2025)

ncaa_stats_py is still listed as a dependency so its cached schools.csv is
available; we sidestep its Playwright helper (which crashes on macOS due
to --single-process).
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

ROOT = "https://stats.ncaa.org"
SCHOOLS_CSV = Path.home() / ".ncaa_stats_py" / "schools.csv"
SPORT_CODE = "WFH"  # Women's field hockey (fall sport)


def load_schools() -> pd.DataFrame:
    if not SCHOOLS_CSV.exists():
        raise FileNotFoundError(
            f"{SCHOOLS_CSV} not found. Run any ncaa_stats_py call once to "
            "populate it, or create it manually with school_id,school_name "
            "columns."
        )
    return pd.read_csv(SCHOOLS_CSV)


async def fetch_html(page, url: str, wait_ms: int = 4000) -> str:
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(wait_ms)
    return await page.content()


def parse_rp(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    sel = soup.find("select", {"id": "rp"})
    if not sel:
        return None
    for opt in sel.find_all("option"):
        if "final" in opt.text.lower():
            return opt.get("value")
    for opt in sel.find_all("option"):
        if "-" not in opt.text:
            return opt.get("value")
    return None


def parse_teams(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", {"id": "stat_grid"})
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []
    rows: list[dict] = []
    for tr in tbody.find_all("tr"):
        a = tr.find("a")
        if not a:
            continue
        m = re.search(r"/teams/(\d+)", a.get("href", ""))
        if not m:
            continue
        tds = tr.find_all("td")
        school_name = tds[0].get_text(strip=True)
        conference = tds[1].get_text(strip=True) if len(tds) > 1 else ""
        rows.append({
            "team_id": int(m.group(1)),
            "school_name": school_name,
            "team_conference_name": conference,
        })
    return rows


async def find_ctl_id(page, school_id: int) -> str | None:
    html = await fetch_html(page, f"{ROOT}/teams/{school_id}", wait_ms=5000)
    ctl_ids = set(re.findall(r"game_sport_year_ctl_id=(\d+)", html))
    return max(ctl_ids, key=int) if ctl_ids else None


async def run(season: int) -> None:
    # Field hockey is a fall sport; NCAA academic_year = season + 1.
    academic_year = season + 1
    output_file = f"url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv"

    schools_df = load_schools()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        rp_url = (
            f"{ROOT}/rankings/change_sport_year_div?"
            f"academic_year={academic_year}.0&division=1.0&sport_code={SPORT_CODE}"
        )
        print(f"Fetching ranking periods from {rp_url}")
        rp_html = await fetch_html(page, rp_url)
        rp = parse_rp(rp_html)
        if not rp:
            print("Could not find a ranking period")
            sys.exit(1)
        print(f"Using ranking_period={rp}")

        teams_url = (
            f"{ROOT}/rankings/institution_trends?"
            f"academic_year={academic_year}.0&division=1.0&"
            f"ranking_period={rp}&sport_code={SPORT_CODE}"
        )
        print(f"Fetching team list from {teams_url}")
        teams_html = await fetch_html(page, teams_url)
        teams = parse_teams(teams_html)
        if not teams:
            print("No teams parsed from rankings page")
            sys.exit(1)
        print(f"Found {len(teams)} teams")

        teams_df = pd.DataFrame(teams).merge(
            schools_df, on="school_name", how="left"
        )
        missing = teams_df["school_id"].isna().sum()
        if missing:
            print(f"Warning: {missing} teams could not be matched to a school_id")
        teams_df = teams_df.dropna(subset=["school_id"]).copy()
        teams_df["school_id"] = teams_df["school_id"].astype(int)

        first_team_id = int(teams_df.iloc[0]["team_id"])
        print(f"Finding game_sport_year_ctl_id from team page {first_team_id}...")
        ctl_id = await find_ctl_id(page, first_team_id)
        if not ctl_id:
            print("Could not find game_sport_year_ctl_id!")
            sys.exit(1)
        print(f"Using game_sport_year_ctl_id={ctl_id}")

        await browser.close()

    rows = []
    for _, row in teams_df.iterrows():
        school_id = int(row["school_id"])
        rows.append({
            "school": row["school_name"],
            "playerstatsurl": f"{ROOT}/team/{school_id}/stats/{ctl_id}",
            "matchstatsurl": (
                f"{ROOT}/player/game_by_game?"
                f"game_sport_year_ctl_id={ctl_id}"
                f"&org_id={school_id}&stats_player_seq=-100"
            ),
        })

    out = pd.DataFrame(rows).sort_values("school").reset_index(drop=True)
    os.makedirs("url_csvs", exist_ok=True)
    out.to_csv(output_file, index=False)
    print(f"Wrote {len(out)} teams to {output_file}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: uv run generate_team_urls.py <season>")
        sys.exit(1)
    season = int(sys.argv[1])
    asyncio.run(run(season))


if __name__ == "__main__":
    main()
