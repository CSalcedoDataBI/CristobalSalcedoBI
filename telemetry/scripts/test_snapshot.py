#!/usr/bin/env python3
"""Unit tests for snapshot.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))  # noqa: E402
import snapshot  # noqa: E402


class TestFindDay(unittest.TestCase):
    def test_finds_matching_timestamp(self):
        items = [
            {"timestamp": "2026-07-27T00:00:00Z", "count": 10, "uniques": 3},
            {"timestamp": "2026-07-28T00:00:00Z", "count": 25, "uniques": 8},
        ]
        result = snapshot.find_day(items, "2026-07-28")
        self.assertEqual(result["count"], 25)

    def test_returns_empty_dict_when_not_found(self):
        items = [{"timestamp": "2026-07-27T00:00:00Z", "count": 5, "uniques": 1}]
        result = snapshot.find_day(items, "2026-07-28")
        self.assertEqual(result, {})

    def test_handles_none_items(self):
        result = snapshot.find_day(None, "2026-07-28")
        self.assertEqual(result, {})

    def test_handles_empty_list(self):
        result = snapshot.find_day([], "2026-07-28")
        self.assertEqual(result, {})


class TestNormalization(unittest.TestCase):
    """Verify that human clone count is correctly normalized."""

    def _make_mock_responses(self, clones_count, views_count, actions_runs_count):
        """Build mock API return values."""
        views_resp = {
            "views": [{"timestamp": "2026-07-28T00:00:00Z", "count": views_count, "uniques": 5}]
        }
        clones_resp = {
            "clones": [{"timestamp": "2026-07-28T00:00:00Z", "count": clones_count, "uniques": 6}]
        }
        referrers_resp = []
        paths_resp = []
        runs_resp = {
            "workflow_runs": [{}] * actions_runs_count,
            "total_count": actions_runs_count,
        }
        return views_resp, clones_resp, referrers_resp, paths_resp, runs_resp

    def test_human_clones_subtracts_actions_runs(self):
        views_resp, clones_resp, referrers, paths, runs_resp = self._make_mock_responses(
            clones_count=100, views_count=20, actions_runs_count=80
        )
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(snapshot, "gh_get") as mock_get, \
             patch.object(snapshot, "actions_runs_by_day") as mock_runs:
            mock_runs.return_value = {"2026-07-28": 80}
            mock_get.side_effect = [views_resp, clones_resp, referrers, paths]
            result = snapshot.snapshot_repo(
                "CSalcedoDataBI", "test-repo", "2026-07-28",
                "fake-token", Path(tmpdir), dry_run=True
            )
        self.assertEqual(result["human_clones_count"], 20)
        self.assertEqual(result["clones_count"], 100)
        self.assertEqual(result["actions_runs"], 80)

    def test_human_clones_floored_at_zero(self):
        """When CI runs exceed total clones, human count is 0, not negative."""
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(snapshot, "gh_get") as mock_get, \
             patch.object(snapshot, "actions_runs_by_day") as mock_runs:
            mock_runs.return_value = {"2026-07-28": 200}
            mock_get.side_effect = [
                {"views": [{"timestamp": "2026-07-28T00:00:00Z", "count": 5, "uniques": 2}]},
                {"clones": [{"timestamp": "2026-07-28T00:00:00Z", "count": 50, "uniques": 3}]},
                [],
                [],
            ]
            result = snapshot.snapshot_repo(
                "CSalcedoDataBI", "test-repo", "2026-07-28",
                "fake-token", Path(tmpdir), dry_run=True
            )
        self.assertGreaterEqual(result["human_clones_count"], 0)

    def test_no_ci_on_weekend_all_human(self):
        """On a day with 0 CI runs, all clones are counted as human."""
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(snapshot, "gh_get") as mock_get, \
             patch.object(snapshot, "actions_runs_by_day") as mock_runs:
            mock_runs.return_value = {"2026-07-26": 0}
            mock_get.side_effect = [
                {"views": [{"timestamp": "2026-07-26T00:00:00Z", "count": 10, "uniques": 6}]},
                {"clones": [{"timestamp": "2026-07-26T00:00:00Z", "count": 16, "uniques": 14}]},
                [],
                [],
            ]
            result = snapshot.snapshot_repo(
                "CSalcedoDataBI", "test-repo", "2026-07-26",
                "fake-token", Path(tmpdir), dry_run=True
            )
        self.assertEqual(result["human_clones_count"], 16)
        self.assertEqual(result["actions_runs"], 0)


class TestUpsert(unittest.TestCase):
    """Verify idempotent merge into data file."""

    def _run_snapshot(self, tmpdir, date_str, clones_count, ci_runs):
        with patch.object(snapshot, "gh_get") as mock_get, \
             patch.object(snapshot, "actions_runs_by_day") as mock_runs:
            mock_runs.return_value = {date_str: ci_runs}
            mock_get.side_effect = [
                {"views": [{"timestamp": f"{date_str}T00:00:00Z", "count": 10, "uniques": 5}]},
                {"clones": [{
                    "timestamp": f"{date_str}T00:00:00Z",
                    "count": clones_count, "uniques": 5,
                }]},
                [],
                [],
            ]
            snapshot.snapshot_repo(
                "CSalcedoDataBI", "repo-a", date_str,
                "fake-token", Path(tmpdir)
            )

    def test_two_runs_same_date_no_duplicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run_snapshot(tmpdir, "2026-07-28", clones_count=30, ci_runs=10)
            self._run_snapshot(tmpdir, "2026-07-28", clones_count=35, ci_runs=10)

            data_file = Path(tmpdir) / "repo-a.json"
            with open(data_file) as f:
                data = json.load(f)

        dates = [s["date"] for s in data["snapshots"]]
        self.assertEqual(len(dates), 1)
        self.assertEqual(dates[0], "2026-07-28")
        # Second run overwrites — reflects latest fetch
        self.assertEqual(data["snapshots"][0]["clones_count"], 35)

    def test_accumulates_multiple_dates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for day in ["2026-07-26", "2026-07-27", "2026-07-28"]:
                self._run_snapshot(tmpdir, day, clones_count=20, ci_runs=5)

            data_file = Path(tmpdir) / "repo-a.json"
            with open(data_file) as f:
                data = json.load(f)

        dates = [s["date"] for s in data["snapshots"]]
        self.assertEqual(dates, ["2026-07-26", "2026-07-27", "2026-07-28"])

    def test_snapshots_sorted_by_date(self):
        """Ensure snapshots are always sorted ascending regardless of insertion order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for day in ["2026-07-28", "2026-07-26", "2026-07-27"]:
                self._run_snapshot(tmpdir, day, clones_count=10, ci_runs=2)

            data_file = Path(tmpdir) / "repo-a.json"
            with open(data_file) as f:
                data = json.load(f)

        dates = [s["date"] for s in data["snapshots"]]
        self.assertEqual(dates, sorted(dates))


