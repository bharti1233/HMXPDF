# Phase 0 — Architecture and privacy audit

Date: 2026-11-20
Repository audited: `tanishka1233/HMXPDF` (GitHub repository id `1439357367`)
Primary branch: `release/hmxpdf-2.1.1-build` at `15ee95e67275f4a032b887a35f2746154fbe1579`
Working tree at audit time: clean, no uncommitted files.

This audit was produced by reading the repository, its workflow, the website
source, the Gradle files, and the existing release report. Nothing was changed
before this document was written. No credentials were read or printed.

## 1. Existing architecture

| Area | What exists |
| --- | --- |
| Language / UI | Kotlin 2.3.0, Jetpack Compose 1.10.1, Material 3 |
| Build | Gradle wrapper 9.3.0, Android Gradle Plugin 9.0.0, JDK 17, compileSdk 36 |
| App id | `com.hmx.pdf`, versionName `2.1.1`, versionCode `6`, minSdk 23, targetSdk 36 |
| Modules | `:app`, `:pdf-core`, `:ocr-core`, `:backdrop`; `:office_engine` is included only when a Gradle task name contains `bundle` |
| Flavors | `play` (Play services), `foss` (sideload, optional engine download), `fdroid` (free software only) |
| ABI output | ABI-split APKs plus a universal APK; bundles skip the split |
| Document engines | In-app DOCX/XLSX code, `:pdf-core` (PdfBox-Android based), bundled OCR, optional downloaded Office engine |
| Network use | Optional Office engine download (play/foss), user-entered URL-to-PDF (foss), Play services components. No HMXPDF document server |

The application is a native Android app. It is not a web app, and it must stay
usable offline for local document workflows.

## 2. Existing workflows

There is exactly one workflow: `.github/workflows/android.yml` (“Android build”,
id `401470842`).

| Job | Trigger | What it does |
| --- | --- | --- |
| `build` | push to `main` or the primary branch, PR, dispatch, tags | JVM unit tests (`testPlayDebugUnitTest`, `:pdf-core:test`, `:ocr-core:test`), `lintPlayDebug`, debug APK, debug APK artifact |
| `release` | tag push, dispatch with `build_signed_release=true`, push to primary branch | validates the four signing secrets, materializes the keystore only for the job, builds `assemblePlayRelease` and `bundlePlayRelease`, verifies every APK certificate against the keystore, verifies the AAB is not debug-signed, uploads private artifacts, removes the keystore |
| `release-guard` | every run | runs four unsigned probes (`assemblePlayRelease`, `assemble`, `build`, `assemblePlay`) with `--dry-run` and fails unless Gradle exits non-zero with `Release signing is not configured` |

The workflow never creates or edits a GitHub Release. Publishing is a manual,
separate action.

### Findings relevant to this project

1. The four signing secrets are stored at **repository scope**, while the
   `release` environment has **no protection rules** and no environment secrets.
   Any job in the repository that references the secret names can read them.
   The cloud-testing workflow added by this project deliberately does not
   reference them; moving them to the `release` environment with required
   reviewers remains a recommended hardening step (user action).
2. The primary branch and `main` are **not protected** in this repository.
   Release safety therefore currently depends on process, not on branch rules.
3. Artifacts are private CI artifacts. The public release `v2.1.1` on this
   repository contains one APK ZIP and one `.sha256` file, published
   `2026-11-18T17:25:39Z`, with download counts of 2 and 3 respectively.

## 3. Existing website data flow

| Item | Value |
| --- | --- |
| Source | `hmxwebsite/` — static HTML, prebuilt `assets/css/site.css`, dependency-free JS |
| Hosting | Vercel, production `https://hmxpdf-website.vercel.app`; `hmxwebsite/vercel.json` sets `cleanUrls`, `trailingSlash: false`, and security headers |
| Alternative host config | `hmxwebsite/netlify.toml` and `hmxwebsite/_headers` (Netlify-compatible headers) |
| Release feed | `assets/js/release.js` calls `https://api.github.com/repos/bharti1233/HMXPDF/releases/latest` at runtime and renders tag, date, assets, sizes and per-asset SHA-256 from `digest` |
| Repo links | All site links point at `github.com/bharti1233/HMXPDF` |
| Download buttons | `Download APK` is a disabled `<button>`; `Download from GitHub` links to the releases page |
| Analytics | None. No script, pixel, cookie, or endpoint. CSP allows only `'self'` scripts and `connect-src` to `api.github.com` |
| Checks | `scripts/check_site.py` (structure, links, metadata, sitemap, release wiring) and `scripts/preflight.sh` |

