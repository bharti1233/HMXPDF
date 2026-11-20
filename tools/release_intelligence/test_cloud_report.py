#!/usr/bin/env python3
"""Unit tests for the cloud device test report parser."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cloud_report  # noqa: E402

PASSED_LOG = """\
Uploading test APK...
Session [session-3cd0564a] finished with result [PASSED].
Result files are stored at [https://console.cloud.google.com/storage/browser/demo-bucket/automation/sessions/session-3cd0564a/].
JOB NAME  EXECUTION NAME  EXECUTION RESULT
job-000   execution-000   PASSED
job-001   execution-000   PASSED
"""

FAILED_LOG = """\
Session [session-94b57778] finished with result [FAILED].
JOB NAME  EXECUTION NAME  EXECUTION RESULT
job-000   execution-000   FAILED: 2 test cases failed, 5 passed
job-001   execution-000   PASSED
"""

ERROR_LOG = """\
Session [session-aaaa1111] finished with result [ERROR].
JOB NAME  EXECUTION NAME  EXECUTION RESULT
job-000   execution-000   ERROR  INSTRUMENTATION_TARGET_MISMATCH
"""


class ParseTests(unittest.TestCase):
    def test_parses_passed_session(self) -> None:
        parsed = cloud_report.parse_log(PASSED_LOG)
        self.assertEqual(parsed["session_id"], "session-3cd0564a")
        self.assertEqual(parsed["session_result"], "PASSED")
        self.assertIn("session-3cd0564a", parsed["report_url"])
        self.assertEqual(len(parsed["jobs"]), 2)
        self.assertEqual({job["status"] for job in parsed["jobs"]}, {"passed"})

    def test_detects_failure_detail(self) -> None:
        parsed = cloud_report.parse_log(FAILED_LOG)
        self.assertEqual(parsed["jobs"][0]["status"], "failed")
        self.assertIn("2 test cases failed", parsed["jobs"][0]["detail"])

    def test_parse_devices_validates_ids(self) -> None:
        self.assertEqual(cloud_report.parse_devices("shiba-34, mediumphone-arm-26"), ["shiba-34", "mediumphone-arm-26"])
        with self.assertRaises(ValueError):
            cloud_report.parse_devices("Pixel 8")

    def test_failure_classification(self) -> None:
        self.assertIsNone(cloud_report.classify_failure("PASSED", ""))
        self.assertEqual(cloud_report.classify_failure("FAILED", "FATAL EXCEPTION in app"), "app_crash")
        self.assertEqual(cloud_report.classify_failure("FAILED", "assertion"), "test_failure")
        self.assertEqual(cloud_report.classify_failure("ERROR", "bad input"), "infrastructure_or_input_error")


class ReportTests(unittest.TestCase):
    def _build(self, log: str, devices: str = "shiba-34,shiba-36") -> dict:
        metadata = {
            "shiba-34": {"model": "Pixel 8", "android": "34", "type": "physical"},
            "shiba-36": {"model": "Pixel 8", "android": "36", "type": "physical"},
        }
        return cloud_report.build_report(
            cloud_report.parse_log(log),
            cloud_report.parse_devices(devices),
            metadata,
            {
                "repository": "tanishka1233/HMXPDF",
                "run_id": "123",
                "run_url": "https://github.com/tanishka1233/HMXPDF/actions/runs/123",
                "commit": "a" * 40,
                "branch": "release/hmxpdf-2.1.1-build",
                "apk": "app-universal-debug.apk",
                "test_apk": "app-debug-androidTest.apk",
            },
            datetime(2026, 11, 20, tzinfo=timezone.utc),
        )

    def test_passed_report(self) -> None:
        report = self._build(PASSED_LOG)
        self.assertEqual(report["status"], "passed")
        self.assertEqual([row["device"] for row in report["runs"]], ["shiba-34", "shiba-36"])
        self.assertEqual(report["runs"][0]["android_version"], "34")
        self.assertEqual(report["runs"][0]["failure_classification"], None)

    def test_failed_report_keeps_all_rows(self) -> None:
        report = self._build(FAILED_LOG)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["runs"][0]["status"], "failed")
        self.assertEqual(report["runs"][1]["status"], "passed")

    def test_missing_result_table_is_error_not_pass(self) -> None:
        report = self._build("Uploading...\nnetwork error\n")
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["runs"][0]["status"], "unknown")
        self.assertIn("No device-run result table", report["summary"])

    def test_device_count_mismatch_is_error(self) -> None:
        report = self._build(PASSED_LOG, devices="shiba-34,shiba-36,mediumphone-arm-26")
        self.assertEqual(report["status"], "error")
        self.assertIn("3 requested device", report["summary"])

    def test_merge_deduplicates(self) -> None:
        first = self._build(PASSED_LOG)
        second = self._build(PASSED_LOG)
        merged = cloud_report.merge_reports(first, second)
        self.assertEqual(len(merged["runs"]), 2)


class CliTests(unittest.TestCase):
    def test_cli_writes_report_and_fails_on_failed_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / "run.log"
            log.write_text(FAILED_LOG, encoding="utf-8")
            out = root / "cloud.json"
            code = cloud_report.main(
                [
                    "--log",
                    str(log),
                    "--devices",
                    "shiba-34,shiba-36",
                    "--output",
                    str(out),
                ]
            )
            self.assertEqual(code, 1)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "failed")
            self.assertEqual(len(data["runs"]), 2)

    def test_cli_rejects_bad_device(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / "run.log"
            log.write_text(PASSED_LOG, encoding="utf-8")
            code = cloud_report.main(
                ["--log", str(log), "--devices", "not a device", "--output", str(root / "x.json")]
            )
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
