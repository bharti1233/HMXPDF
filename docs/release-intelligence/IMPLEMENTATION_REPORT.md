# Implementation report — Release Intelligence + Cloud Device Testing

Date: 2026-11-20

Repository: `tanishka1233/HMXPDF`
Baseline commit: `15ee95e67275f4a032b887a35f2746154fbe1579`
Primary branch: `release/hmxpdf-2.1.1-build`

This report separates four things that are easy to blur together:

1. **Implemented and verified locally** — code exists and its automated checks pass.
2. **Implemented but not executed** — code exists, but needs external account
   configuration and has never produced a real result.
3. **Pending owner action** — cannot be done from a repository change.
4. **Not implemented** — deliberately out of scope, with the reason.

A skipped cloud job is not a pass. A missing metric is not zero.

## 1. Phase status

| Phase | Scope | Status | Evidence |
| --- | --- | --- | --- |
| 0 | Architecture, privacy, and provider audit | Done | `PHASE0_ARCHITECTURE_AUDIT.md`; facts read from the repository and official docs |
| 1 | Download intelligence + snapshots | Done, verified locally | `collect.py`, 17 unit tests, real dataset generated |
| 2 | Website analytics | **Not enabled** — documentation only | No script added; exact steps in `OPERATIONS_GUIDE.md` §4 |
| 3 | Cloud device testing workflow | Implemented, **never executed** | `cloud-device-tests.yml`, `cloud_report.py`, 11 unit tests |
| 4 | Instrumentation coverage | Implemented, CI build verified | two `androidTest` files; `Cloud device tests` build job passed on `4662a15` |
| 5 | Dashboard | Done, verified locally | page, JS, CSS, dataset checks, sitemap, footer links |
| 6 | Release integration / gate | **Not enabled** — documented plan only | production workflow and release guard untouched |

## 2. Implemented and verified locally

### 2.1 Download intelligence

| File | Purpose |
| --- | --- |
| `tools/release_intelligence/collect.py` | stdlib-only collector |
| `tools/release_intelligence/test_collect.py` | 17 unit tests |
| `hmxwebsite/data/release-intelligence.json` | committed dashboard dataset |
| `hmxwebsite/data/snapshots/2026-11-20.json` | first cumulative snapshot |
| `.github/workflows/release-intelligence.yml` | daily + release-event automation |

Verified:

- 17 tests pass (`python3 -m unittest discover -s tools/release_intelligence -p 'test_*.py'`).
- Real API run against `tanishka1233/HMXPDF` succeeded with a token:
  1 release (`v2.1.1`), 2 counted APK-package downloads (the APK ZIP), 2 excluded
  assets (the ZIP and its `.sha256` checksum), 0 installable single-APK
  downloads.
- `--check` validates the committed file.
- Classification covers ABI APKs, universal APKs, APK ZIP bundles, debug APKs,
  AABs, checksums, and source archives. Debug APKs and AABs are reported as
  excluded, never counted.
- Pagination, retry/rate-limit handling, snapshot deduplication, same-day
  replacement, and 400-day pruning are unit-tested.

### 2.2 Dashboard

| File | Purpose |
| --- | --- |
| `hmxwebsite/release-intelligence.html` | static dashboard page |
| `hmxwebsite/assets/js/release-intelligence.js` | dataset renderer |
| `hmxwebsite/assets/css/intelligence.css` | page styles |
| `hmxwebsite/scripts/check_site.py` | extended site validation |
| `hmxwebsite/sitemap.xml` | dashboard URL |
| seven page footers | navigation link |

Verified:

- `check_site.py`: **144 checks, 0 failures, 0 warnings**.
- `preflight.sh`: **all checks passed**.
- `node --check` passes for both site JavaScript files.
- The page is CSP-compatible: no inline script or style, no `innerHTML`, only
  `textContent` and property assignment. The progress bars use `<progress>`
  because inline `style` is forbidden by `style-src 'self'`.
- All outbound URLs pass an https-only check before becoming links.
- Missing metrics render as “unavailable”, not zero.

### 2.3 Cloud reporting tool

