#!/usr/bin/env python3
"""Aggregate HMXPDF GitHub release download intelligence.

Reads the public GitHub Releases API and produces:

  hmxwebsite/data/release-intelligence.json   machine-readable dashboard feed
  hmxwebsite/data/snapshots/YYYY-MM-DD.json   daily cumulative snapshots

Only aggregate asset counters are used. GitHub does not provide a per-download
event stream, so the snapshot files exist to estimate trends from cumulative
values over time. No user identity is collected anywhere.

Usage:
    GITHUB_TOKEN=... python3 tools/release_intelligence/collect.py
    python3 tools/release_intelligence/collect.py --input fixture.json
    python3 tools/release_intelligence/collect.py --check

Exit codes: 0 success, 1 failure, 2 usage/configuration error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
DEFAULT_REPO = "tanishka1233/HMXPDF"
API_ROOT = "https://api.github.com"
USER_AGENT = "HMXPDF-release-intelligence/1.0 (+https://github.com/tanishka1233/HMXPDF)"
SNAPSHOT_RETENTION_DAYS = 400
MAX_RELEASES = 300

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "hmxwebsite" / "data"
OUTPUT_PATH = DATA_DIR / "release-intelligence.json"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
CLOUD_REPORT_PATH = DATA_DIR / "cloud-device-tests.json"

APK_RE = re.compile(r"\.apk$", re.IGNORECASE)
AAB_RE = re.compile(r"\.aab$", re.IGNORECASE)
ZIP_RE = re.compile(r"\.zip$", re.IGNORECASE)
CHECKSUM_RE = re.compile(r"\.(sha256|sha1|sha512|md5|txt|sig|asc|json)$", re.IGNORECASE)
DEBUG_RE = re.compile(r"(^|[-_.])debug($|[-_.])", re.IGNORECASE)

# Order matters: x86_64 before x86, arm64 before arm.
ABI_PATTERNS: tuple[tuple[str, str], ...] = (
    ("arm64-v8a", "arm64-v8a"),
    ("armeabi-v7a", "armeabi-v7a"),
    ("armeabi", "armeabi-v7a"),
    ("x86_64", "x86_64"),
    ("x86-64", "x86_64"),
    ("x86", "x86"),
    ("universal", "universal"),
)

ASSET_KINDS = {
    "apk": "Installable APK",
    "apk_bundle_zip": "APK ZIP (multi-ABI bundle)",
    "apk_debug": "Debug APK",
    "aab": "Android App Bundle",
    "checksum": "Checksum or text file",
    "archive": "Source or generic archive",
    "other": "Other asset",
}


def classify_asset(name: str, content_type: str = "") -> dict[str, str]:
    """Classify a release asset without trusting its description."""
    lower = (name or "").lower()
    if APK_RE.search(lower):
        # A debug APK is not a release download and must not inflate metrics.
        if DEBUG_RE.search(lower) or "debug" in lower:
            return {"kind": "apk_debug", "abi": "debug"}
        return {"kind": "apk", "abi": detect_abi(lower)}
    if AAB_RE.search(lower):
        return {"kind": "aab", "abi": "none"}
    if ZIP_RE.search(lower):
        if "apk" in lower:
            return {"kind": "apk_bundle_zip", "abi": "multi"}
        return {"kind": "archive", "abi": "none"}
    if "source code" in lower and "zip" in lower:
        return {"kind": "archive", "abi": "none"}
    if CHECKSUM_RE.search(lower) or "checksum" in lower:
        return {"kind": "checksum", "abi": "none"}
    if content_type in ("application/zip", "application/x-zip-compressed") and "apk" in lower:
        return {"kind": "apk_bundle_zip", "abi": "multi"}
    return {"kind": "other", "abi": "none"}


def detect_abi(name: str) -> str:
    for needle, abi in ABI_PATTERNS:
        if needle in name:
            return abi
    return "unknown"


def is_counted_apk(kind: str) -> bool:
    """APK-package downloads: installable APKs and multi-ABI APK ZIPs."""
    return kind in ("apk", "apk_bundle_zip")


def parse_digest(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"sha256:([a-f0-9]{64})", value, re.IGNORECASE)
    return match.group(1).lower() if match else None


def normalize_release(raw: dict[str, Any]) -> dict[str, Any]:
    assets = []
    for asset in raw.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name") or ""
        content_type = asset.get("content_type") or ""
        classification = classify_asset(name, content_type)
        assets.append(
            {
                "name": name,
                "kind": classification["kind"],
                "kind_label": ASSET_KINDS[classification["kind"]],
                "abi": classification["abi"],
                "size": int(asset.get("size") or 0),
                "download_count": int(asset.get("download_count") or 0),
                "content_type": content_type,
                "digest": parse_digest(asset.get("digest")),
                "browser_download_url": asset.get("browser_download_url") or "",
                "state": asset.get("state") or "",
            }
        )
    return {
        "id": raw.get("id"),
        "tag": raw.get("tag_name") or "",
        "title": raw.get("name") or raw.get("tag_name") or "",
        "draft": bool(raw.get("draft")),
        "prerelease": bool(raw.get("prerelease")),
        "published_at": raw.get("published_at") or raw.get("created_at") or "",
        "url": raw.get("html_url") or "",
        "assets": assets,
    }


def summarize_release(release: dict[str, Any]) -> dict[str, Any]:
    apk_assets = [a for a in release["assets"] if is_counted_apk(a["kind"])]
    installable = [a for a in apk_assets if a["kind"] == "apk"]
    by_abi: dict[str, int] = {}
    for asset in apk_assets:
        by_abi[asset["abi"]] = by_abi.get(asset["abi"], 0) + asset["download_count"]
    total = sum(a["download_count"] for a in apk_assets)
    top = None
    if apk_assets:
        top_asset = max(apk_assets, key=lambda a: (a["download_count"], a["name"]))
        top = {
            "asset_name": top_asset["name"],
            "abi": top_asset["abi"],
            "download_count": top_asset["download_count"],
        }
    return {
        **{k: v for k, v in release.items() if k != "assets"},
        "assets": release["assets"],
        "apk_downloads": total,
        "installable_apk_downloads": sum(a["download_count"] for a in installable),
        "apk_asset_count": len(apk_assets),
        "counted_assets": [
            {"name": a["name"], "kind": a["kind"], "abi": a["abi"], "download_count": a["download_count"]}
            for a in apk_assets
        ],
        "downloads_by_abi": by_abi,
        "top_asset": top,
        "excluded_assets": [
            {
                "name": a["name"],
                "kind": a["kind"],
                "download_count": a["download_count"],
                "reason": "not an APK package download"
                if a["kind"] not in ("apk", "apk_bundle_zip")
                else "",
            }
            for a in release["assets"]
            if a["kind"] not in ("apk", "apk_bundle_zip")
        ],
    }


def build_intelligence(
    releases: list[dict[str, Any]],
    repository: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(timezone.utc)
    summarized = [summarize_release(normalize_release(raw)) for raw in releases]
    summarized.sort(key=lambda r: (r["published_at"] or "", r["tag"]))

    by_abi: dict[str, int] = {}
    total_apk = 0
    total_installable = 0
    for release in summarized:
        total_apk += release["apk_downloads"]
        total_installable += release["installable_apk_downloads"]
        for abi, count in release["downloads_by_abi"].items():
            by_abi[abi] = by_abi.get(abi, 0) + count

    for release in summarized:
        release["share_percent"] = (
            round(release["apk_downloads"] * 100.0 / total_apk, 1) if total_apk else 0.0
        )

    by_abi_distribution = {
        abi: {
            "downloads": count,
            "percent": round(count * 100.0 / total_apk, 1) if total_apk else 0.0,
        }
        for abi, count in sorted(by_abi.items(), key=lambda item: (-item[1], item[0]))
    }

    most_downloaded = None
    if by_abi:
        abi, count = max(by_abi.items(), key=lambda item: (item[1], item[0]))
        most_downloaded = {
            "abi": abi,
            "label": ABI_LABELS.get(abi, abi),
            "downloads": count,
            "percent": round(count * 100.0 / total_apk, 1) if total_apk else 0.0,
        }

    comparison = []
    for index, release in enumerate(summarized):
        previous = summarized[index - 1] if index else None
        delta = release["apk_downloads"] - previous["apk_downloads"] if previous else None
        comparison.append(
            {
                "tag": release["tag"],
                "published_at": release["published_at"],
                "apk_downloads": release["apk_downloads"],
                "delta_from_previous": delta,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "generated_at_utc": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "GitHub REST API /repos/{repo}/releases (asset download_count)",
        "source_url": f"https://api.github.com/repos/{repository}/releases",
        "disclaimers": [
            "download_count is the number of asset download requests GitHub has recorded, not unique people and not successful installations.",
            "APK ZIP bundles are multi-ABI packages; they are counted as APK-package downloads but not assigned to a single architecture.",
            "Debug APKs, AABs, source archives, checksum files and other assets are excluded from APK download totals.",
            "Historical values are reconstructed from periodic cumulative snapshots, not from per-download events.",
        ],
        "totals": {
            "releases": len(summarized),
            "releases_with_apk": sum(1 for r in summarized if r["apk_asset_count"]),
            "apk_downloads": total_apk,
            "installable_apk_downloads": total_installable,
            "apk_bundle_downloads": total_apk - total_installable,
            "assets": sum(len(r["assets"]) for r in summarized),
        },
        "latest_release": _latest(summarized),
        "releases": list(reversed(summarized)),
        "downloads_by_abi": by_abi_distribution,
        "most_downloaded_variant": most_downloaded,
        "release_comparison": comparison,
    }


def _latest(releases: list[dict[str, Any]]) -> dict[str, Any] | None:
    published = [r for r in releases if not r["draft"]]
    if not published:
        return None
    latest = published[-1]
    return {
        "tag": latest["tag"],
        "title": latest["title"],
        "published_at": latest["published_at"],
        "url": latest["url"],
        "apk_downloads": latest["apk_downloads"],
    }


ABI_LABELS = {
    "arm64-v8a": "ARM64 (arm64-v8a)",
    "armeabi-v7a": "ARMv7 (armeabi-v7a)",
    "x86": "x86",
    "x86_64": "x86_64",
    "universal": "Universal",
    "multi": "APK ZIP (multi-ABI)",
    "unknown": "Unknown ABI",
    "debug": "Debug",
    "none": "Not an APK",
}


# --------------------------------------------------------------------------
# GitHub API access
# --------------------------------------------------------------------------


class GitHubError(RuntimeError):
    pass


def _request(url: str, token: str | None, timeout: int = 30) -> tuple[bytes, dict[str, str]]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            last_error = error
            remaining = error.headers.get("X-RateLimit-Remaining")
            retry_after = error.headers.get("Retry-After")
            if error.code in (403, 429) and (retry_after or remaining == "0"):
                wait = int(retry_after) if retry_after and retry_after.isdigit() else 60
                if attempt < 2:
                    time.sleep(min(wait, 90))
                    continue
                raise GitHubError(
                    "GitHub API rate limit reached. Configure GITHUB_TOKEN or retry later."
                ) from error
            if 500 <= error.code < 600 and attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise GitHubError(f"GitHub API returned HTTP {error.code} for {url}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
                continue
            raise GitHubError(f"Network error while contacting GitHub: {error}") from error
    raise GitHubError(f"GitHub API request failed: {last_error}")


def fetch_releases(repository: str, token: str | None) -> list[dict[str, Any]]:
    releases: list[dict[str, Any]] = []
    page = 1
    while page <= 5:
        url = f"{API_ROOT}/repos/{repository}/releases?per_page=100&page={page}"
        body, _headers = _request(url, token)
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, list):
            raise GitHubError("Unexpected GitHub response: expected a list of releases")
        releases.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100 or len(releases) >= MAX_RELEASES:
            break
        page += 1
    return releases[:MAX_RELEASES]


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def snapshot_assets(intelligence: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for release in intelligence["releases"]:
        for asset in release["assets"]:
            rows.append(
                {
                    "release_tag": release["tag"],
                    "asset_name": asset["name"],
                    "kind": asset["kind"],
                    "abi": asset["abi"],
                    "download_count": asset["download_count"],
                    "size": asset["size"],
                    "digest": asset["digest"],
                }
            )
    rows.sort(key=lambda row: (row["release_tag"], row["asset_name"]))
    return rows


def load_latest_snapshot(now: datetime) -> dict[str, Any] | None:
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.json"))
    for path in reversed(files):
        if path.name.startswith("latest"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def write_snapshot(intelligence: dict[str, Any], now: datetime, force: bool = False) -> tuple[bool, str]:
    """Write today's snapshot unless the cumulative values are unchanged."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    rows = snapshot_assets(intelligence)
    latest = load_latest_snapshot(now)
    signature = [
        (row["release_tag"], row["asset_name"], row["download_count"], row["size"], row["digest"])
        for row in rows
    ]
    if not force and latest is not None:
        previous = [
            (
                row.get("release_tag"),
                row.get("asset_name"),
                row.get("download_count"),
                row.get("size"),
                row.get("digest"),
            )
            for row in latest.get("assets", [])
            if isinstance(row, dict)
        ]
        if previous == signature:
            return False, "unchanged"

    captured = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "captured_at_utc": captured,
        "repository": intelligence["repository"],
        "total_apk_downloads": intelligence["totals"]["apk_downloads"],
        "assets": rows,
    }
    day = now.strftime("%Y-%m-%d")
    path = SNAPSHOT_DIR / f"{day}.json"
    previous_for_day: dict[str, Any] | None = None
    if path.exists():
        try:
            previous_for_day = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous_for_day = None
    if previous_for_day is not None:
        # Keep one snapshot per day; replace it only with fresher counters.
        path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        return True, f"replaced {path.name}"
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return True, f"wrote {path.name}"


