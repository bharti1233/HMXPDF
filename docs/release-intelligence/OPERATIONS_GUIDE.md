# Operations guide

Day-two instructions for the release intelligence and cloud device testing
features. Everything here is manual owner action unless the step says otherwise.

## 1. Check current status

| What | Command | Expected |
| --- | --- | --- |
| Dataset is valid | `python3 tools/release_intelligence/collect.py --check` | `OK hmxwebsite/data/release-intelligence.json` |
| Python tests | `python3 -m unittest discover -s tools/release_intelligence -p 'test_*.py'` | `OK` |
| Website structure | `python3 hmxwebsite/scripts/check_site.py` | `N checks, 0 failure(s)` |
| Full site gate | `bash hmxwebsite/scripts/preflight.sh` | `All preflight checks passed.` |
| Dashboard script syntax | `node --check hmxwebsite/assets/js/release-intelligence.js` | no output |
| Workflow YAML | see §9 | parses, expected job names |

## 2. Routine refresh

The collector runs automatically at **05:17 UTC** every day and whenever a
GitHub Release is published, edited, released, unpublished, or deleted.

To refresh now:

1. Actions → **Release intelligence** → **Run workflow**.
2. Leave `force_snapshot` off for a normal refresh. Turn it on only when you want
   a heartbeat snapshot even though no counter changed.
3. The job runs tests, collects, validates, commits `hmxwebsite/data/**` with
   `Update release intelligence data [skip ci]`, and uploads an artifact.

Locally:

```bash
export GITHUB_TOKEN=...            # never commit or print the value
python3 tools/release_intelligence/collect.py
python3 tools/release_intelligence/collect.py --check
git diff --stat hmxwebsite/data
```

Prefer the workflow. A local run writes snapshots for the current UTC day, and a
second run the same day replaces that day's file only if values changed.

### What a refresh can and cannot do

- It cannot invent numbers: every value comes from GitHub’s asset
  `download_count`, `size`, or `digest`.
- It cannot see individual downloads. GitHub has no event stream.
- It cannot backfill history. Snapshots start at the first run.
- It cannot remove past snapshots except through the 400-day pruning rule or a
  manual delete.

### If GitHub rate-limits the run

The collector retries `403`/`429` responses that carry `Retry-After` or an
exhausted quota, then fails with a clear message. It never writes a partial
dataset. Wait for the window to reset and re-run. The workflow uses the automatic
`secrets.GITHUB_TOKEN`; do not add a personal token.

## 3. Restore or roll back a snapshot

Snapshots are ordinary JSON files in `hmxwebsite/data/snapshots/`.

```bash
# See what changed
git log --oneline -- hmxwebsite/data
git show <commit> -- hmxwebsite/data/snapshots/2026-11-20.json

# Restore one day from an older commit
git checkout <commit> -- hmxwebsite/data/snapshots/2026-11-20.json
git commit -m "Restore release snapshot 2026-11-20 [skip ci]"

# Remove a bad day (future runs will recreate it only if the counters differ)
git rm hmxwebsite/data/snapshots/2026-11-20.json
git commit -m "Drop invalid release snapshot [skip ci]"
```

Restore the whole dataset:

```bash
git checkout <commit> -- hmxwebsite/data
git commit -m "Restore release intelligence dataset [skip ci]"
```

The dashboard reads only `release-intelligence.json`. Snapshot files are history
for the trend section, so a missing day shows as a gap, not a zero.

## 4. Website analytics (optional, approval required)

Currently **not enabled**. No analytics script, pixel, cookie, or endpoint exists.
The dashboard reports page views and link clicks as **unavailable**, not zero.
Do not add a script by hand; it would violate the site CSP
(`script-src 'self'`) and the privacy stance.

If the owner approves Vercel Web Analytics:

1. Sign in to Vercel and open the existing HMXPDF project. Do **not** create a new
   project, move the domain, or change the root directory.
2. Project → **Analytics** → **Enable**.
3. Confirm the plan. Web Analytics availability and limits depend on the current
   Vercel plan; if it requires an upgrade, stop and get explicit cost approval.
4. Vercel normally injects its script at the edge for projects it builds. Verify
   the deployed page source contains the analytics script, or follow Vercel’s
   current framework-specific instruction.
5. Check the site’s CSP. The existing header is
   `script-src 'self'` and `connect-src 'self' https://api.github.com`.
   Vercel Analytics needs its own script/connect origins. Either:
   - let Vercel manage the analytics injection and confirm the live CSP in
     DevTools → Network → document response headers, or
   - add the exact origins Vercel documents, **without** loosening
     `script-src` to `'unsafe-inline'`.
6. Redeploy the existing project (Deployments → Redeploy). Do not change the
   production branch or domain.
7. Visit the site, then check Project → Analytics for a page view. Confirm no
   cookie is set and no personal data appears.
8. Update `docs/release-intelligence/PRIVACY_AND_DATA_FLOW.md` and the dashboard
   copy to replace “unavailable” with the real source and its caveats. Treat this
   as a new data practice and mention it in `PRIVACY.md` only if app behaviour
   changes; website-only analytics does not change the app.

Rollback: Project → Analytics → Disable, then redeploy. No repository change is
required. Revert any CSP change separately.

## 5. Google Cloud setup for device tests (owner action)

