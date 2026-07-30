#!/usr/bin/env python3
"""
Daily telemetry snapshot for portfolio repos.

Fetches views, clones, referrers, and paths from the GitHub Traffic API.
Normalizes clone counts by subtracting Actions runs (CI clones inflate the signal).

Usage:
    GH_TOKEN=<token> python snapshot.py [--date YYYY-MM-DD] [--dry-run]
"""
import json
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import urllib.request
import urllib.error
import time


BASE_URL = "https://api.github.com"
REPO_ROOT = Path(__file__).parent.parent.parent

# Outputs go INSIDE docs/, because docs/ is what GitHub Pages publishes. Writing
# them to telemetry/ put every file outside the published tree, so the dashboard's
# relative fetches ("telemetry/data/<repo>.json") resolved to paths Pages does not
# serve and every request 404'd - a dashboard that could never show data.
# Config stays in telemetry/repos.json (hand-edited input); a copy is emitted here
# so the page can read it over HTTP like the rest.
OUTPUT_DIR = REPO_ROOT / "docs" / "telemetry"


def gh_get(path: str, token: str) -> dict | list | None:
    """Authenticated GitHub API GET request. Returns None on error."""
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"  HTTP {e.code} for {path}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Error fetching {path}: {e}", file=sys.stderr)
        return None


def actions_runs_by_day(
    owner: str, repo: str, start_date: str, end_date: str, token: str
) -> dict[str, int]:
    """Count Actions runs per UTC day across a date range.

    One paginated query for the whole window instead of one per day: the window
    is 14 days wide and this runs for every repo, so per-day queries would be
    14x the API calls for the same answer.
    """
    counts: dict[str, int] = {}
    page = 1
    date_range = f"{start_date}..{end_date}"
    while True:
        data = gh_get(
            f"/repos/{owner}/{repo}/actions/runs"
            f"?created={date_range}&per_page=100&page={page}",
            token,
        )
        if not data or "workflow_runs" not in data:
            break
        runs = data["workflow_runs"]
        if not runs:
            break
        for run in runs:
            day = (run.get("created_at") or "")[:10]
            if day:
                counts[day] = counts.get(day, 0) + 1
        if len(runs) < 100:
            break
        page += 1
        time.sleep(0.2)  # gentle on rate limits
    return counts