def prune_snapshots(now: datetime, retention_days: int = SNAPSHOT_RETENTION_DAYS) -> list[str]:
    if not SNAPSHOT_DIR.exists():
        return []
    cutoff = (now - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    removed = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", path.name):
            continue
        if path.stem < cutoff:
            path.unlink()
            removed.append(path.name)
    return removed


def collect_snapshot_history() -> list[dict[str, Any]]:
    if not SNAPSHOT_DIR.exists():
        return []
    history = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json")):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        history.append(
            {
                "date": path.stem,
                "captured_at_utc": data.get("captured_at_utc"),
                "total_apk_downloads": data.get("total_apk_downloads"),
            }
        )
    return history


def load_cloud_tests() -> dict[str, Any]:
    if CLOUD_REPORT_PATH.exists():
        try:
            data = json.loads(CLOUD_REPORT_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "status": "not_configured",
        "summary": "No cloud device test run has been recorded.",
        "runs": [],
    }


def build_output(releases: list[dict[str, Any]], repository: str, now: datetime) -> dict[str, Any]:
    intelligence = build_intelligence(releases, repository, generated_at=now)
    intelligence["snapshots"] = collect_snapshot_history()
    intelligence["cloud_tests"] = load_cloud_tests()
    intelligence["unavailable_metrics"] = [
        {
            "metric": "Website page views",
            "reason": "Vercel Web Analytics is not enabled for this project.",
        },
        {
            "metric": "Website release-link clicks",
            "reason": "No click analytics are collected; clicks are not downloads in any case.",
        },
        {
            "metric": "Unique downloaders",
            "reason": "GitHub exposes only aggregate asset request counters.",
        },
        {
            "metric": "Successful installations",
            "reason": "No installation telemetry exists and none will be added.",
        },
    ]
    intelligence["abi_labels"] = ABI_LABELS
    return intelligence