| File | Purpose |
| --- | --- |
| `tools/release_intelligence/cloud_report.py` | console log → aggregate JSON |
| `tools/release_intelligence/test_cloud_report.py` | 11 unit tests |
| `tools/release_intelligence/device-catalog.json` | verified device ids |
| `hmxwebsite/data/cloud-device-tests.json` | placeholder, status `not_configured` |

Verified:

- 11 tests pass; combined Python total is **28**.
- A missing result table becomes `error`, not `passed`.
- A device/job count mismatch becomes `error`.
- Failed runs are classified as `app_crash`, `test_failure`, `timeout`,
  `infrastructure_or_input_error`, or `missing_result`.
- The CLI exits 1 for failed/error results after writing the report, so the
  workflow cannot silently pass.

### 2.4 Repository identity

The active repository is `tanishka1233/HMXPDF`. `api.github.com/repos/bharti1233/HMXPDF`
returns **HTTP 301** to repository id `1439357367`, which is
`tanishka1233/HMXPDF`, so the old name only worked through a redirect. README,
SECURITY, CONTRIBUTING, CHANGELOG, the issue-template config, the website pages,
`release.js`, and `check_site.py` now name `tanishka1233/HMXPDF` directly.

## 3. Implemented but not executed

### 3.1 Cloud device testing workflow

`.github/workflows/cloud-device-tests.yml` exists and is syntactically valid, but
**no cloud session has ever run**. It is skipped with an explicit notice while
the three Google Cloud secrets are absent.

What it does when configured:

1. Builds `assemblePlayDebug` and `assemblePlayDebugAndroidTest`.
2. Validates package ids and version with `aapt dump badging`.
3. Uploads only debug APKs as a 7-day artifact.
4. Checks the three secret names.
5. Reads the device list with `gcloud beta device-run devices list`.
6. Submits instrumentation with a three-device default matrix.
7. Writes an aggregate report; fails unless every row passed.
8. Publishes only the aggregate report on the primary branch.

Why it has not run:

- no Google Cloud project,
- no billing,
- no DDP Preview access,
- no Workload Identity Federation,
- no service account,
- no bucket,
- no `gcloud` in the local environment.

Inventing a device id, flag, or result was explicitly avoided.

### 3.2 Instrumentation tests

`app/src/androidTest/java/com/hmx/pdf/` contains:

- `AppLaunchSmokeTest.kt` — launches `MainActivity`, checks window attachment and
  `RESUMED`, then background/resume/recreate.
- `PdfRenderInstrumentationTest.kt` — generates a PDF with PdfBox, opens it with
  the platform `PdfRenderer`, and asserts a dark pixel from the drawn square.

Compilation is now verified in CI. The `Cloud device tests` build job ran
`assemblePlayDebug assemblePlayDebugAndroidTest` successfully on commit `4662a15`
(run `44660011655`) after two R8 fixes: supplying `testProguardFiles` for the
instrumentation APK so compile-time-only Error Prone and `javax.lang.model`
annotations are not treated as missing. The existing `android.yml` build job
still does not build `androidTest`; the cloud workflow’s build job is what
verifies it. No cloud session has run.

## 4. Pending owner action

| Action | Why it cannot be done here |
| --- | --- |
| Google Cloud project + billing | account-level |
| DDP Preview access | account-level request |
| Workload Identity Pool + OIDC provider | account-level IAM |
| Service account and role bindings | account-level IAM |
| Storage bucket + lifecycle rule | account-level |
| Three repository secrets + `DDP_BUCKET` | secret values |
| `cloud-testing` environment with reviewers | repository settings |
| Vercel Web Analytics (optional) | dashboard + plan approval |
| Verify the live dashboard after deploy | Vercel deployment |
| Approve automatic cloud runs (`DDP_AUTORUN`) | cost owner |

Recommended hardening, not required by this change:

- Move the four signing secrets from repository scope into the `release`
  environment and add required reviewers.
- Enable branch protection on the primary branch and `main`.

Both are outside this task’s safe-change boundary because they alter the
production release path.

## 5. Explicitly not implemented