`api.github.com/repos/bharti1233/HMXPDF` currently returns **HTTP 301** to
repository id `1439357367`, which is `tanishka1233/HMXPDF`. The site therefore
works through a redirect, not because the old owner name is still canonical.
Pointing the site at `tanishka1233/HMXPDF` removes that dependency without
changing behaviour.

The local site checker asserts the literal string
`api.github.com/repos/bharti1233/HMXPDF`, so the repo rename must update both the
loader and the check in the same commit.

## 4. Existing release data flow

```
git tag v2.1.1
  -> android.yml release job (protected-ish environment, repo secrets)
  -> assemblePlayRelease (5 APKs) + bundlePlayRelease (AAB)
  -> apksigner certificate comparison against the keystore
  -> private GitHub Actions artifacts
  -> manual GitHub Release with HMXPDF-v2.1.1-Android-APKs.zip + .sha256
  -> website reads releases/latest and displays assets
```

There is no automated download counter, no historical snapshot, and no
machine-readable release dataset. GitHub exposes only cumulative per-asset
`download_count`; it does not expose a per-download event stream.

## 5. Existing tests

| Source set | Files | Notes |
| --- | --- | --- |
| `app/src/test` | 54 Kotlin files | DOCX round-trip/layout/notes/tables, XLSX, PDF viewer internals, save recovery, OCR state mapping, office engine |
| `pdf-core/src/test` | 5 Kotlin files | converter orientation/sample size, rasterizer page size, decrypted cache cleanup, bidi |
| `ocr-core/src/test` | 0 | module has no test source set |
| `app/src/androidTest` | none | no instrumentation runner configured, no AndroidX test/Espresso/Compose test dependencies |
| Static checks | `lintPlayDebug`, site checker, release guard | run in CI / locally |

There is no instrumentation coverage and no device matrix. `testImplementation`
already pulls JUnit 4.13.2 and `androidx.test` core/ext-junit/rules, but those are
JVM-scope only.

## 6. Existing privacy constraints

From `PRIVACY.md` and the app source:

- No account system, no advertising, no analytics SDK, no crash-reporting SDK.
- No HMXPDF document-upload backend; documents are processed on-device.
- Network use is limited to user-initiated engine download, user-entered
  URL-to-PDF, and Google Play services components.
- Files are opened/saved through the Android document picker; recent files stay
  local.

Consequences for this project:

- Download intelligence must use only GitHub’s aggregate counters. It must never
  add a per-user download ping, a tracking pixel, or an app-side beacon.
- Website analytics must be cookieless and aggregate. If enabling a provider
  requires a dashboard change, it must wait for explicit approval.
- Cloud device tests run on CI test APKs, not on user documents. No user file
  may be uploaded to Google Cloud.
- No new app permission, SDK, or manifest component is required by any phase.

## 7. Missing capabilities

| Capability | Status before this project |
| --- | --- |
| Aggregate download metrics from GitHub | missing |
| Historical snapshots of cumulative counters | missing |
| Machine-readable release dataset | missing |
| Website analytics (aggregate, privacy-conscious) | missing |
| Instrumentation tests | missing |
| Android instrumentation runner configuration | missing |
| Cloud device test workflow | missing |
| Device matrix / DDP access | missing (no `gcloud`, no Google Cloud project configured) |
| Aggregated dashboard | missing |
| Release gate for cloud tests | missing (and must not weaken the existing gate) |

## 8. Proposed implementation

Six phases, each independently revertible:

1. **Download intelligence** — a stdlib-only Python collector at
   `tools/release_intelligence/` that reads the GitHub Releases API, classifies
   APK/AAB/ZIP/checksum assets, computes per-release and per-ABI totals, writes
   `hmxwebsite/data/release-intelligence.json`, and appends deduplicated daily
   snapshots under `hmxwebsite/data/snapshots/`. Unit tests cover classification,
   aggregation, pagination and snapshot deduplication.
2. **Website analytics** — documentation and exact Vercel steps only. No
   tracking script is added until the owner approves the dashboard setting.
