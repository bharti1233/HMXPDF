# Privacy and data flow

This document covers the **project infrastructure** added here: GitHub release
metrics, the website dashboard, and cloud device testing. It does not change the
Android app’s data behaviour.

## App: unchanged

The app still has:

- no account system,
- no analytics SDK,
- no crash-reporting SDK,
- no advertising SDK,
- no HMXPDF document-upload server,
- no new permission, service, receiver, provider, or exported component.

`app/src/main/AndroidManifest.xml` is untouched. The only build change is a
`testInstrumentationRunner` and debug-only `androidTestImplementation`
dependencies, which are not packaged in release APKs.

## Data collected

| Data | Where it lives | Purpose | Retention |
| --- | --- | --- | --- |
| Release tag, title, publication date, URL | public GitHub API | dashboard | while the release exists |
| Asset name, size, content type, download counter, digest | public GitHub API | download metrics | snapshot history 400 days |
| Daily cumulative snapshot | `hmxwebsite/data/snapshots/` | trend estimation | 400 days, then pruned |
| Website page HTML/JS | public website | static dashboard | versioned in Git |
| CI run id, commit, branch, device id, Android version, pass/fail | `cloud-device-tests.json` (aggregate only) | test reporting | last 60 device rows |

## Data not collected

- No IP address, cookie, local storage identifier, fingerprint, or user agent is
  stored by this project.
- No advertising id, Android ID, IMEI, contact, phone number, or location.
- No PDF/DOCX/XLSX content, file names, thumbnails, or extracted text.
- No per-download event, per-user download identity, or installation telemetry.
- No app-level analytics or crash upload.
- No raw logcat, stack trace, bugreport, screenshot, or video in the public
  repository.

## Flow 1 — download metrics

```
GitHub Actions (schedule / release event / manual)
  -> api.github.com/repos/tanishka1233/HMXPDF/releases  (read, GITHUB_TOKEN)
  -> tools/release_intelligence/collect.py
  -> hmxwebsite/data/release-intelligence.json + snapshots/YYYY-MM-DD.json
  -> commit with [skip ci]
  -> static website fetches its own JSON (same origin)
```

The browser never calls GitHub for the dashboard; it reads the committed file.
The existing Download page still calls the public GitHub API in the browser to
show the latest release, exactly as before. That request goes to GitHub, which
sees the normal HTTP metadata any web request carries; this project stores none
of it.

## Flow 2 — website analytics

Not enabled. No script, pixel, cookie, or endpoint was added. The site’s CSP
still allows only self-hosted scripts and `connect-src` to `api.github.com`.

If the owner later approves Vercel Web Analytics, it is cookieless and
aggregate, but it is still a third-party script and must be treated as a new
data practice. The exact steps are in `OPERATIONS_GUIDE.md`. Until then the
dashboard shows page views and clicks as **unavailable**.

## Flow 3 — cloud device tests

```
GitHub Actions (opt-in)
  -> OIDC token (no long-lived key)
  -> Google Cloud Workload Identity Federation
  -> gcloud beta device-run
  -> uploads only debug APKs + generated test fixtures
  -> device session
  -> aggregate JSON report artifact
  -> optional commit of aggregate rows to hmxwebsite/data/cloud-device-tests.json
```

Google Cloud necessarily records project/session metadata for billing and
operations. This project does not add device identifiers beyond the device model
id chosen for the matrix, and it never uploads a user document. The report keeps
only session id, run id, device id, Android version, and status.

## Secrets

- The existing four signing secrets are not read by the new workflows.
- The metrics workflow uses only the automatic `GITHUB_TOKEN`.
- The cloud workflow uses OIDC federation and three non-secret identifiers
  (`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`).
- No token value is printed, committed, or uploaded. `.gitignore` continues to
  exclude `key.properties` and keystores.

## Third parties

| Party | Role | Data |
| --- | --- | --- |
| GitHub | repository, Actions, Releases API, artifact storage | public release counters, CI logs, private artifacts |
| Vercel | static hosting (existing project) | standard request metadata per its policy; no project analytics enabled |
| Google Cloud | optional cloud device testing | debug APKs, generated fixtures, test results, billing metadata |

## Children and consent

No accounts, profiles, or user data are collected, so there is nothing to
consent to at the app level. The repository tooling processes only public
release counters and CI artifacts.

## Review checklist for future changes

Before adding any metric or SDK:

1. Does it identify a person or device? If yes, stop and request approval.
2. Can the same insight come from GitHub’s aggregate counters? Prefer that.
3. Is the value labelled as requests/clicks/runs rather than people?
4. Is the data retention bounded and documented here?
5. Does `PRIVACY.md` need an update because app behaviour changed? If yes, do not
   merge without explicit approval.
