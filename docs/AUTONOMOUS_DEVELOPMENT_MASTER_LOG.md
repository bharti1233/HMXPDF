# HMXPDF autonomous development master log

## Recovery audit update — 2026-11-17

Phase 4.1 is REOPENED; earlier completion statements below are superseded. Green CI did not
prove interruption safety. Source audit found replacement of package bytes before metadata
publication could invalidate the previous checkpoint, and recovery kept using the original
package as the subsequent writer source. Repairs now use immutable generation filenames with
a single metadata publication point, sync metadata after writing, retain unreadable recovery
data, and copy recovered packages into matching editor source mirrors. An injected failure
before metadata publication verifies preservation of the previously committed generation.

Validation so far: `git diff --check` passed; no local Gradle/APK builds. New CI verification
is pending. Phase 4.2 must wait for the reopened foundation gate. Remaining audit items include
save/checkpoint races, newer edits during save, spreadsheet op identity versus list length,
retry scheduling, startup recovery with inaccessible originals, and storage bounds. Earlier
claims that all these scenarios were covered by the original JVM tests were too broad.

Recovery point for autonomous phase-by-phase work. Update after every meaningful operation.

## Environment and identity

- Local workspace (no `.git`): `/mnt/sdcard/AIProjects/Hmxpdf` (= `/storage/emulated/0/AIProjects/Hmxpdf`)
- Working clone: `/tmp/opencode/hmxpdf-phase1-publish`
- Remote: https://github.com/bharti1233/Hmxpdf.git
- Actual default branch (discovered via `git ls-remote --symref`): `release/hmxpdf-2.1.1-build`
- CI: `.github/workflows/android.yml` — on push to the default branch: unit tests → lint → `assemblePlayDebug` → signed `assemblePlayRelease` + `bundlePlayRelease` (release environment secrets) → `release-guard`.

## Phase 1 — DOCX Editing Foundation: COMPLETE (CI verified)

- Pre-publication baseline preserved: branch `backup/pre-phase1-publication` @ `55007c32663c0c3e84bc76ec1abbed07e3318bc8`.
- Publication commit: `c031c732c6d9a8dff64f4fd8b2349ef5039e5ace` (normal push to the default branch).
  - 13 modified source/test files: DocxModel/Reader/Writer/Edits/Comments/Revisions, DocxEditorViewModel, DocxEditorScreen, plus 5 test classes.
  - Plus docs: `docs/fresh-audit/` (14), `docs/phase1-completion/` (8), and the pre-Phase-1 audit trail.