| Item | Reason |
| --- | --- |
| App analytics / crash reporting | prohibited by the privacy constraints |
| Per-user or per-device download tracking | prohibited; GitHub only exposes aggregates |
| Document upload to any HMXPDF server | no such server exists or is wanted |
| Website analytics script | requires owner approval and a CSP change |
| Download APK button activation | must stay disabled |
| Vercel setting/domain changes | requires approval |
| Cloud test release gate | unconfigured cloud testing must not look like protection |
| API 23–25 device coverage | DDP catalog starts at Android 26 |
| DOCX/XLSX UI journeys in `androidTest` | no fixtures/navigation; JVM suites already cover serializers |
| OCR instrumentation | depends on Play services and bundled models |
| New version, tag, or GitHub Release | `v2.1.1` must not be duplicated; no release was created |
| Changes to `android.yml` or the release guard | must remain intact |

## 6. Files added or changed

Added:

```
.github/workflows/cloud-device-tests.yml
.github/workflows/release-intelligence.yml
app/src/androidTest/java/com/hmx/pdf/AppLaunchSmokeTest.kt
app/src/androidTest/java/com/hmx/pdf/PdfRenderInstrumentationTest.kt
docs/release-intelligence/PHASE0_ARCHITECTURE_AUDIT.md
docs/release-intelligence/DOWNLOAD_INTELLIGENCE.md
docs/release-intelligence/CLOUD_DEVICE_TESTING.md
docs/release-intelligence/PRIVACY_AND_DATA_FLOW.md
docs/release-intelligence/OPERATIONS_GUIDE.md
docs/release-intelligence/IMPLEMENTATION_REPORT.md
docs/release-intelligence/CLOUD_DEVICE_TEST_REPORT.md
hmxwebsite/release-intelligence.html
hmxwebsite/assets/css/intelligence.css
hmxwebsite/assets/js/release-intelligence.js
hmxwebsite/data/release-intelligence.json
hmxwebsite/data/cloud-device-tests.json
hmxwebsite/data/snapshots/2026-11-20.json
tools/release_intelligence/collect.py
tools/release_intelligence/test_collect.py
tools/release_intelligence/cloud_report.py
tools/release_intelligence/test_cloud_report.py
tools/release_intelligence/device-catalog.json
```

Changed:

```
.github/ISSUE_TEMPLATE/config.yml      repo identity
CHANGELOG.md                           repo identity
CONTRIBUTING.md                        repo identity
README.md                              repo identity + new section
SECURITY.md                            repo identity
app/build.gradle.kts                   instrumentation runner + androidTest deps
hmxwebsite/README.md                   repo identity
hmxwebsite/{index,features,privacy,faq,support,about,download}.html
                                       repo identity + dashboard footer link
hmxwebsite/assets/js/release.js        repo identity
hmxwebsite/scripts/check_site.py       repo identity + new page/dataset checks
hmxwebsite/sitemap.xml                 dashboard URL
```

Not changed: `AndroidManifest.xml`, package id, version, signing configuration,
`android.yml`, release guard, `vercel.json`, `netlify.toml`, `_headers`,
`PRIVACY.md` app-data sections.

## 7. Verification summary

| Check | Result |
| --- | --- |
| Python unit tests | 28 pass |
| Dataset validation | pass |
| Site checker | 144 checks, 0 failures |
| Site preflight | pass |
| JS syntax (`node --check`) | pass (2 files) |
| JSON parse (dataset, placeholder, catalog) | pass |
| Workflow YAML parse (PyYAML) | pass (3 files, expected job sets) |
| `actionlint` | unavailable in container (`Illegal instruction`) |
| Android unit tests / lint | CI green on `4662a15` (`Android build`: build, release, release-guard) |
| `androidTest` compilation | CI green on `4662a15` (`Cloud device tests` build job) |
| Cloud device session | never run; unconfigured (cloud job skipped with notice) |
| Live site deployment | deployed; `/release-intelligence` and `/data/release-intelligence.json` return HTTP 200 |

## 8. Honest conclusion

The repository-side implementation is complete and verified by local checks plus
CI. The cloud feature is real code with a fail-closed gate and a green build job,
but it has produced **zero** device results. The
dashboard shows that plainly. Website analytics remain off, the app’s privacy
behaviour is unchanged, the production release path is untouched, and `v2.1.1`
was neither duplicated nor modified.