3. **Cloud device testing** — a configuration-gated workflow
   (`.github/workflows/cloud-device-tests.yml`) using GitHub OIDC →
   Workload Identity Federation → `gcloud beta device-run`. Without Google Cloud
   configuration the cloud job is skipped with an explicit notice; it never
   fabricates a result.
4. **Test coverage** — an `androidTest` source set with a launch/lifecycle smoke
   test and an on-device PDF render test using a generated fixture. DOCX/XLSX
   round-trip stays covered by the existing JVM suites (they already exercise
   the real serializers); duplicating them on-device adds cost without new
   signal.
5. **Dashboard** — a static `hmxwebsite/release-intelligence.html` page that reads
   the committed JSON, shows overview/downloads/website/device sections, and
   labels data-quality limits explicitly. No backend, no authentication, no raw
   logs.
6. **Release integration** — documentation of where a cloud-test gate would sit.
   The production workflow, signing path, and release guard are **not modified**
   in this phase because cloud testing is not configured and a gate that is off
   by default would create a false sense of protection.

## 9. Required external account configuration

Nothing below is configured by this repository change; all items need the owner.

| Service | Requirement | Needed for |
| --- | --- | --- |
| GitHub | Actions enabled (already true) | all workflows |
| GitHub | `GITHUB_TOKEN` with default read access for the collector; `contents: write` only in the collector workflow | snapshots |
| GitHub | Optional: move four signing secrets into the protected `release` environment; enable branch protection | hardening, not blocking |
| Vercel | Reuse the existing project; confirm Git connection, root directory `hmxwebsite`, production branch, domain | website deploy |
| Vercel | Enable Web Analytics in the project dashboard (optional, approval required) | website metrics |
| Google Cloud | Project with billing, DDP Preview access, Cloud Testing API, Cloud Storage bucket | cloud tests |
| Google Cloud | Workload Identity Pool + OIDC provider restricted to `tanishka1233/HMXPDF`; service account with `roles/devicerun.admin`, `roles/serviceusage.serviceUsageConsumer`, `roles/viewer`, plus bucket object access | keyless CI auth |
| Google Cloud | Bucket lifecycle rule (for example delete objects after 30 days) | cost/retention |

## 10. Potential costs

- GitHub Actions: standard included minutes; the signed release job is the most
  expensive existing job. Snapshot runs are a few seconds.
- GitHub storage: negligible (JSON files, one per day, pruned).
- Vercel: existing plan. Web Analytics may require a paid tier depending on the
  current plan; this is not changed here.
- Google Cloud DDP: billed per device-minute for physical and virtual devices,
  plus Cloud Storage for inputs/artifacts. Prices are set by Google and are not
  asserted in this document. The default matrix is deliberately three devices
  with a 10-minute instrumentation timeout; the full matrix is manual-only.
- Firebase Test Lab is **not** used. Google documents its shutdown on
  2027-09-30, so no new dependency is placed on it.

## 11. Risks and rollback

| Risk | Mitigation | Rollback |
| --- | --- | --- |
| Collector commits noise to the primary branch | deduplicated snapshots, one file per day, `[skip ci]` commit message | `git revert` the data commit; delete `tools/release_intelligence/` |
| GitHub API rate limit | authenticated token in CI, retry with `Retry-After`, clear failure message | workflow can be disabled in the Actions tab |
| Website shows misleading numbers | explicit “requests, not users” labels; missing values shown as unavailable | revert the page/commit |
| Analytics violates privacy expectations | not enabled; requires approval | no change to revert |
| Cloud tests incur cost | config gate, `cloud-testing` environment, manual full matrix, timeouts, artifact retention | disable workflow; delete bucket lifecycle objects |
| Instrumentation tests flake | two deterministic tests only; no network, no user files | remove `app/src/androidTest` and the runner line |
| Any phase breaks the release path | production workflow untouched; release guard untouched | revert the phase commit |

## 12. Audit conclusion

The repository is a multi-module Kotlin/Compose Android app with one build
workflow, a static website, and no analytics, instrumentation, or cloud testing.
The safe implementation is additive: a read-only GitHub API collector, a static
dashboard, documentation-gated analytics, and a configuration-gated cloud
workflow. No application code, package id, signing key, version, release guard,
or published release needs to change.