- Token note: the token supplied with an `app.` prefix was rejected (401); the same token without the prefix authenticated (scopes `repo`, `workflow`). Masked in all logs. Recommendation: rotate this token after use since it was pasted in plain text.
- CI run 43934592604 (https://github.com/bharti1233/Hmxpdf/actions/runs/43934592604): **completed/success**.
  - Jobs: build (tests+lint+debug APK) ✅, release (signed APK 134.59 MB + AAB 51.17 MB, signature verified) ✅, release-guard ✅.
  - Debug APK artifact: `hmx-pdf-debug-apk` 170.70 MB.
  - Test counts not published by workflow; step success recorded only.
- Post-build audit: modified-file diff reviewed; no secrets, no dead code introduced; `DocxWriter` remains the sole DOCX writer; architecture invariants held.
- Reports: `docs/phase1-completion/*` (8 files) and `docs/phase-completion/PHASE1_FINAL_REPORT.md`.
- Not verified: on-device/instrumentation behavior; external Word/LibreOffice compatibility.

## Phase 2 — Track Changes: COMPLETE (CI verified)

- Re-verified against source at `c031c73` (not trusting the phase reports): reader parses `w:ins`/`w:del`/`w:delText` into per-char `Rev` flags; writer emits `w:ins`/`w:del` wrappers + `w:delText`; `DocxRevisions.accept/reject/acceptAll/rejectAll` present; VM `tracking`/`pendingRevisions`/`resolveRevision`/`resolveAllRevisions` present; `DocPanel.REVISIONS` panel with Track toggle and accept/reject-all actions present.
- Tests: `DocxRevisionsTest` (24 `@Test`) + `DocxTrackingStateTest` (9 `@Test`) — green in run 43934592604 (head `c031c73`).
- Debug + signed release APK/AAB artifacts for the same commit verified.
- Report: `docs/phase-completion/PHASE2_FINAL_REPORT.md`.
- Not verified: on-device panel review; external Word/LibreOffice handling of emitted wrappers.

## Phase 3 — Page Layout and Page Setup: COMPLETE (CI verified)

- Re-verified against source: `DocxPageLayout` (sections, orientation/sizes/margins/gutter, titlePg, section-break insert/type, HF references, even/odd settings splice), VM ops (`setSectionSetup`, `commitSect` rebase, HF editing with stable-id cache), `DocPanel.LAYOUT` panel UI, `DocxPageLayoutTest` (18 round-trip tests) — green in run 43934592604.
- Rejected experimental direct-manipulation UI was not reintroduced.
- Report: `docs/phase-completion/PHASE3_FINAL_REPORT.md`.

## Phase 4 — Advanced Document Editing: 4.0 COMPLETE (CI verified)

Planning basis: `docs/fresh-audit/HMXPDF_MASTER_IMPLEMENTATION_ROADMAP.md` + `HMXPDF_FEATURE_GAP_ANALYSIS.md` (+ FA register `HMXPDF_BUGS_AND_TECHNICAL_DEBT.md`). The five named `docs/phase4/*.md` planning docs do not exist; scope limited to the approved docs — no invention.

### Phase 4.0 — Foundation: COMPLETE

Commits (normal pushes): `c8816c2` (implementation) → repairs `632d9d5` (2 compile errors: `SaveRecovery.begin(root,…)` context seam, `currentFile` capture), `bf9dabd` (`createTempDir` deprecated-at-ERROR in test code; unused import), `9463b53` (test-only: `sections()` terminal-entry model). Final: run 43943430785 — **success** (tests 0 failures / 42 pre-existing skips, lint, debug APK 170.70 MB, signed release APK 134.59 MB + AAB 51.17 MB, release-guard).

- FA-03: HF envelope preservation (`hfEnvelopes` VM capture → `Extras` → `hfXml` re-emits original root start tag).
- FA-04: `saveCapture()` immutable generation; writer + `recordSaved(capture)` consume exactly it; share/export path too.
- FA-05: `SessionSnap` package-inclusive undo/redo (HF parts, rel claims, envelopes, settings).
- FA-06: `hfPathOf` resolves session-created parts first.
- FA-22: `CT_OnOff` val-aware `titlePg`/`hasEvenOdd`; inclusive `sectionAt`.
- Recovery: `SaveRecovery` pure core JVM-tested (`SaveRecoveryCoreTest`, 6 tests) replacing the empty `@Ignore`d `SaveRecoverySameUriTest`.
- Shared `DocxFixtures`; 16 new tests total. Post-build audit clean (built commit = remote head; diff scope exact; no secrets/placeholders; sole-writer invariant held).

Report: `docs/phase-completion/PHASE4_FINAL_REPORT.md`.

## Phase 4.1 — Autosave and Recovery: COMPLETE (CI verified)

Commits: `f58a6ec` (DOCX editor: store + coordinator + wiring + recovery UI) → repair `67e249a` (internal visibility of `pendingCheckpoint`) → repair `df0848c` (test-only `listFiles` NPE) → `e36abbb` (spreadsheet wiring). Final runs: 43949208216 (DOCX) and 43951540104 (full) — **both success** (305 tests / 0 failures / 42 pre-existing skips, lint, debug APK 170.82 MB, signed release APK 134.65 MB + AAB 51.20 MB, release-guard).

- `EditorCheckpointStore`: one validated complete package per document identity (sha-256 of the source URI) under noBackupFilesDir; validate→atomic-rename keeps the last known-good checkpoint through disk-full/interruption/death; generation + sticky originalHash metadata; corrupt leftovers refused+cleaned.
- `AutosaveCoordinator`: 2 s idle debounce, 15 s bounded dirty interval, one write at a time, edits-during-write coalesce into one immediate follow-up.
- Both editors wired: checkpoint writes ride the save-capture/op-log discipline; manual save clears the store; load offers recover/discard/later; recovery never produces a false clean state; stale originals labeled. Recovery UI in the established dialog patterns, 7 locales.
- Tests: AutosaveCoordinatorTest (7) + EditorCheckpointStoreTest (8).
- Limits: on-device force-stop/restart scenarios remain device-verified work; 2 s/15 s unprofiled; WorkManager cleanup not added (roadmap-optional).

Report: `docs/phase-completion/PHASE4_FINAL_REPORT.md`.

## Phase 4.2 — Advanced Tables: NEXT

Next steps (STEP A): read roadmap §4.2 + gap-analysis "Advanced DOCX tables"; audit the existing table model (reader cell blocks, `mapContainerOf`, writer `table`), reject/protect revision-bearing structural edits; implement row/col ops, merge/split, borders/shading/margins/row heights with tests; publish; monitor CI.

## Open items / risks

- Exact unit-test counts invisible to CI reporting (no JUnit XML artifact) — consider adding a test-report upload step in a later phase commit.
- External Office compatibility fixtures still unrun.
- Device verification requires manual install of the CI APK artifacts.
