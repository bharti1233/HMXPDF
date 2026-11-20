# Cloud device testing

Status: **implemented, not executed.** Google Cloud access is not configured for
this repository, so no billable session has been started and no result is
claimed. The workflow fails closed: an unconfigured run is skipped with a
notice, never reported as a pass.

## Provider verification

Facts checked against the official documentation on 2026-11-20:

| Fact | Source |
| --- | --- |
| Device Run is a Google Cloud service under Developer Device Platform (DDP), in Preview | `docs.cloud.google.com/developer-device-platform/device-run` |
| CLI is `gcloud beta device-run` with `sessions submit instrumentation` | same page and `.../device-run/android-instrument` |
| Android instrumentation uses `--device`, `--apps`, `--test` | `.../device-run/android-instrument` |
| Output artifacts go to Cloud Storage under `.../automation/sessions/session-ID/` | `.../device-run` |
| Required IAM roles include `roles/devicerun.admin`, `roles/serviceusage.serviceUsageConsumer`, `roles/viewer` | `.../quickstart` |
| Firebase Test Lab is not used; Google documents its shutdown on 2027-09-30 | Firebase Test Lab documentation |

No CLI flag, device id, or bucket name in this repository was invented. Device
ids come from the current Device Catalog page; the workflow lists the catalog
again before submitting because availability changes.

## Test APKs

The workflow builds only debug artifacts:

```bash
./gradlew assemblePlayDebug assemblePlayDebugAndroidTest
```

It copies:

- `app-play-universal-debug.apk` (package `com.hmx.pdf`, versionName `2.1.1`)
- the instrumentation APK (package `com.hmx.pdf.test`)

Both package ids are asserted with `aapt dump badging` before upload. Release
signing secrets are not referenced by this workflow at all.

## Instrumentation coverage

Two deterministic tests, both using generated fixtures and no user storage:

| Test | What it proves |
| --- | --- |
| `AppLaunchSmokeTest.launcherActivityResumes` | the launcher activity starts, attaches its window, and reaches RESUMED |
| `AppLaunchSmokeTest.survivesBackgroundResumeAndRecreation` | background → resume and activity recreation keep the app usable |
| `PdfRenderInstrumentationTest.rendersGeneratedPdfOnDevice` | a PdfBox-generated PDF is opened by the platform `PdfRenderer` on this device/ABI and a black square is actually rasterized |

DOCX and XLSX round-trip behaviour is not duplicated on-device: it is already
covered by the JVM suites (`DocxRoundTripTest`, `DocxTablesTest`,
`OfficePackageValidationTest`, and related files) that run in the existing
build job. Re-implementing the editor UI journeys would require document
fixtures and navigation that do not exist yet; that work is listed as a gap, not
claimed as done.

Not automated yet:

- document picker grant/deny journeys,
- DOCX/XLSX edit-and-save through the UI,
- OCR flows that depend on Google Play services,
- portrait/landscape and large-font visual checks,
- low-memory lifecycle stress.

These are listed honestly because cloud coverage is not proof of compatibility
with every physical device.

## Device matrix

Default (three devices, the only automatic option):

| Device id | Model | Android | Type | Why |
| --- | --- | --- | --- | --- |
| `mediumphone-arm-26` | Medium Phone (Arm) | 26 | virtual | oldest Android in the current catalog |
| `shiba-34` | Pixel 8 | 34 | physical | mid-lifecycle physical phone |
| `shiba-36` | Pixel 8 | 36 | physical | current target SDK |

Full matrix (manual dispatch only):

`mediumphone-arm-26`, `redfin-30` (Pixel 5), `panther-33` (Pixel 7),
`shiba-34`, `smallphone-arm-34` (4.65in virtual), `mediumtablet-arm-35`
(10.05in virtual), `shiba-36`, `tangorpro-36` (Pixel Tablet).

Gap: the catalog starts at Android 26. The app supports API 23, so API 23–25
cannot be tested on DDP today. The nearest available version (26) is used and
the gap is stated rather than hidden.

## Required Google Cloud setup (owner action)

1. Create or choose a Google Cloud project and enable billing.
2. Request/verify Developer Device Platform Preview access, then enable the
   Cloud Testing API (required by Device Run during Preview).
3. Create a Cloud Storage bucket (for example `hmxpdf-devicerun`) in the same
   project and add a lifecycle rule that deletes objects after 30 days.
