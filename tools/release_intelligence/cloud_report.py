#!/usr/bin/env python3
"""Turn a `gcloud beta device-run` console log into an aggregate JSON report.

The report is safe to publish: it contains device ids, Android versions, CI run
ids, session ids, and pass/fail classifications. It never contains logcat text,
stack traces, credentials, or Cloud Storage object paths with tokens.

Usage:
    python3 tools/release_intelligence/cloud_report.py \
        --log device-run.log \
        --devices shiba-34,shiba-36 \
        --metadata tools/release_intelligence/device-catalog.json \
        --run-id 123456789 \
        --run-url https://github.com/OWNER/REPO/actions/runs/123456789 \
        --commit SHA --branch BRANCH \
        --apk app-universal-debug.apk --test-apk app-debug-androidTest.apk \
        --output hmxwebsite/data/cloud-device-tests.json --merge
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
SESSION_RE = re.compile(
    r"Session\s+\[(?P<session>session-[0-9a-zA-Z-]+)\]\s+finished with result\s+\[(?P<result>[A-Z]+)\]"
)
RESULT_DIR_RE = re.compile(r"Result files are stored at\s+\[(?P<url>https://[^\]]+)\]")
JOB_RE = re.compile(
    r"^(?P<job>job-\d+)\s+(?P<execution>\S+)\s+(?P<result>PASSED|FAILED|ERROR|SKIPPED)(?P<detail>.*)$",
    re.MULTILINE,
)
DEVICE_RE = re.compile(r"^(?P<id>[a-z0-9][a-z0-9-]*-\d{2})$")

STATUS_MAP = {
    "PASSED": "passed",
    "FAILED": "failed",
    "ERROR": "error",
    "SKIPPED": "skipped",
}


def classify_failure(result: str, detail: str) -> str | None:
    if result == "PASSED":
        return None
    text = (detail or "").lower()
    if "crash" in text or "fatal exception" in text:
        return "app_crash"
    if result == "ERROR":
        return "infrastructure_or_input_error"
    if "timeout" in text:
        return "timeout"
    return "test_failure"


def parse_log(log: str) -> dict[str, Any]:
    session_match = SESSION_RE.search(log)
    result_dir = RESULT_DIR_RE.search(log)
    jobs = []
    for match in JOB_RE.finditer(log):
        jobs.append(
            {
                "job": match.group("job"),
                "execution": match.group("execution"),
                "result": match.group("result"),
                "status": STATUS_MAP.get(match.group("result"), "unknown"),
                "detail": match.group("detail").strip(),
            }
        )
    return {
        "session_id": session_match.group("session") if session_match else None,
        "session_result": session_match.group("result") if session_match else None,
        "report_url": result_dir.group("url") if result_dir else None,
        "jobs": jobs,
    }


def parse_devices(value: str) -> list[str]:
    devices = []
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        if not DEVICE_RE.match(item):
            raise ValueError(f"invalid device id: {item}")
        devices.append(item)
    return devices


def load_metadata(path: Path | None) -> dict[str, dict[str, str]]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    devices = data.get("devices", data) if isinstance(data, dict) else {}
    result = {}
    if isinstance(devices, dict):
        for device_id, info in devices.items():
            if isinstance(info, dict):
                result[device_id] = {
                    "model": str(info.get("model") or device_id),
                    "android": str(info.get("android") or "unknown"),
                    "type": str(info.get("type") or "unknown"),
                }
    return result


def build_report(
    parsed: dict[str, Any],
    devices: list[str],
    metadata: dict[str, dict[str, str]],
    build: dict[str, str],
    now: datetime | None = None,
) -> dict[str, Any]:
    generated = now or datetime.now(timezone.utc)
    jobs = parsed["jobs"]

    rows = []
    for index, device_id in enumerate(devices):
        job = jobs[index] if index < len(jobs) else None
        info = metadata.get(device_id, {})
        status = job["status"] if job else "unknown"
        rows.append(
            {
                "run_id": build.get("run_id") or "unknown",
                "run_url": build.get("run_url") or "",
                "session_id": parsed["session_id"] or "unknown",
                "device": device_id,
                "device_model": info.get("model", device_id),
                "android_version": info.get("android", "unknown"),
                "device_type": info.get("type", "unknown"),
                "status": status,
                "failure_classification": classify_failure(job["result"], job["detail"]) if job else "missing_result",
                "commit": build.get("commit") or "",
                "branch": build.get("branch") or "",
                "apk": build.get("apk") or "",
                "test_apk": build.get("test_apk") or "",
                "report_url": parsed["report_url"] or "",
                "started_at_utc": build.get("started_at_utc") or "",
                "finished_at_utc": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )

    if not jobs:
        overall = "error"
        summary = "No device-run result table was found in the console log. The run is classified as an error, not a pass."
    elif len(jobs) != len(devices):
        overall = "error"
        summary = (
            f"Result table has {len(jobs)} job row(s) for {len(devices)} requested device(s); "
            "the mismatch is reported as an error rather than guessing."
        )
    elif all(job["status"] == "passed" for job in jobs):
        overall = "passed"
        summary = f"{len(jobs)} of {len(devices)} device run(s) passed."
    else:
        overall = "failed"
        failed = sum(1 for job in jobs if job["status"] != "passed")
        summary = f"{failed} of {len(devices)} device run(s) did not pass."

    return {
        "schema_version": SCHEMA_VERSION,
        "repository": build.get("repository") or "",
        "provider": "Google Cloud Developer Device Platform (Device Run, Preview)",
        "status": overall,
        "generated_at_utc": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary,
        "session": {
            "id": parsed["session_id"],
            "result": parsed["session_result"],
            "report_url": parsed["report_url"],
        },
        "build": {
            "run_id": build.get("run_id") or "",
            "run_url": build.get("run_url") or "",
            "commit": build.get("commit") or "",
            "branch": build.get("branch") or "",
            "apk": build.get("apk") or "",
            "test_apk": build.get("test_apk") or "",
        },
        "runs": rows,
        "privacy": {
            "uploads_user_documents": False,
            "collects_device_identifiers": False,
            "note": "Only CI-built APKs and generated test fixtures are uploaded. No user file, account, advertising id, or device identifier is collected.",
        },
    }


def render_summary(report: dict[str, Any]) -> str:
    """Markdown summary for a GitHub Actions step summary."""
    lines = [
        "### Cloud device tests",
        "",
        f"- Status: **{report.get('status', 'unknown')}**",
        f"- {report.get('summary', '')}",
    ]
    session = report.get("session") or {}
    if session.get("id"):
        lines.append(f"- Session: `{session.get('id')}`")
    for row in report.get("runs", []):
        lines.append(
            "- `{}` (Android {}): {}".format(
                row.get("device", "unknown"),
                row.get("android_version", "unknown"),
                row.get("status", "unknown"),
            )
        )
    lines.extend(
        [
            "",
            "Cloud results are aggregate CI outcomes; raw logs and stack traces stay in the private report artifact.",
        ]
    )
    return "\n".join(lines) + "\n"


def merge_reports(existing: dict[str, Any] | None, report: dict[str, Any], limit: int = 60) -> dict[str, Any]:
    if not isinstance(existing, dict) or not isinstance(existing.get("runs"), list):
        return report
    merged = {**report}
    combined = []
    seen = set()
    for row in list(existing["runs"]) + list(report["runs"]):
        if not isinstance(row, dict):
            continue
        key = (row.get("run_id"), row.get("device"), row.get("session_id"))
        if key in seen:
            continue
        seen.add(key)
        combined.append(row)
    merged["runs"] = combined[-limit:]
    merged["history_note"] = "Most recent runs are kept; older rows are pruned by the reporting workflow."
    return merged


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--devices", required=True)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--repository", default="tanishka1233/HMXPDF")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--commit", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--apk", default="")
    parser.add_argument("--test-apk", default="")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, help="Write a Markdown summary for the Actions step summary")
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        devices = parse_devices(args.devices)
    except ValueError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 2
    if not devices:
        print("FAIL no devices were provided", file=sys.stderr)
        return 2

    try:
        log = args.log.read_text(encoding="utf-8", errors="replace")
        metadata = load_metadata(args.metadata)
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL could not read input: {error}", file=sys.stderr)
        return 1

    report = build_report(
        parse_log(log),
        devices,
        metadata,
        {
            "repository": args.repository,
            "run_id": args.run_id,
            "run_url": args.run_url,
            "commit": args.commit,
            "branch": args.branch,
            "apk": args.apk,
            "test_apk": args.test_apk,
            "started_at_utc": args.started_at,
        },
    )

    existing = None
    if args.merge and args.output.exists():
        try:
            existing = json.loads(args.output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = None
    final = merge_reports(existing, report) if args.merge else report

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")
    if args.summary_md:
        args.summary_md.parent.mkdir(parents=True, exist_ok=True)
        args.summary_md.write_text(render_summary(report), encoding="utf-8")
    print(f"Status: {report['status']} — {report['summary']}")
    print(f"Wrote:  {args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