def write_output(intelligence: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(intelligence, indent=2) + "\n", encoding="utf-8")


def validate_output(path: Path) -> list[str]:
    problems = []
    if not path.exists():
        return [f"{path} does not exist"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{path} is not valid JSON: {error}"]
    for key in (
        "schema_version",
        "repository",
        "generated_at_utc",
        "totals",
        "releases",
        "downloads_by_abi",
        "disclaimers",
    ):
        if key not in data:
            problems.append(f"missing key: {key}")
    totals = data.get("totals", {})
    if not isinstance(totals.get("apk_downloads"), int):
        problems.append("totals.apk_downloads must be an integer")
    if data.get("repository") != DEFAULT_REPO and "repository" in data:
        problems.append(f"unexpected repository: {data.get('repository')}")
    for release in data.get("releases", []):
        if not isinstance(release.get("apk_downloads"), int):
            problems.append(f"release {release.get('tag')} has no integer apk_downloads")
    return problems


def main(argv: Iterable[str] | None = None) -> int:
    global OUTPUT_PATH
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.environ.get("HMXPDF_REPO", DEFAULT_REPO))
    parser.add_argument("--input", type=Path, help="Read releases from a local JSON fixture instead of the network")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-snapshot", action="store_true", help="Do not write a snapshot file")
    parser.add_argument("--force-snapshot", action="store_true", help="Write a snapshot even if counters are unchanged")
    parser.add_argument("--check", action="store_true", help="Validate the existing output file and exit")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    global OUTPUT_PATH
    OUTPUT_PATH = args.output or OUTPUT_PATH

    if args.check:
        problems = validate_output(OUTPUT_PATH)
        if problems:
            for problem in problems:
                print(f"FAIL {problem}", file=sys.stderr)
            return 1
        print(f"OK {OUTPUT_PATH}")
        return 0

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        if args.input:
            payload = json.loads(args.input.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and "releases" in payload:
                payload = payload["releases"]
            if not isinstance(payload, list):
                raise GitHubError("--input must contain a JSON list of releases")
            releases = [item for item in payload if isinstance(item, dict)]
        else:
            releases = fetch_releases(args.repo, token)
    except GitHubError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL could not read --input: {error}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    intelligence = build_output(releases, args.repo, now)

    wrote = False
    snapshot_message = "skipped"
    if not args.no_snapshot:
        wrote, snapshot_message = write_snapshot(intelligence, now, force=args.force_snapshot)
        intelligence["snapshots"] = collect_snapshot_history()
        removed = prune_snapshots(now)
        if removed and not args.quiet:
            print(f"Pruned {len(removed)} old snapshot(s)")

    intelligence["snapshot_written"] = wrote
    write_output(intelligence)

    if not args.quiet:
        print(f"Repository: {intelligence['repository']}")
        print(f"Releases:   {intelligence['totals']['releases']}")
        print(f"APK downloads (aggregate): {intelligence['totals']['apk_downloads']}")
        print(f"Snapshot:   {snapshot_message}")
        print(f"Wrote:      {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