4. Create a service account, for example `hmxpdf-cloud-tests`, and grant:
   - `roles/devicerun.admin`
   - `roles/serviceusage.serviceUsageConsumer`
   - `roles/viewer`
   - object access on the test bucket (for example `roles/storage.objectAdmin`
     scoped to that bucket)
5. Create a Workload Identity Pool and a GitHub OIDC provider:
   - issuer `https://token.actions.githubusercontent.com`
   - audience `https://github.com/tanishka1233`
   - attribute condition restricted to this repository, for example
     `assertion.repository == "tanishka1233/HMXPDF"`
6. Allow the repository principal to impersonate the service account:
   `roles/iam.workloadIdentityUser` on the service account for the
   `principalSet://.../attribute.repository/tanishka1233/HMXPDF` principal.
7. Add repository secrets (values never printed):
   - `GCP_WORKLOAD_IDENTITY_PROVIDER`
   - `GCP_SERVICE_ACCOUNT`
   - `GCP_PROJECT_ID`
8. Add the repository variable `DDP_BUCKET` with the bucket name.
9. Create the `cloud-testing` environment and add required reviewers so a
   billable run needs a human approval.
10. Optional: set repository variable `DDP_AUTORUN=true` to allow automatic
    small-matrix runs on pushes to the primary branch and pull requests. Leave
    it unset to require a manual dispatch with `confirm_paid_run=true`.

No service-account JSON key is needed or accepted by this workflow.

## Workflow behaviour

`.github/workflows/cloud-device-tests.yml`

| Job | Runs when | What it does |
| --- | --- | --- |
| `build-test-apks` | PR, push (non-doc changes), dispatch | builds and validates debug/test APKs, uploads a 7-day artifact |
| `configuration` | after build | checks the three secret names; outputs `enabled` and the device list |
| `cloud-run` | configured **and** (manual confirmation **or** `DDP_AUTORUN=true`) | OIDC auth, catalog listing, submits instrumentation, writes report, fails unless every row passed |
| `publish-report` | push to the primary branch, not PR | commits the aggregate report to `hmxwebsite/data/cloud-device-tests.json` with `[skip ci]` |

Cost controls:

- three-device default matrix;
- `--instrumentation-timeout=10m` (allowed range 1m–3h);
- job timeout 45 minutes;
- one concurrency group per ref with cancellation of obsolete runs;
- 7-day APK artifact retention, 30-day report retention;
- bucket lifecycle recommendation (30 days);
- no automatic run until explicitly enabled.

## Reports

`tools/release_intelligence/cloud_report.py` parses the console result table and
writes an aggregate JSON report:

```json
{
  "status": "passed",
  "summary": "3 of 3 device run(s) passed.",
  "session": {"id": "session-…", "result": "PASSED", "report_url": "https://console.cloud.google.com/…"},
  "build": {"run_id": "…", "run_url": "…", "commit": "…", "branch": "…", "apk": "…", "test_apk": "…"},
  "runs": [
    {"device": "shiba-34", "android_version": "34", "status": "passed", "failure_classification": null}
  ]
}
```

Failure classification values: `app_crash`, `test_failure`, `timeout`,
`infrastructure_or_input_error`, `missing_result`. A missing result table is
`error`, never `passed`. A device/job count mismatch is `error`.

The workflow uploads the JSON and console log as a private artifact and publishes
only the aggregate JSON. Raw logcat, stack traces, bugreports, and signed Cloud
Storage URLs are never committed or shown on the public dashboard.

## Making cloud tests a release gate (not enabled)

The production workflow, signing path, and release guard are unchanged. When the
cloud suite has a stable history:

1. Require `Cloud device tests / Run instrumentation on cloud devices` as a
   status check on the primary branch.
2. Add a release-job dependency on that check, or run the cloud workflow as a
   reusable workflow from the release path.
3. Keep the signing job in the protected `release` environment and never pass
   signing secrets to the cloud job.

Do not enable a gate while the cloud job is unconfigured: a skipped job must not
look like a pass.

## Rollback

- Disable the workflow in the Actions tab, or delete
  `.github/workflows/cloud-device-tests.yml`.
- Delete `app/src/androidTest/` and remove the `testInstrumentationRunner` line
  and four `androidTestImplementation` lines from `app/build.gradle.kts`.
- Delete `hmxwebsite/data/cloud-device-tests.json` (the dashboard shows
  “Not configured”).
- Nothing in the production release path changes, so no release rollback is
  needed.