class TestActionsRunsByDay(unittest.TestCase):
    """Runs are fetched once for the whole window and bucketed per UTC day."""

    def _run(day, n):  # noqa: N805 - helper, not a test method
        return [{"created_at": f"{day}T0{i}:00:00Z"} for i in range(n)]

    def test_buckets_runs_by_day(self):
        page1 = {"workflow_runs": TestActionsRunsByDay._run("2026-07-27", 3)
                 + TestActionsRunsByDay._run("2026-07-28", 2)}
        with patch.object(snapshot, "gh_get", side_effect=[page1]), patch("time.sleep"):
            counts = snapshot.actions_runs_by_day("o", "r", "2026-07-27", "2026-07-28", "tok")
        self.assertEqual(counts, {"2026-07-27": 3, "2026-07-28": 2})

    def test_paginates_correctly(self):
        page1 = {"workflow_runs": TestActionsRunsByDay._run("2026-07-28", 100)}
        page2 = {"workflow_runs": TestActionsRunsByDay._run("2026-07-28", 40)}
        page3 = {"workflow_runs": []}
        with patch.object(snapshot, "gh_get", side_effect=[page1, page2, page3]), \
             patch("time.sleep"):
            counts = snapshot.actions_runs_by_day("o", "r", "2026-07-28", "2026-07-28", "tok")
        self.assertEqual(counts["2026-07-28"], 140)

    def test_returns_empty_on_api_error(self):
        with patch.object(snapshot, "gh_get", return_value=None):
            counts = snapshot.actions_runs_by_day("o", "r", "2026-07-28", "2026-07-28", "tok")
        self.assertEqual(counts, {})


