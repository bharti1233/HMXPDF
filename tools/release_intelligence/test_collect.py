#!/usr/bin/env python3
"""Unit tests for the HMXPDF release intelligence collector (stdlib only).

Run with:
    python3 -m unittest discover -s tools/release_intelligence -p 'test_*.py'
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect  # noqa: E402


def release(tag: str, published: str, assets: list[dict]) -> dict:
    return {
        "id": 1,
        "tag_name": tag,
        "name": f"HMXPDF {tag}",
        "draft": False,
        "prerelease": False,
        "published_at": published,
        "html_url": f"https://example.test/{tag}",
        "assets": assets,
    }


def asset(name: str, count: int = 0, size: int = 100, digest: str | None = None, ctype: str = "application/octet-stream") -> dict:
    return {
        "name": name,
        "size": size,
        "download_count": count,
        "content_type": ctype,
        "digest": digest,
        "state": "uploaded",
        "browser_download_url": f"https://example.test/download/{name}",
    }


class ClassifyTests(unittest.TestCase):
    def test_apk_abis(self) -> None:
        cases = {
            "app-play-arm64-v8a-release.apk": "arm64-v8a",
            "app-play-armeabi-v7a-release.apk": "armeabi-v7a",
            "app-play-x86_64-release.apk": "x86_64",
            "app-play-x86-release.apk": "x86",
            "app-play-universal-release.apk": "universal",
            "hmxpdf-2.1.1.apk": "unknown",
        }
        for name, abi in cases.items():
            with self.subTest(name=name):
                result = collect.classify_asset(name)
                self.assertEqual(result["kind"], "apk")
                self.assertEqual(result["abi"], abi)

    def test_debug_apk_is_excluded(self) -> None:
        for name in ("app-debug.apk", "app-play-arm64-v8a-debug.apk", "HMXPDF_debug_2.1.1.apk"):
            with self.subTest(name=name):
                self.assertEqual(collect.classify_asset(name)["kind"], "apk_debug")

    def test_non_packages(self) -> None:
        self.assertEqual(collect.classify_asset("HMXPDF-v2.1.1-Android-APKs.zip")["kind"], "apk_bundle_zip")
        self.assertEqual(collect.classify_asset("HMXPDF-v2.1.1-Android-APKs.zip.sha256")["kind"], "checksum")
        self.assertEqual(collect.classify_asset("HMXPDF-v2.1.1.aab")["kind"], "aab")
        self.assertEqual(collect.classify_asset("Source code (zip)")["kind"], "archive")
        self.assertEqual(collect.classify_asset("notes.txt")["kind"], "checksum")
        self.assertEqual(collect.classify_asset("logo.png")["kind"], "other")

    def test_digest_parsing(self) -> None:
        digest = "sha256:" + "a" * 64
        self.assertEqual(collect.parse_digest(digest), "a" * 64)
        self.assertIsNone(collect.parse_digest(None))
        self.assertIsNone(collect.parse_digest(""))
        self.assertIsNone(collect.parse_digest("sha256:nothex"))


class AggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.releases = [
            release(
                "v2.0.0",
                "2026-10-01T00:00:00Z",
                [
                    asset("app-play-arm64-v8a-release.apk", 10, digest="sha256:" + "1" * 64),
                    asset("app-play-universal-release.apk", 5),
                    asset("app-debug.apk", 99),
                    asset("HMXPDF-v2.0.0-Android-APKs.zip", 3),
                    asset("HMXPDF-v2.0.0.aab", 7),
                ],
            ),
            release(
                "v2.1.1",
                "2026-11-18T17:25:39Z",
                [
                    asset("app-play-arm64-v8a-release.apk", 20),
                    asset("app-play-armeabi-v7a-release.apk", 4),
                    asset("HMXPDF-v2.1.1-Android-APKs.zip", 2),
                    asset("HMXPDF-v2.1.1-Android-APKs.zip.sha256", 3),
                ],
            ),
        ]
        self.data = collect.build_intelligence(
            self.releases, "tanishka1233/HMXPDF", datetime(2026, 11, 20, tzinfo=timezone.utc)
        )

    def test_totals_exclude_non_packages_and_debug(self) -> None:
        # 10 + 5 + 3 + 20 + 4 + 2
        self.assertEqual(self.data["totals"]["apk_downloads"], 44)
        self.assertEqual(self.data["totals"]["installable_apk_downloads"], 39)
        self.assertEqual(self.data["totals"]["apk_bundle_downloads"], 5)
        self.assertEqual(self.data["totals"]["releases"], 2)

    def test_abi_distribution(self) -> None:
        abi = self.data["downloads_by_abi"]
        self.assertEqual(abi["arm64-v8a"]["downloads"], 30)
        self.assertEqual(abi["multi"]["downloads"], 5)
        self.assertEqual(abi["universal"]["downloads"], 5)
        self.assertEqual(self.data["most_downloaded_variant"]["abi"], "arm64-v8a")
        self.assertAlmostEqual(
            sum(item["percent"] for item in abi.values()), 100.0, delta=0.2
        )

    def test_latest_and_comparison(self) -> None:
        self.assertEqual(self.data["latest_release"]["tag"], "v2.1.1")
        comparison = {row["tag"]: row for row in self.data["release_comparison"]}
        self.assertIsNone(comparison["v2.0.0"]["delta_from_previous"])
        self.assertEqual(comparison["v2.1.1"]["delta_from_previous"], 26 - 18)

    def test_missing_fields_are_tolerated(self) -> None:
        raw = release("v9.9.9", "2026-11-19T00:00:00Z", [{"name": "app.apk"}])
        data = collect.build_intelligence([raw], "tanishka1233/HMXPDF")
        self.assertEqual(data["totals"]["apk_downloads"], 0)
        row = data["releases"][0]
        self.assertIsNone(row["assets"][0]["digest"])
        self.assertEqual(row["assets"][0]["abi"], "unknown")

    def test_debug_and_aab_are_reported_but_not_counted(self) -> None:
        by_tag = {row["tag"]: row for row in self.data["releases"]}
        excluded = by_tag["v2.0.0"]["excluded_assets"]
        kinds = {item["kind"] for item in excluded}
        self.assertIn("apk_debug", kinds)
        self.assertIn("aab", kinds)
        checksum_row = by_tag["v2.1.1"]
        self.assertIn("checksum", {item["kind"] for item in checksum_row["excluded_assets"]})


class PaginationTests(unittest.TestCase):
    def test_fetch_follows_pages(self) -> None:
        page_one = [release(f"v1.0.{i}", "2026-01-01T00:00:00Z", []) for i in range(100)]
        page_two = [release("v0.9.0", "2025-12-01T00:00:00Z", [])]
        responses = [
            (json.dumps(page_one).encode(), {}),
            (json.dumps(page_two).encode(), {}),
        ]
        with mock.patch.object(collect, "_request", side_effect=responses) as request:
            releases = collect.fetch_releases("tanishka1233/HMXPDF", None)
        self.assertEqual(len(releases), 101)
        self.assertEqual(request.call_count, 2)

    def test_fetch_stops_before_extra_call(self) -> None:
        page = [release("v1.0.0", "2026-01-01T00:00:00Z", [])]
        with mock.patch.object(collect, "_request", return_value=(json.dumps(page).encode(), {})) as request:
            releases = collect.fetch_releases("tanishka1233/HMXPDF", None)
        self.assertEqual(len(releases), 1)
        self.assertEqual(request.call_count, 1)


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = mock.patch.multiple(
            collect, SNAPSHOT_DIR=self.root / "snapshots", OUTPUT_PATH=self.root / "out.json"
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.now = datetime(2026, 11, 20, 5, 17, tzinfo=timezone.utc)

    def _intelligence(self, count: int) -> dict:
        return collect.build_intelligence(
            [release("v2.1.1", "2026-11-18T17:25:39Z", [asset("app-play-arm64-v8a-release.apk", count)])],
            "tanishka1233/HMXPDF",
            self.now,
        )

    def test_deduplicates_unchanged_snapshots(self) -> None:
        wrote, _ = collect.write_snapshot(self._intelligence(5), self.now)
        self.assertTrue(wrote)
        wrote, reason = collect.write_snapshot(self._intelligence(5), self.now)
        self.assertFalse(wrote)
        self.assertEqual(reason, "unchanged")
        self.assertEqual(len(list(collect.SNAPSHOT_DIR.glob("*.json"))), 1)

    def test_writes_again_when_counter_changes(self) -> None:
        collect.write_snapshot(self._intelligence(5), self.now)
        wrote, _ = collect.write_snapshot(self._intelligence(6), self.now)
        self.assertTrue(wrote)
        data = json.loads(next(collect.SNAPSHOT_DIR.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(data["total_apk_downloads"], 6)

    def test_prunes_old_snapshots(self) -> None:
        collect.SNAPSHOT_DIR.mkdir(parents=True)
        (collect.SNAPSHOT_DIR / "2024-01-01.json").write_text("{}", encoding="utf-8")
        (collect.SNAPSHOT_DIR / "2026-11-20.json").write_text("{}", encoding="utf-8")
        removed = collect.prune_snapshots(self.now, retention_days=400)
        self.assertEqual(removed, ["2024-01-01.json"])
        self.assertTrue((collect.SNAPSHOT_DIR / "2026-11-20.json").exists())


class OutputTests(unittest.TestCase):
    def test_output_round_trip_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "release-intelligence.json"
            data = collect.build_intelligence(
                [release("v2.1.1", "2026-11-18T17:25:39Z", [asset("app.apk", 1)])],
                "tanishka1233/HMXPDF",
            )
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(collect.validate_output(path), [])

    def test_validation_rejects_wrong_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "release-intelligence.json"
            data = collect.build_intelligence([], "someone/else")
            path.write_text(json.dumps(data), encoding="utf-8")
            problems = collect.validate_output(path)
            self.assertTrue(any("repository" in problem for problem in problems))

    def test_collect_cli_from_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = root / "fixture.json"
            fixture.write_text(
                json.dumps(
                    [
                        release(
                            "v2.1.1",
                            "2026-11-18T17:25:39Z",
                            [
                                asset("app-play-arm64-v8a-release.apk", 7, digest="sha256:" + "b" * 64),
                                asset("HMXPDF-v2.1.1-Android-APKs.zip", 2),
                            ],
                        )
                    ]
                ),
                encoding="utf-8",
            )
            output = root / "out.json"
            code = collect.main(
                ["--input", str(fixture), "--output", str(output), "--no-snapshot", "--quiet"]
            )
            self.assertEqual(code, 0)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["totals"]["apk_downloads"], 9)
            self.assertEqual(data["releases"][0]["assets"][0]["digest"], "b" * 64)


if __name__ == "__main__":
    unittest.main()
