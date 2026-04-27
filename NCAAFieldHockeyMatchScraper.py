"""NCAA women's field hockey match stats scraper.

Reads URLs from url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv and
writes data/ncaa_womens_field_hockey_matchstats_{season}.csv. Each NCAA box
score exposes a team row and a "Defensive Totals" row (the opponent's
stats); the two are merged side-by-side with defensive_ prefixes.

Usage:
    uv run NCAAFieldHockeyMatchScraper.py [season] [limit]
"""
import re
import sys
import time
from urllib.parse import parse_qs, urlparse

import pandas as pd
from playwright.sync_api import sync_playwright


def extract_team_id(url: str) -> str | None:
    return parse_qs(urlparse(url).query).get("org_id", [None])[0]


def clean_value(val: str | None) -> str:
    if val is None:
        return ""
    val = val.strip()
    if val.endswith("/"):
        val = val[:-1].strip()
    return val


def parse_breakdown(page) -> pd.DataFrame | None:
    table = page.query_selector("#game_breakdown_div table")
    if not table:
        return None
    rows = table.query_selector_all("tr")

    headers: list[str] = []
    data_start = 0
    for i, row in enumerate(rows):
        th_cells = row.query_selector_all("th")
        td_cells = row.query_selector_all("td")
        if th_cells and not td_cells:
            texts = [c.inner_text().strip() for c in th_cells]
            if "Date" in texts and "Opponent" in texts:
                headers = [
                    t.lower().replace(" ", "_").replace("/", "").replace("%", "_pct")
                    for t in texts
                ]
                data_start = i + 1
                break
    if not headers:
        return None

    all_rows = []
    for row in rows[data_start:]:
        cells = row.query_selector_all("td")
        if len(cells) != len(headers):
            continue
        values = [clean_value(c.inner_text()) for c in cells]
        all_rows.append(dict(zip(headers, values)))
    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    df["date"] = df["date"].replace("", pd.NA).ffill()
    df["result"] = df["result"].replace("", pd.NA).ffill()
    return df


def parse_result(result: str) -> tuple[str, str, str]:
    """Return (team_score, opponent_score, WLT)."""
    if not result:
        return "", "", ""
    result = result.strip()
    wlt = ""
    m = re.match(r"^([WLT])\s+", result)
    if m:
        wlt = m.group(1)
        result = result[m.end():]
    parts = result.split("-")
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip(), wlt
    return "", "", wlt


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


def process_team(page, url: str) -> pd.DataFrame | None:
    team_id = extract_team_id(url)
    try:
        page.goto(url, timeout=30000)
        time.sleep(2)
    except Exception as e:
        print(f"  Error loading page: {e}")
        return None

    school = school_name(page)
    if not school:
        print(f"  Could not find team name for {url}")
        return None

    base = parse_breakdown(page)
    if base is None or base.empty:
        print(f"  No match data found for {school}")
        return None

    teamside = base[base["opponent"] != "Defensive Totals"].copy()
    defside = base[base["opponent"] == "Defensive Totals"].copy()

    if teamside.empty:
        print(f"  No team rows for {school}")
        return None

    teamside["home_away"] = teamside["opponent"].apply(
        lambda x: "Away" if x.startswith("@") else "Home"
    )
    teamside["opponent"] = teamside["opponent"].apply(
        lambda x: re.sub(r"^@\s*", "", x).split("\n")[0].strip()
    )
    teamside["opponent"] = teamside["opponent"].apply(
        lambda x: re.sub(r"\s*@.*,\s*[A-Z]{2}$", "", x)
    )
    scores = teamside["result"].apply(parse_result)
    teamside["team_score"] = scores.apply(lambda x: x[0])
    teamside["opponent_score"] = scores.apply(lambda x: x[1])
    teamside["result"] = scores.apply(lambda x: x[2])
    teamside["team"] = school
    teamside["date"] = pd.to_datetime(teamside["date"], format="%m/%d/%Y", errors="coerce")

    stat_cols = [c for c in teamside.columns if c not in (
        "date", "team", "opponent", "home_away", "result",
        "team_score", "opponent_score",
    )]
    team_out = teamside[[
        "date", "team", "opponent", "home_away", "result",
        "team_score", "opponent_score", *stat_cols,
    ]].copy()

    if defside.empty:
        print(f"  No defensive totals for {school}")
        return None

    defside["date"] = pd.to_datetime(defside["date"], format="%m/%d/%Y", errors="coerce")
    def_scores = defside["result"].apply(parse_result)
    defside["team_score"] = def_scores.apply(lambda x: x[0])
    defside["opponent_score"] = def_scores.apply(lambda x: x[1])
    defside["result"] = def_scores.apply(lambda x: x[2])
    defside["team"] = school
    def_stat_cols = [c for c in stat_cols if c in defside.columns]
    def_out = defside[[
        "date", "team", "result", "team_score", "opponent_score",
        *def_stat_cols,
    ]].rename(columns={c: f"defensive_{c}" for c in def_stat_cols})

    def_out = def_out.drop_duplicates(subset=["date"], keep="first")

    joined = team_out.merge(
        def_out,
        on=["date", "team", "result", "team_score", "opponent_score"],
        how="inner",
    )
    joined["ncaa_id"] = team_id

    numeric_cols = [c for c in joined.columns if c not in (
        "date", "team", "opponent", "home_away", "result", "ncaa_id",
    )]
    for col in numeric_cols:
        joined[col] = pd.to_numeric(joined[col], errors="coerce")

    front = ["ncaa_id", "date", "team", "opponent", "home_away", "result",
             "team_score", "opponent_score"]
    rest = [c for c in joined.columns if c not in front]
    return joined[front + rest]


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else "2025"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    urls_file = f"url_csvs/ncaa_womens_field_hockey_teamurls_{season}.csv"
    output_file = f"data/ncaa_womens_field_hockey_matchstats_{season}.csv"

    print(f"Reading URLs from {urls_file}")
    urls_df = pd.read_csv(urls_file)
    urls = urls_df["matchstatsurl"].tolist()
    if limit:
        urls = urls[:limit]
    print(f"Processing {len(urls)} teams")

    all_matches: list[pd.DataFrame] = []
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
                result = process_team(page, url)
                if result is not None and not result.empty:
                    all_matches.append(result)
                    print(f"  Adding {result['team'].iloc[0]} ({len(result)} matches)")
                else:
                    print("  Skipped (no data)")
            except Exception as e:
                print(f"  Error: {e}")
            time.sleep(1)
        browser.close()

    if all_matches:
        final = pd.concat(all_matches, ignore_index=True).drop_duplicates()
        final.to_csv(output_file, index=False)
        print(f"\nWrote {len(final)} matches to {output_file}")
    else:
        print("\nNo data collected!")


if __name__ == "__main__":
    main()