class TestBackfill(unittest.TestCase):
    """The Traffic API keeps 14 days; every day it returns must be (re)written.

    The bug this guards: a day captured before GitHub had consolidated it was
    stored as 0/0 and never revisited, so the zero outlived the real data.
    """

    def _api(self, days: dict):
        """days = {date: (views, clones)}"""
        return (
            {"views": [{"timestamp": f"{d}T00:00:00Z", "count": v, "uniques": 1}
                       for d, (v, _) in days.items()]},
            {"clones": [{"timestamp": f"{d}T00:00:00Z", "count": c, "uniques": 1}
                        for d, (_, c) in days.items()]},
            [{"referrer": "Google", "count": 9, "uniques": 4}],
            [{"path": "/x", "title": "x", "count": 3, "uniques": 2}],
        )

    def _run(self, tmpdir, requested, days, runs=None):
        views, clones, refs, paths = self._api(days)
        with patch.object(snapshot, "gh_get") as mock_get, \
             patch.object(snapshot, "actions_runs_by_day") as mock_runs:
            mock_runs.return_value = runs or {}
            mock_get.side_effect = [views, clones, refs, paths]
            snapshot.snapshot_repo("CSalcedoDataBI", "repo-a", requested,
                                   "fake-token", Path(tmpdir))
        with open(Path(tmpdir) / "repo-a.json", encoding="utf-8") as f:
            return json.load(f)

    def test_writes_every_day_the_api_returns_not_just_the_requested_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(tmp, "2026-07-29", {
                "2026-07-27": (5, 1), "2026-07-28": (7, 2), "2026-07-29": (29, 3),
            })
        by_date = {s["date"]: s for s in data["snapshots"]}
        self.assertEqual(sorted(by_date), ["2026-07-27", "2026-07-28", "2026-07-29"])
        self.assertEqual(by_date["2026-07-27"]["views_count"], 5)
        self.assertEqual(by_date["2026-07-29"]["views_count"], 29)

    def test_a_stored_zero_is_repaired_when_the_data_arrives_late(self):
        """The regression test for #18."""
        with tempfile.TemporaryDirectory() as tmp:
            # First run: GitHub has not consolidated the day yet.
            first = self._run(tmp, "2026-07-29", {"2026-07-29": (0, 0)})
            self.assertEqual(first["snapshots"][0]["views_count"], 0)

            # Next run, a day later: the API now reports the real numbers.
            second = self._run(tmp, "2026-07-30", {
                "2026-07-29": (29, 5), "2026-07-30": (4, 1),
            })

        by_date = {s["date"]: s for s in second["snapshots"]}
        self.assertEqual(by_date["2026-07-29"]["views_count"], 29,
                         "the frozen zero must be overwritten by the real value")
        self.assertEqual(by_date["2026-07-30"]["views_count"], 4)

    def test_referrers_are_attached_only_to_the_newest_day(self):
        """They are a rolling 14-day aggregate, not a per-day measure.

        Copying them onto every day would let a consumer sum the same visits
        fourteen times.
        """
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(tmp, "2026-07-29", {
                "2026-07-28": (7, 2), "2026-07-29": (29, 3),
            })
        by_date = {s["date"]: s for s in data["snapshots"]}
        self.assertEqual(by_date["2026-07-28"]["top_referrers"], [])
        self.assertEqual(len(by_date["2026-07-29"]["top_referrers"]), 1)

    def test_older_referrers_already_stored_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._run(tmp, "2026-07-28", {"2026-07-28": (7, 2)})
            data = self._run(tmp, "2026-07-29", {
                "2026-07-28": (7, 2), "2026-07-29": (29, 3),
            })
        by_date = {s["date"]: s for s in data["snapshots"]}
        self.assertEqual(len(by_date["2026-07-28"]["top_referrers"]), 1,
                         "a past day keeps the aggregate captured when it was current")

    def test_ci_normalization_uses_that_days_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = self._run(tmp, "2026-07-29",
                             {"2026-07-28": (7, 30), "2026-07-29": (29, 12)},
                             runs={"2026-07-28": 25, "2026-07-29": 2})
        by_date = {s["date"]: s for s in data["snapshots"]}
        self.assertEqual(by_date["2026-07-28"]["human_clones_count"], 5)
        self.assertEqual(by_date["2026-07-29"]["human_clones_count"], 10)


class TestMainCLI(unittest.TestCase):
    def test_exits_1_without_token(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GH_TOKEN", None)
            rc = snapshot.main(["--date", "2026-07-28", "--dry-run"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
