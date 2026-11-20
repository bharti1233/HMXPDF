# Cloud device test report

Date: 2026-11-20
Provider: Google Cloud Developer Device Platform (Device Run, **Preview**)
Status: **not executed** — Google Cloud access is not configured.

This report covers test design, coverage, device matrix, and the reasons no
result exists yet. It contains no invented pass rate, device result, or timing.

## 1. Result

```
Test APK build:      passed (CI run 44660011655, commit 4662a15)
Sessions submitted:  0
Devices exercised:   0
Tests executed:      0
Aggregate status:    not_configured
```

`hmxwebsite/data/cloud-device-tests.json` records `status: "not_configured"` with
an empty `runs` array. The dashboard renders “Not configured” and “No cloud run
recorded”, not “0 / 0 passed”.

## 2. Test inventory

Two test classes, three test methods, all deterministic and offline.

| Test | Class | What it asserts | User data |
| --- | --- | --- | --- |
| `launcherActivityResumes` | `AppLaunchSmokeTest` | `MainActivity` launches, decor view is attached, lifecycle reaches `RESUMED` | none |
| `survivesBackgroundResumeAndRecreation` | `AppLaunchSmokeTest` | `CREATED` → `RESUMED` → `recreate()` leaves the activity at least `RESUMED` | none |
| `rendersGeneratedPdfOnDevice` | `PdfRenderInstrumentationTest` | PdfBox-generated 200×200 PDF opens in platform `PdfRenderer`, has one page, and rasterizes a non-blank dark region | none |

The PDF fixture is generated inside `context.cacheDir` during the test and
deleted afterwards. No document picker, permission dialog, network call, or
account is involved, which keeps the tests suitable for unattended cloud runs.

### Why only three tests

Instrumentation tests are valuable when they exercise something the JVM tests
cannot: the real Android framework, window lifecycle, and the platform PDF
renderer on a specific ABI. The existing 54 app JVM tests already cover DOCX
round-trip, tables, notes, comments, revisions, XLSX handling, save recovery, and
office package validation using the real serializers. Re-running those on a
device would add cost without new signal.

What is genuinely missing on-device is UI navigation and document-picker
journeys. Adding them safely needs fixture documents and a stable semantics
strategy, which this change does not have. They are listed as gaps below rather
than faked.

## 3. Build inputs

The workflow builds these from the pushed commit:

```bash
./gradlew assemblePlayDebug assemblePlayDebugAndroidTest
```

Validation performed by the workflow before upload:

- app package `com.hmx.pdf`, test package `com.hmx.pdf.test`;
- `versionName='2.1.1'`;
- the universal debug APK and the instrumentation APK both exist.

Only these debug artifacts are uploaded. No release APK, AAB, keystore, or
signing secret enters the cloud job.

## 4. Device matrix

Default (automatic option once enabled):

| Device id | Model | API | Type | Coverage role |
| --- | --- | --- | --- | --- |
| `mediumphone-arm-26` | Medium Phone (Arm) | 26 | virtual | oldest catalog version, ARM |
| `shiba-34` | Pixel 8 | 34 | physical | mid-lifecycle physical phone |
| `shiba-36` | Pixel 8 | 36 | physical | current target SDK |

Full (manual dispatch only):

`mediumphone-arm-26`, `redfin-30` (Pixel 5, 30), `panther-33` (Pixel 7, 33),
`shiba-34`, `smallphone-arm-34` (4.65in virtual), `mediumtablet-arm-35`
(10.05in virtual), `shiba-36`, `tangorpro-36` (Pixel Tablet).

Device ids were taken from the current Device Catalog. The workflow still lists
the catalog before submitting, because capacity and availability change.

### Coverage gaps

| Gap | Detail |
| --- | --- |
| API 23–25 | The DDP catalog begins at Android 26. The app supports 23, so three supported versions cannot be tested on this provider. |
| Other ABIs | The matrix is ARM-heavy. The universal debug APK covers the app, but x86/x86_64 device coverage is not in the default matrix. |
| Tablets | Only the manual full matrix includes a tablet. |
| Foldables / large screens | Not in the verified catalog selection here. |
| Landscape, split screen, font scale | Not exercised. |
| Low-memory / process death | Recreation is tested; forced process death is not. |

## 5. Failure classification

`cloud_report.py` maps console output to a small vocabulary:

| Value | Meaning |
| --- | --- |
| `app_crash` | crash or fatal exception in the run detail |
| `test_failure` | assertion failure |
| `timeout` | instrumentation timeout |
| `infrastructure_or_input_error` | provider/input `ERROR` |
| `missing_result` | no row for a requested device |

If the result table is absent, the overall status is `error`. If the device count
does not match the requested count, the overall status is `error`. Neither case
can be mistaken for a pass.

## 6. Cost and safety controls

| Control | Value |
| --- | --- |
| Automatic run | off unless `DDP_AUTORUN=true` |
| Manual run | requires `confirm_paid_run=true` |
| Environment | `cloud-testing`, intended to require reviewers |
| Default matrix | 3 devices |
| Instrumentation timeout | 10 minutes |
| Job timeout | 45 minutes |
| Concurrency | one group per ref, cancel obsolete |
| APK artifact retention | 7 days |
| Report retention | 30 days |
| Bucket lifecycle | 30 days recommended |
| Signing secrets | never referenced |

Billing is controlled by Google Cloud, not by the workflow. Run
`gcloud beta device-run devices list` first: it is read-only. A submitted session
consumes device time.

## 7. What would make this report say “passed”

1. Complete the Google Cloud setup in `CLOUD_DEVICE_TESTING.md`.
2. Confirm a read-only catalog call succeeds. (The build half is already green;
   this step is about authentication and IAM.)
3. Dispatch **Cloud device tests** with `device_matrix=default` and
   `confirm_paid_run=true`.
4. Open the run, review the step summary, and download the
   `cloud-test-report` artifact.
5. Confirm `hmxwebsite/data/cloud-device-tests.json` shows real rows only after
   the publish job runs on the primary branch.

Until all five happen, the correct statement is: **cloud device testing is
implemented, gated, and unexecuted.**

## 8. Recommended next increments

1. ~~Push and confirm `assemblePlayDebugAndroidTest` compiles in CI.~~ Done:
   the build job passed on commit `4662a15`. Two R8 fixes were required; see
   `IMPLEMENTATION_REPORT.md` §3.2.
2. Enable the minimum three-device matrix and run it manually twice.
3. Add a document-picker smoke test using a generated DOCX/XLSX fixture in app
   cache, once a stable semantics selector exists.
4. Add a landscape/font-scale launch variant.
5. Only then evaluate a release status check; keep it separate from signing.

No release gate is enabled now, and no result is claimed.
