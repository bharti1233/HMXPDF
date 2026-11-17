# Phase 4 final report (autonomous master-flow convention)

> **2026-11-17 correction: Phase 4.1 was reopened and is now complete.** Its first green
> builds were valid build evidence, but a source audit found a checkpoint publication crash
> window, recovered packages using the wrong source mirror on later saves, non-immutable
> spreadsheet saves, unbounded generations and unswept crash temps. Repairs
> `aab606f` → `e562454` → `4c406e4` → `0d72242` closed those paths; final run 44044415038 is
> success. Device-only scenarios (real force-stop/reboot, revoked URI, real ENOSPC) remain
> unverified and are listed as limits in the 4.1 section.

Scope basis: `docs/fresh-audit/HMXPDF_MASTER_IMPLEMENTATION_ROADMAP.md` (Phase 4.0–4.6) and
`docs/fresh-audit/HMXPDF_FEATURE_GAP_ANALYSIS.md` — the five Phase 4 planning documents named in
the original work order do not exist in the repository (`docs/phase4/` absent); no scope was
invented beyond these two approved documents and the FA defect register
(`docs/fresh-audit/HMXPDF_BUGS_AND_TECHNICAL_DEBT.md`, FA-01…FA-24).

## Sub-phase status

| Sub-phase | Scope (roadmap) | Status |
|---|---|---|
| 4.0 Foundation | Save coordinator, package-safe splicing, package-inclusive session state, shared fixtures, resolve skipped recovery tests | **IMPLEMENTED AND CI VERIFIED** (below) |
| 4.1 Autosave & recovery | Autosave, recovery checkpoints, save reliability, disk-full handling, retry, process-death recovery | **COMPLETE** (CI verified below; device scenarios listed as limits) |
| 4.2 Advanced tables | Structural row/col ops, merge/split, borders, shading, cell margins, row heights | Not started |
| 4.4 Footnotes/endnotes | Note part structure and editing | Not started |
| 4.3 Spell checking | Local engine, suggestions, safe cross-run replacement | Not started |
| 4.5 Read Aloud | Android TTS, playback controls | Not started |
| 4.6 Integration & regression | Cross-feature regression, release verification | Not started |

(Execution order follows the roadmap's dependency graph: 4.1 → 4.2 → 4.4 → 4.3 → 4.5 → 4.6.)

---

## Phase 4.0 — Foundation: COMPLETE (CI verified)

Published head: `9463b5314af6e33e539dc9635c359d57f187183e` (normal pushes only).
Final CI run: https://github.com/bharti1233/Hmxpdf/actions/runs/43943430785 — completed/success
(unit tests 0 failures, lint, debug APK 170.70 MB, signed release APK 134.59 MB, AAB 51.17 MB,
release-guard). Artifacts correspond to exactly this commit (verified against the remote head).

### Defects fixed (FA register)

- **FA-03 — header/footer edits no longer drop the part's root namespaces.** The VM captures each
  loaded part's original root start tag (`hfEnvelopes`, captured on first parse) and
  `DocxWriter.Extras.hfEnvelopes` carries it to the writer; `DocxPageLayout.hfXml` re-emits the
  original envelope verbatim (foreign namespaces like `r`/`a`/`mc:Ignorable` survive). Brand-new
  parts keep the minimal `w`-only root.
- **FA-04 — one immutable save capture.** `DocxEditorViewModel.saveCapture()` snapshots
  (package, body, package-level edits) on the owner thread; `buildPatched` and the acknowledgement
  (`recordSaved(capture)`) consume exactly that generation. Edits made during a slow write stay
  dirty instead of being marked saved. The share/export path (`currentFile`) uses the same capture.
- **FA-05 — package-inclusive undo.** Undo/redo steps are `SessionSnap` (body + header/footer part
  contents + relationship claims + envelopes + settings splice). Removing a header/footer then
  undoing restores the section reference and its part/relationship claims as one unit — no
  dangling reference can reach the next save.
- **FA-06 — session relationship lookup.** `hfPathOf` consults the session's claims before the
  loaded rels, so a part created this session resolves (its rel id cannot exist in the loaded
  rels string).
- **FA-22 — OOXML `CT_OnOff` truthiness and inclusive section lookup.** `titlePg` /
  `hasEvenOdd` honor `w:val="false"|"0"|"off"` (a bare element or true/absent val is ON);
  `sectionAt` treats a `sectPr`-carrying paragraph as inside the section it terminates.
- **Skipped recovery tests resolved.** The empty `@Ignore`d `SaveRecoverySameUriTest` (2 empty
  methods) is deleted; `SaveRecovery`'s pure core (journal round trip, destination-comparison
  table, restore decision table, pending auto-discard rules) is now JVM-tested directly —
  `SaveRecoveryCoreTest` (6 tests). Context-bound halves delegate to the core; nothing was
  disabled to go green.