def snapshot_repo(
    owner: str,
    repo: str,
    date_str: str,
    token: str,
    data_dir: Path,
    dry_run: bool = False,
) -> dict:
    """Snapshot traffic for one repo and merge into its data file."""
    print(f"  {owner}/{repo} ...", end=" ", flush=True)

    # Traffic endpoints. views/clones carry the whole 14-day window GitHub keeps.
    views_data = gh_get(f"/repos/{owner}/{repo}/traffic/views?per=day", token)
    clones_data = gh_get(f"/repos/{owner}/{repo}/traffic/clones?per=day", token)
    referrers = gh_get(f"/repos/{owner}/{repo}/traffic/popular/referrers", token)
    paths = gh_get(f"/repos/{owner}/{repo}/traffic/popular/paths", token)

    views_by_day = {
        d["timestamp"][:10]: d for d in (views_data or {}).get("views", [])
    }
    clones_by_day = {
        d["timestamp"][:10]: d for d in (clones_data or {}).get("clones", [])
    }

    # Rewrite EVERY day the API still knows about, not only date_str. A day asked
    # for before GitHub had consolidated it comes back as zero, and the old
    # write-once-per-date behavior froze that zero forever even though the real
    # number landed minutes later. Re-reading the window makes late data self-heal.
    days = sorted(set(views_by_day) | set(clones_by_day) | {date_str})
    runs_by_day = actions_runs_by_day(owner, repo, days[0], days[-1], token)
    newest = days[-1]

    # Load existing data file first: past days keep the referrer/path aggregate
    # captured while they were current.
    data_file = data_dir / f"{repo}.json"
    if data_file.exists():
        with open(data_file, encoding="utf-8") as f:
            repo_data = json.load(f)
    else:
        repo_data = {"repo": repo, "owner": owner, "snapshots": []}
    stored = {s["date"]: s for s in repo_data.get("snapshots", [])}

    captured_at = datetime.now(timezone.utc).isoformat()
    rebuilt = []
    for day in days:
        v = views_by_day.get(day, {})
        c = clones_by_day.get(day, {})
        clones_count = c.get("count", 0)
        actions_runs = runs_by_day.get(day, 0)
        prev = stored.get(day, {})

        # referrers/paths are a rolling 14-day aggregate, not a daily measure:
        # copying them onto every day would let a consumer count the same visit
        # fourteen times. Only the newest day carries the current aggregate.
        if day == newest:
            day_referrers, day_paths = referrers or [], paths or []
        else:
            day_referrers = prev.get("top_referrers", [])
            day_paths = prev.get("top_paths", [])

        rebuilt.append({
            "date": day,
            "captured_at": captured_at,
            "views_count": v.get("count", 0),
            "views_uniques": v.get("uniques", 0),
            "clones_count": clones_count,
            "clones_uniques": c.get("uniques", 0),
            "actions_runs": actions_runs,
            # CI normalization: GH Actions runners are few IPs, so uniques are
            # mostly already human. The raw count is inflated by each checkout.
            "human_clones_count": max(0, clones_count - actions_runs),
            # Unique cloners already mostly human (CI shares IPs -> few uniques)
            "human_clones_uniques": c.get("uniques", 0),
            "top_referrers": day_referrers,
            "top_paths": day_paths,
        })

    # date_str is always in `days`, so the requested day is always present here.
    by_date = {s["date"]: s for s in rebuilt}
    snapshot = by_date[date_str]

    print(
        f"views={snapshot['views_count']}/{snapshot['views_uniques']} "
        f"clones={snapshot['clones_count']}/{snapshot['clones_uniques']} "
        f"ci_runs={snapshot['actions_runs']} "
        f"human_clones={snapshot['human_clones_count']} "
        f"({len(rebuilt)} day(s) refreshed)"
    )

    if dry_run:
        return snapshot

    # Days older than the API window survive untouched; the refreshed ones win.
    stored.update(by_date)
    repo_data["snapshots"] = sorted(stored.values(), key=lambda s: s["date"])

    data_dir.mkdir(parents=True, exist_ok=True)
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(repo_data, f, indent=2, ensure_ascii=False)

    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot GitHub portfolio traffic")
    parser.add_argument(
        "--date",
        default=None,
        help="Snapshot date YYYY-MM-DD (default: yesterday UTC)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch data but do not write files",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("ERROR: GH_TOKEN environment variable not set", file=sys.stderr)
        return 1

    if args.date:
        date_str = args.date
    else:
        date_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    config_file = REPO_ROOT / "telemetry" / "repos.json"
    if not config_file.exists():
        print(f"ERROR: config not found: {config_file}", file=sys.stderr)
        return 1

    with open(config_file, encoding="utf-8") as f:
        config = json.load(f)

    owner = config["owner"]
    data_dir = OUTPUT_DIR / "data"

    # The page fetches the repo list too, so mirror the config into the published
    # tree. telemetry/repos.json stays the source of truth that a human edits.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(config_file, encoding="utf-8") as f:
        _cfg_raw = f.read()
    with open(OUTPUT_DIR / "repos.json", "w", encoding="utf-8") as f:
        f.write(_cfg_raw)

    print(f"Snapshotting {len(config['repos'])} repos for {date_str} (dry_run={args.dry_run})")
    results = []
    errors = 0

    for repo_cfg in config["repos"]:
        repo = repo_cfg["name"]
        try:
            snap = snapshot_repo(owner, repo, date_str, token, data_dir, dry_run=args.dry_run)
            results.append({"repo": repo, "status": "ok", "snapshot": snap})
        except Exception as e:  # pylint: disable=broad-except
            print(f"  ERROR: {e}", file=sys.stderr)
            results.append({"repo": repo, "status": "error", "error": str(e)})
            errors += 1

    if not args.dry_run:
        summary = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "snapshot_date": date_str,
            "repos": [
                {k: v for k, v in r.items() if k != "snapshot"}
                for r in results
            ],
        }
        summary_file = OUTPUT_DIR / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    print(f"\nDone: {len(results) - errors} ok, {errors} errors")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
