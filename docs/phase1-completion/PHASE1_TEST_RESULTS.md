# Phase 1 test results

No local Gradle/Kotlin tests, APK/AAB build, instrumentation test or app runtime command was executed. No test is reported as passed here.

Updated tests cover stale replacement rejection, expected-text matching, marker movement, marker-aware comment assertions and editing before an existing comment. Existing table-cell tests remain active and were not weakened.

Required CI command: `./gradlew testPlayDebugUnitTest :pdf-core:test :ocr-core:test --rerun-tasks`. Record actual pass/fail/skip counts from CI; skipped tests are not passes.
