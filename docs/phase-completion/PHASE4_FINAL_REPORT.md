# Phase 4 final report (autonomous master-flow convention)

Scope basis: `docs/fresh-audit/HMXPDF_MASTER_IMPLEMENTATION_ROADMAP.md` (Phase 4.0–4.6) and
`docs/fresh-audit/HMXPDF_FEATURE_GAP_ANALYSIS.md` — the five Phase 4 planning documents named in
the original work order do not exist in the repository (`docs/phase4/` absent); no scope was
invented beyond these two approved documents and the FA defect register
(`docs/fresh-audit/HMXPDF_BUGS_AND_TECHNICAL_DEBT.md`, FA-01…FA-24).

## Sub-phase status

| Sub-phase | Scope (roadmap) | Status |
|---|---|---|
| 4.0 Foundation | Save coordinator, package-safe splicing, package-inclusive session state, shared fixtures, resolve skipped recovery tests | **IMPLEMENTED AND CI VERIFIED** (below) |
| 4.1 Autosave & recovery | Autosave, recovery checkpoints, save reliability, disk-full handling, retry, process-death recovery | Not started |
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