- **Shared test fixtures.** `DocxFixtures` builds valid in-memory DOCX packages (custom body,
  rels, content-type overrides, extra parts) used by the integrity and session tests.

### New/changed files

Main: `SaveRecovery.kt`, `DocxPageLayout.kt`, `DocxWriter.kt` (`Extras.hfEnvelopes` wiring),
`DocxEditorViewModel.kt`.
Tests: `DocxFixtures.kt`, `DocxHeaderFooterIntegrityTest.kt` (4), `DocxSessionStateTest.kt` (6),
`SaveRecoveryCoreTest.kt` (6) — 16 new tests replacing 2 empty ignored stubs.

### CI history for this sub-phase (all repair root causes fixed, none skipped-by)

| Run | Commit | Result | Root cause of failure |
|---|---|---|---|
| 43938424486 | `c8816c2` | failure | 2 compile errors (`begin(root,…)` referenced `context`; `currentFile`'s `buildPatched` call) → fixed `632d9d5` |
| 43939305850 | `632d9d5` | failure | test compile: `kotlin.io.createTempDir` deprecated at ERROR level → fixed `bf9dabd` |
| 43941290865 | `bf9dabd` | failure | genuine test failure: wrong expectation vs. the established `sections()` model (terminal body-level entry) → fixed `9463b53` (test-only; production behavior verified correct) |
| 43943430785 | `9463b53` | **success** | — |

Test outcome on the green run: the same suite as the failed run (290 executed, 42 skipped — the
pre-existing `@Ignore`d Android-Context-only classes, untouched) with 0 failures.

### Post-build source audit (STEP H)

- Built commit = published remote head (`9463b53`) — verified via `git ls-remote`.
- Combined diff touches exactly the 9 intended files; no unrelated changes.
- No TODO/FIXME/placeholder code; no secrets (the single "passwords" grep hit is a doc comment
  explaining the journal never stores them).
- Invariants held: `DocxWriter` remains the sole DOCX writer (envelope support extends the
  existing `Extras` seam, no parallel writer); byte-preserving patch architecture untouched;
  unknown parts/relations preserved; no new dependencies.
- Test compilation note: Kotlin's `createTempDir` deprecation is `DeprecationLevel.ERROR`
  (a compile error, not a suppressible warning); regular warnings remain non-fatal
  (pre-existing `w:` debt in main sources is untouched and not hidden).

### Not verified / remaining limits

- No on-device/instrumented run: the Context-bound halves of `SaveRecovery` (URI hashing, SAF
  copies) remain covered only by inspection — their decision inputs are JVM-tested.
- 42 tests remain skipped (pre-existing `@Ignore`d OfficeEngineDownloadTest classes requiring an
  Android Context); enabling them needs Robolectric or an androidTest source set (a separate,
  deliberate change, not part of 4.0 scope).
- External Word/LibreOffice compatibility of envelope-preserving HF parts is untested.

---

## Phase 4.1 — Autosave and document recovery: COMPLETE (CI verified)

Published head: `0d72242dede86ddaec1c7e56d6cab015220d02ad`.
Verification run: https://github.com/bharti1233/Hmxpdf/actions/runs/44044415038 — `build`,
`release` and `release-guard` all completed/success. Artifacts: debug APK 170,830,525 bytes
(artifact 14311642159), signed release APK 134,671,621 bytes (14310593891), AAB 51,197,800 bytes
(14310374040). The workflow checked out `0d72242…`, matching the published development branch head.

Phase 4.1 was reopened after its first green build: a source audit found interruption and
concurrency defects the original tests did not cover. This completion claim covers the repaired
protocol below; the earlier `e36abbb` verdict is superseded.

### What was implemented

- **`EditorCheckpointStore`** (`data/repository`): one complete, validated package per document
  identity — sha-256 of the source URI, never the display name — under `noBackupFilesDir`.
  Commit protocol: copy to a new immutable generation → validate (`SaveRecovery.validateOfficePackage`)
  → fsync → rename the package → write and fsync metadata → rename metadata (the single publication
  point). Until that publication the previous package and metadata are untouched; a failure or
  cancellation deletes only the new generation and temps. After publication superseded generations
  and interrupted temps are pruned, so storage is bounded to one package plus metadata per document.
  `find` validates identity, recorded hash and package structure, refuses orphans, and retires only
  the observed session via `clearIfCurrent` (a newer checkpoint is never deleted by an older save).
- **`AutosaveCoordinator`**: deterministic scheduling core — ~2 s idle debounce, 15 s bounded
  maximum dirty interval, one write at a time, edits during a write coalesce into one follow-up.
  A failed write returns a 15 s retry delay and stays dirty without needing another keystroke.
- **DOCX editor wiring** (`DocxEditorViewModel`): body/undo/redo/settings changes feed the
  coordinator; checkpoint writes use the 4.0 `SaveCapture` discipline extended with source file,
  display name and identity (one captured generation, unique temp output). A successful save marks
  only the captured generation saved, retires only the checkpoint it observed, and keeps newer
  edits scheduled. Recovery copies the checkpoint into a matching local source package so later
  saves patch recovered content, restarts undo, marks the document dirty and labels stale originals
  via the mirror hash.
- **Spreadsheet wiring** (`SpreadsheetViewModel`): an immutable `SheetCapture` (source mirror,
  display name, op list, identity) now feeds checkpoint writes, manual save, PDF export and share.
  A manual save acknowledges only an exact op-log match; edits made during the save remain dirty and
  scheduled. Cleanup is generation-aware, and patched temp files are deleted after save/export.
  Recovery restarts the op log with `savedAt = -1` (dirty until a real save); legacy .xls is
  read-only and never checkpoints.
- **Temp-file bounds** (`EditorTempFiles`): at editor load, crash-orphaned patched files older than
  1 hour and recovery mirrors older than 24 hours are removed. Only editor-owned names are touched;
  fresh files that may belong to an in-flight save/share/conversion are preserved.
- **UI**: recovery prompts reuse the existing dialogs (`GlassDialog`, `UnsavedChangesDialog`), with
  strings in all 7 locales.
- **WorkManager cleanup**: intentionally not added (optional/deferred in the roadmap); bounded
  per-document storage plus the age sweep replace it.

### Tests

- `AutosaveCoordinatorTest` (8, fake clock): idle debounce, bounded interval, clean no-schedule,
  single-write exclusion, coalesced follow-up, no-op end, save reset, failed-write retry without a
  new keystroke.
- `EditorCheckpointStoreTest` (12): metadata round trip, display-name non-identity, generation
  increments with sticky originalHash, failed commit keeps the prior checkpoint, corrupted
  checkpoint refused without deleting evidence, interrupted publication keeps the prior generation,
  bounded generation storage, failed publication leaves no generation, identity mismatch refused,
  clear, unknown identity, key stability.
- `EditorTempFilesTest` (1): only stale editor intermediates are removed; fresh and unrelated cache
  files survive.
- The full JVM test tasks (`testPlayDebugUnitTest`, `:pdf-core:test`, `:ocr-core:test`) passed in the
  verification run. 42 pre-existing skips remain (`OfficeEngineDownloadTest` needs an Android
  context); no test was disabled or skipped to obtain this result.

### CI history for this sub-phase

| Run | Commit | Result | Note |
|---|---|---|---|
| 43946472274 | `f58a6ec` | failure | public property exposed internal `Checkpoint` type → fixed `67e249a` |
| 43947101199 | `67e249a` | failure | test-only `listFiles()` NPE on a deleted directory → fixed `df0848c` |
| 43949208216 | `df0848c` | success | DOCX editor verification |
| 43951540104 | `e36abbb` | success | spreadsheet wiring (later superseded by the audit) |
| 43992838288 | `aab606f` | success | checkpoint publication + recovery-source repair |
| 43993526471 | `e562454` | success | autosave retry + detached follow-up |
| 43994949152 | `4c406e4` | success | generation-aware cleanup + source capture |
| 44043818080 | `a4d7145` | failure | compile: `cacheDir` is already a `File` → fixed `0d72242` |
| 44044415038 | `0d72242` | **success** | final 4.1 verification (build, release, release-guard) |

### Not verified / remaining limits

- No device/emulator run: real force-stop process death, device reboot, a URI revoked mid-session,
  and actual ENOSPC on a full device are **not** executed by CI. The store's publication and
  failure boundaries are covered by injected-failure JVM tests; device behaviour remains
  unverified.
- The 2 s/15 s constants are roadmap defaults, unprofiled on device.
- ENOSPC handling is reasoned and injection-tested at the checkpoint/store boundary; the SAF write
  path is protected by `SaveRecovery` (prepare/backup/journal before touching the destination), but
  a real full-disk device run was not performed.
- The spreadsheet capture snapshots the op list, which is self-contained for values/formatting, but
  the writer still reads the session's style table; concurrent style derivation during a save is
  not stress-tested.
- No WorkManager-based opportunistic cleanup (optional per roadmap).
