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


def count_actions_runs(owner: str, repo: str, date_str: str, token: str) -> int:
    """Count Actions runs whose created_at falls on date_str (UTC, YYYY-MM-DD)."""
    total = 0
    page = 1
    # GitHub supports `created` as a date range: YYYY-MM-DD..YYYY-MM-DD
    date_range = f"{date_str}..{date_str}"
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
        total += len(runs)
        if len(runs) < 100:
            break
        page += 1
        time.sleep(0.2)  # gentle on rate limits
    return total


def find_day(items: list, date_str: str, timestamp_key: str = "timestamp") -> dict:
    """Find the item whose timestamp starts with date_str."""
    for item in items or []:
        ts = item.get(timestamp_key, "")
        if ts.startswith(date_str):
            return item
    return {}


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

    # Traffic endpoints
    views_data = gh_get(f"/repos/{owner}/{repo}/traffic/views?per=day", token)
    clones_data = gh_get(f"/repos/{owner}/{repo}/traffic/clones?per=day", token)
    referrers = gh_get(f"/repos/{owner}/{repo}/traffic/popular/referrers", token)
    paths = gh_get(f"/repos/{owner}/{repo}/traffic/popular/paths", token)
    actions_runs = count_actions_runs(owner, repo, date_str, token)

    today_views = find_day(views_data.get("views", []) if views_data else [], date_str)
    today_clones = find_day(clones_data.get("clones", []) if clones_data else [], date_str)

    views_count = today_views.get("count", 0)
    views_uniques = today_views.get("uniques", 0)
    clones_count = today_clones.get("count", 0)
    clones_uniques = today_clones.get("uniques", 0)

    # CI normalization: GH Actions runners are few IPs, so uniques are mostly
    # already human. The raw count is inflated by each individual run checkout.
    human_clones_count = max(0, clones_count - actions_runs)

    snapshot = {
        "date": date_str,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "views_count": views_count,
        "views_uniques": views_uniques,
        "clones_count": clones_count,
        "clones_uniques": clones_uniques,
        "actions_runs": actions_runs,
        "human_clones_count": human_clones_count,
        # Unique cloners already mostly human (CI shares IPs -> few uniques)
        "human_clones_uniques": clones_uniques,
        "top_referrers": referrers or [],
        "top_paths": paths or [],
    }

    print(
        f"views={views_count}/{views_uniques} "
        f"clones={clones_count}/{clones_uniques} "
        f"ci_runs={actions_runs} "
        f"human_clones={human_clones_count}"
    )

    if dry_run:
        return snapshot

    # Load existing data file
    data_dir.mkdir(parents=True, exist_ok=True)
    data_file = data_dir / f"{repo}.json"
    if data_file.exists():
        with open(data_file, encoding="utf-8") as f:
            repo_data = json.load(f)
    else:
        repo_data = {"repo": repo, "owner": owner, "snapshots": []}

    # Upsert by date (idempotent re-runs)
    existing = {s["date"]: i for i, s in enumerate(repo_data["snapshots"])}
    if date_str in existing:
        repo_data["snapshots"][existing[date_str]] = snapshot
    else:
        repo_data["snapshots"].append(snapshot)

    repo_data["snapshots"].sort(key=lambda s: s["date"])

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
    data_dir = REPO_ROOT / "telemetry" / "data"

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
        summary_file = REPO_ROOT / "telemetry" / "summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)

    print(f"\nDone: {len(results) - errors} ok, {errors} errors")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
