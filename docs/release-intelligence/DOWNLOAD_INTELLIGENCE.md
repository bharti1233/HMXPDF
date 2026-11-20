# Download intelligence

## What it is

A read-only collector that turns GitHub release asset counters into a static,
machine-readable dataset for the website dashboard.

| Item | Value |
| --- | --- |
| Source | `https://api.github.com/repos/tanishka1233/HMXPDF/releases` |
| Collector | `tools/release_intelligence/collect.py` (Python 3 stdlib only) |
| Tests | `tools/release_intelligence/test_collect.py` (17 unit tests) |
| Dataset | `hmxwebsite/data/release-intelligence.json` |
| Snapshots | `hmxwebsite/data/snapshots/YYYY-MM-DD.json` |
| Workflow | `.github/workflows/release-intelligence.yml` |
| Dashboard | `hmxwebsite/release-intelligence.html` → `/release-intelligence` |

No server, database, cookie, pixel, or app-side beacon is involved. The browser
reads a JSON file that is committed to this repository.

## What is counted

An asset is counted when its name ends in `.apk`, or when it is an APK ZIP
bundle (`*.zip` whose name contains `apk`).

| Asset example | Kind | Counted as APK download |
| --- | --- | --- |
| `app-play-arm64-v8a-release.apk` | `apk` (arm64-v8a) | yes |
| `app-play-armeabi-v7a-release.apk` | `apk` (armeabi-v7a) | yes |
| `app-play-x86-release.apk` | `apk` (x86) | yes |
| `app-play-x86_64-release.apk` | `apk` (x86_64) | yes |
| `app-play-universal-release.apk` | `apk` (universal) | yes |
| `HMXPDF-v2.1.1-Android-APKs.zip` | `apk_bundle_zip` (multi) | yes, shown separately |
| `app-debug.apk` / `*-debug.apk` | `apk_debug` | no |
| `HMXPDF-v2.1.1.aab` | `aab` | no |
| `*.sha256`, `*.txt`, checksum files | `checksum` | no |
| source archives, images, other files | `archive` / `other` | no |

ABI detection checks `arm64-v8a` before `armeabi-v7a`/`armeabi`, and `x86_64`
before `x86`. Unknown APK names get `abi: "unknown"` rather than a guess.

## Metrics produced

- Total APK-package downloads across all releases.
- Installable APK downloads vs. APK ZIP downloads.
- Downloads per release and share of the total.
- Downloads by architecture with percentages.
- Most downloaded variant.
- Release-to-release delta (computed from cumulative values, so it is a
  snapshot delta, not an event count).
- Latest published release.
- Excluded assets with a reason, so a debug APK or AAB is visible but never
  counted.

## Semantics (important)

`download_count` is the number of asset download requests GitHub has recorded.
It is **not**:

- unique people,
- active users,
- installed devices,
- successful installations.

The dataset and dashboard repeat this in `disclaimers` and on the page. The
dashboard also renders missing metrics as “unavailable”, not as zero.

## Snapshots

GitHub has no historical per-download event stream, so the collector stores one
cumulative snapshot per UTC day:

```json
{
  "schema_version": 1,
  "captured_at_utc": "2026-11-20T01:26:05Z",
  "repository": "tanishka1233/HMXPDF",
  "total_apk_downloads": 2,
  "assets": [
    {
      "release_tag": "v2.1.1",
      "asset_name": "HMXPDF-v2.1.1-Android-APKs.zip",
      "kind": "apk_bundle_zip",
      "abi": "multi",
      "download_count": 2,
      "size": 132886048,
      "digest": "18ed388d55426626fc7f02f90f883d8d9426a61fb2742c43fa02925016c34e5e"
    }
  ]
}
```

Rules:

- A new snapshot is written only when at least one counter, size, or digest
  changed. `--force-snapshot` writes a heartbeat anyway.
- Re-running on the same day replaces that day’s file with fresher values.
- Snapshots older than 400 days are pruned automatically.
- Digest is normalised to lowercase hex, and `null` when GitHub did not provide
  one.

## Running it

```bash
# Normal refresh using a token (raises the rate limit; value is never printed)
GITHUB_TOKEN=... python3 tools/release_intelligence/collect.py

# Validate the committed dataset without network access
python3 tools/release_intelligence/collect.py --check

# Offline fixture mode (used by tests and for reproducible debugging)
python3 tools/release_intelligence/collect.py --input releases.json

# Unit tests
python3 -m unittest discover -s tools/release_intelligence -p 'test_*.py'
```

The workflow runs the tests first, then the collector, then `--check`, then
commits only `hmxwebsite/data/**` with a `[skip ci]` message so the Android
build is not triggered by a data-only commit.

## Triggers and scheduling

| Trigger | Purpose |
| --- | --- |
| `schedule` (`17 5 * * *` UTC) | daily snapshot |
| `workflow_dispatch` | manual refresh; optional forced heartbeat |
| `release` (`published`, `edited`, `released`, `unpublished`, `deleted`) | refresh immediately after a release change |

## Rate limits, errors, and duplicates

- Public API without a token allows 60 requests/hour; the workflow uses the
  built-in `GITHUB_TOKEN` for a much higher limit. No personal token is stored.
- `403`/`429` with `Retry-After` or an exhausted quota is retried up to three
  times, then the run fails with a clear message. It never writes a partial or
  invented dataset.
- Network errors and `5xx` responses use bounded exponential backoff.
- Pagination follows `per_page=100` pages up to 300 releases.
- Missing `download_count`, `size`, `digest`, `content_type`, or `state` values
  are normalised, not treated as failures.
- Duplicate workflow executions are harmless: snapshots are deduplicated and the
  workflow uses a single concurrency group.
- A deleted asset disappears from the next dataset; the previous daily snapshot
  remains as history.

## Files and ownership

| Path | Purpose | Safe to delete? |
| --- | --- | --- |
| `tools/release_intelligence/collect.py` | collector | yes, with its workflow |
| `tools/release_intelligence/test_collect.py` | unit tests | yes |
| `hmxwebsite/data/release-intelligence.json` | dashboard feed | regenerated |
| `hmxwebsite/data/snapshots/*.json` | history | pruned automatically |
| `.github/workflows/release-intelligence.yml` | automation | disable in Actions tab |

Rollback: revert the commit that introduced these files, or disable the
workflow. No production release, app binary, signing key, or website domain is
affected.