Full detail is in `CLOUD_DEVICE_TESTING.md` §“Required Google Cloud setup”. Short
version:

1. Choose a project, enable billing.
2. Verify DDP Preview access; enable the Cloud Testing API.
3. Create a bucket and a 30-day lifecycle rule.
4. Create `hmxpdf-cloud-tests` with `roles/devicerun.admin`,
   `roles/serviceusage.serviceUsageConsumer`, `roles/viewer`, and bucket-scoped
   object access.
5. Create a Workload Identity Pool + GitHub OIDC provider restricted to
   `assertion.repository == "tanishka1233/HMXPDF"`.
6. Grant `roles/iam.workloadIdentityUser` to the repository principal set.
7. Add repository secrets `GCP_WORKLOAD_IDENTITY_PROVIDER`,
   `GCP_SERVICE_ACCOUNT`, `GCP_PROJECT_ID`; add variable `DDP_BUCKET`.
8. Create the `cloud-testing` environment with required reviewers.
9. Leave `DDP_AUTORUN` unset until you are ready for automatic three-device runs.

**Do not** create a service-account JSON key. The workflow uses OIDC only.

### Verify access without spending money

`gcloud beta device-run devices list` is a read-only catalog call. Run it locally
or in a scratch job to confirm authentication and IAM before submitting a
session. Submitting a session starts billable device time.

## 6. Secret rotation

The new workflows never read the four release-signing secrets. If you rotate
those, follow the existing release process; nothing here changes.

For cloud testing, rotate the three configuration values only if they change:

```bash
# Names only; values are read interactively and never echoed.
gh secret set GCP_WORKLOAD_IDENTITY_PROVIDER --repo tanishka1233/HMXPDF
gh secret set GCP_SERVICE_ACCOUNT --repo tanishka1233/HMXPDF
gh secret set GCP_PROJECT_ID --repo tanishka1233/HMXPDF
gh variable set DDP_BUCKET --repo tanishka1233/HMXPDF
```

Using the GitHub web UI is equally fine. To revoke access, delete the Workload
Identity provider, the service-account binding, or the environment reviewers;
the workflow then skips rather than running unauthenticated.

If a workflow log ever prints a secret value, treat it as compromised: rotate it,
delete the run log if policy requires, and review the workflow that printed it.
The current workflows print only names and non-secret outputs.

## 7. Disabling the new workflows

| Goal | Action |
| --- | --- |
| Stop daily metric commits | Actions → **Release intelligence** → `…` → **Disable workflow** |
| Stop cloud test builds (not just cloud runs) | Actions → **Cloud device tests** → **Disable workflow** |
| Stop billable cloud runs only | Leave `DDP_AUTORUN` unset and do not dispatch with `confirm_paid_run=true`; or remove `cloud-testing` reviewers |
| Remove the feature entirely | Delete the workflow file and its supporting files, then commit |

Removing files does not affect `android.yml`, the release guard, signing, or the
published `v2.1.1` release.

## 8. Dashboard troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| “Release data is unavailable” | `data/release-intelligence.json` missing, invalid, or blocked | run `collect.py --check`; confirm the file is committed and deployed |
| Numbers look stale | workflow disabled or failing | check the Actions run and the `generated_at_utc` value |
| Snapshot trend is one point | only one daily capture exists | wait; a trend needs several days |
| Cloud section says “Not configured” | no cloud run recorded | expected until §5 is complete; missing data is not a pass |
| Page loads but styles are plain | `intelligence.css` not deployed | redeploy the existing Vercel project |

Force a browser refresh after a deploy; the dataset request uses
`cache: 'no-store'`, but the HTML/CSS may still be cached.

## 9. Validating workflow YAML

`actionlint` is the preferred checker in CI or on a normal workstation. In this
development container its prebuilt binary crashes with `Illegal instruction`, so
YAML was validated with PyYAML instead:

```bash
python3 -m venv /tmp/opencode/venv
/tmp/opencode/venv/bin/pip install pyyaml
/tmp/opencode/venv/bin/python - <<'PY'
import glob, yaml
expected = {
    ".github/workflows/android.yml": {"build", "release", "release-guard"},
    ".github/workflows/release-intelligence.yml": {"collect"},
    ".github/workflows/cloud-device-tests.yml": {
        "build-test-apks", "configuration", "cloud-run", "publish-report"
    },
}
for path in sorted(glob.glob(".github/workflows/*.yml")):
    data = yaml.safe_load(open(path))
    assert set(data["jobs"]) == expected[path], path
    print(path, "OK", sorted(data["jobs"]))
PY
```

Run `actionlint` in CI if you want stronger expression checking. Do not add a
third-party action just to lint YAML.

## 10. Routine checklist

Weekly:

- [ ] Last **Release intelligence** run succeeded.
- [ ] Latest snapshot date is within two days.
- [ ] `generated_at_utc` is recent.
- [ ] Android build is green on the primary branch.
- [ ] Cloud workflow builds APKs and correctly skips the cloud job while
      unconfigured.

Before enabling cloud automation:

- [ ] Read-only catalog call works with OIDC.
- [ ] `cloud-testing` has required reviewers.
- [ ] Bucket lifecycle rule exists.
- [ ] A manual three-device run has passed at least twice.
- [ ] Cost owner has approved automatic runs.
