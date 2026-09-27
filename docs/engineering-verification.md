# Engineering lab verification record

Verification date: 2026-09-27. Implementation is on `codex/engineering-lab`.
Production is unchanged and the feature flag defaults to off. No commit, push,
or deployment has been performed for this change. Incomplete gates are not passes.

## Executed checks

- Final complete Django suite: 222 discovered, **212 executed successfully and ten
  skipped** on SQLite, in 74.455 seconds after the final race fixes. This includes 21 ML tests and five
  rendered-form tests; skips are not counted as concurrency evidence.
- **All 77 Engineering Lab tests passed on MySQL 8.4.11**, zero skips, in
  22.268 seconds after a clean full migration chain. This includes all six
  concurrency/lost-acknowledgement/rollback/stale-claim cases.
  This run preceded the final lazy-auth ordering fix; that fix and its two new
  tests were verified in the final SQLite suite. The six concurrency paths are
  unchanged. The expanded MySQL suite must also run in CI before release.
- Final shipping review reproduced two further concurrency defects: independently
  loaded session copies could initialize different owner secrets, and expired-run
  cleanup could collect children before a concurrent source transaction committed.
  Canonical session initialization now holds the database session row lock; cleanup
  holds root locks before cascade collection. Two deterministic owner regressions
  passed locally. New MySQL first-use and cleanup-overlap tests are CI gates; the
  local VM failed to start with `HCS_E_CONNECTION_TIMEOUT`, so their SQLite skips
  are not concurrency evidence. Independent follow-up cleared both fixes.
- A bounded coverage audit mapped 28 of 30 behaviors to evidence (93% AI-assessed,
  not measured coverage). Broader simultaneous cap/reset-cleanup combinations
  remain coverage gaps, not reproduced defects or assertions of complete coverage.
- Permission extraction: 13 focused tests passed, including 128 pure fact
  combinations, 48 object-role/resource cases, and existing policy regressions.
- Six dependency-free JavaScript event-contract tests passed after the finish
  fixes: network/timeout feedback, Retry-After guidance, trusted validation
  fragments, unrelated forms, local success focus, and intentional error focus.
  Five Django rendered-form tests also passed after these changes. The event
  tests do not emulate a browser; actual browser evidence is recorded below.
- Migration parity, Django checks, `check --deploy --fail-level WARNING` with
  synthetic production configuration, compressed manifest static collection,
  Python compilation, and JavaScript syntax passed. `git diff --check` passes
  for all changed paths except frozen `ml/data/triage-corpus.json`, which
  intentionally retains one EOF blank line to preserve its published SHA256.
- Independent backend review: normalized-length validation was fixed and covered
  by regression tests. Expiry is checked after the run lock is acquired.
- Independent UI-source review: hidden key errors, silent network failures, and
  unhelpful throttle responses were fixed. Follow-up found no remaining P1/P2
  issues in reviewed sources; this is not visual/accessibility sign-off.
- Independent ML review found no concrete P1/P2 defects in the contract, split
  integrity, evidence fingerprints, metrics, or invalid-artifact handling.
- A final adversarial pass confirmed a P2 session-revocation disclosure: lazy
  authentication was evaluated only after run lookup on a direct GET. New real
  Client regressions reproduced HTTP 200 before the fix for full and HTMX GETs.
  Resolving authentication before reading the session secret fixed the ordering;
  six invalidated-session GET/POST cases and anonymous-owner access now pass.
  Source follow-up reports no remaining P1/P2 findings. This pass reviewed tests
  and JSON fixtures in summary mode rather than inspecting their raw payloads.
- The user's pre-existing portfolio date/employment edits remain unchanged.
- A final rerun exposed a pre-existing clock-sensitive chat throttle assertion.
  A controlled reproduction passed with all 41 requests in one minute and failed
  when request 41 entered the next fixed window (302 instead of expected 429).
  The test now fixes its clock, checks `Retry-After`, then explicitly advances a
  minute and verifies recovery. Production rate-limit code is unchanged. The
  targeted test and the complete suite above passed after this test-only fix.
- `pip-audit -r requirements-production.txt --vulnerability-service=osv` completed
  with no known vulnerabilities in the resolved production dependencies.
- The six exactly pinned offline-training packages also passed `pip-audit`
  with `--no-deps --disable-pip`; no known vulnerabilities were reported.
- Gitleaks 8.30.1, verified against its official download checksum, reported no
  findings in the full fetched `main` history at `37e29d2` (60 reachable commits;
  54 commits with scanned diffs) or the 290-file tracked/unignored source snapshot.
  Scans used full redaction and did not honor inline allow comments. The isolated
  source snapshot excludes private ignored files. Both corrected commands exited
  zero; an earlier malformed PowerShell invocation was discarded as invalid-scope
  evidence. Redacted reports remain under ignored `.gstack/security-scan-*`.
- A subsequent staged-release scan covered approximately 616,811 bytes with full
  redaction and found no leaks. CI must still scan the final published history.
- `.gitattributes` pins hashed model/data JSON to LF. A fresh index export with
  `core.autocrlf=true` retained all five inspected frozen-file SHA256 hashes,
  including the corpus and runtime artifact; model contents were not retuned.
- Impeccable detector ran on the new templates/styles. Its one thick-top-border
  warning was fixed. Django static template tags prevented complete stylesheet
  resolution, so its color/custom-property checks were incomplete.
- Real headless Microsoft Edge checks passed after the user authorized the
  fallback. The no-JavaScript walkthrough, keyboard entry/submission, explicit
  delivery/recovery/replay, cross-browser ownership, error/loading states,
  reduced motion, and four viewport widths were exercised. Axe-core 4.13.0
  reported zero violations in checked states. See
  `docs/engineering-browser-verification.md` for exact coverage and limitations.
- The independent Impeccable verdict scored all three finish corrections
  **resolved**, with disposition **ship at that fix-list scope**. It does not
  certify the entire application or production release. The documentation
  handoff recorded source-backed inheritance in the two surface records without
  changing global design authority or the legacy `PRODUCT.md` metadata.

## Model evidence

- 360 LLM-authored synthetic examples, 90 scenario groups; group-disjoint
  train/validation/test counts 216/72/72. Another 24 challenges are separate.
- Frozen validation threshold 0.45. No tuning followed held-out evaluation.
- Held-out macro-F1 **0.917729**, accepted precision **0.940299** (63/67),
  coverage **0.930556** (67/72). All requested offline promotion targets passed.
- JSON artifact 256,961 bytes, 2,740 features; numerical parity maximum absolute
  error 4.44e-16. App inference uses no NumPy/scikit-learn/SciPy installation.
- Important limitation: three of seven accepted ambiguous challenges were wrong.
  These synthetic-data metrics are not real-world accuracy or calibrated confidence.
- The Colab notebook is structurally valid; its training path ran in a Linux CPU
  container. Actual Colab execution was unavailable and is not claimed.

See `ml/evaluation-v1.json`, `ml/frozen-v1.json`, and `ml/README.md`.

## Performance evidence and limits

- Two 500-call warm, complete `classify()` benchmarks on Windows/Python 3.12.4
  measured p95 9.9424 ms and 4.7502 ms. Both are below 50 ms. Cache/file-stat,
  inference, abstention, and result construction are included; first model load,
  Django, and network are excluded. Observed maximum spikes are retained in
  `ml/runtime-benchmarks-v1.json`. This is not a PythonAnywhere latency guarantee.
- A separate Linux/Python 3.12.14 CPU-container core-inference-plus-abstention
  benchmark measured p95 2.6315 ms over 500 calls. Its narrower scope is recorded
  in the evaluation report, not conflated with complete API latency.
- Production-rendered overview HTML was 13,915 bytes / 4,900 bytes gzipped.
  Its two stylesheets, two scripts, and favicon total 24,765 estimated compressed
  bytes: **29,665 bytes overall**. This is a local gzip source-size calculation,
  not a measured cold browser transfer. No new raster or font downloads are added.
- A subsequent actual cache-disabled browser measurement recorded **101,837
  bytes** for the local lab overview and **97,186 bytes** for the local homepage.
  Both meet their transfer budgets even on the development server. These are
  not production measurements and do not establish a production LCP guarantee.

## Environment failures and pending checks

- Several newly written files became entirely NUL bytes. Restored files passed
  subsequent tests; the final changed-text audit found zero NUL bytes across 63 paths.
  Final audits must remain clean. The initial failed run is not a passing result.
- The in-app Browser/Node runtime fails during startup with a Windows sandbox
  ACL error or "trusted Node process exited unexpectedly". Retried after the
  user's request, including an explicit JavaScript-kernel reset; the final error
  still reports `apply deny-read ACLs`. The standalone gstack browser also failed
  to start. Direct Playwright successfully drove the installed headless Edge
  after the user's explicit approval; no personal cookies were imported.
- Responsive, keyboard, reduced-motion, automated accessibility, no-JavaScript,
  and actual transfer checks are now complete at the documented scope. The zoom
  check used 200%-equivalent reflow rather than native browser-menu zoom. No
  screen-reader session was performed. Actual screenshots support the review.
- The disposable MySQL run passed after all migrations applied successfully.
  To reduce this VM's severe fsync overhead, test-only
  `innodb_flush_log_at_trx_commit=1` / `sync_binlog=1` were temporarily set to 2 / 0.
  Defaults 1 / 1 were restored and verified after tests. This verifies transaction
  visibility, locks, rollback, and uniqueness, not machine power-loss durability.
  CI retains normal durability; production database settings were not changed.
- The initial Gitleaks download was blocked by a GitHub TLS timeout. On the
  subsequent continuation the download, checksum verification, full fetched-main
  history scan, and source-snapshot scan succeeded. CI must still scan the final
  published commit; the local result does not cover other unpublished branches.
- Refreshing the local review base failed with a bad object at
  `refs/codex/turn-diffs/captures/1789398906922/953a33f5-a921-4cea-aab3-4dbc6aa25a97/base`.
  The remote is reachable and `main`
  resolves to `37e29d2b515b362f69ba5f81971019f4fea24d68`, but this checkout cannot
  complete the fetch. No Git metadata was deleted or repaired. A separate,
  disposable bare clone of remote main subsequently succeeded: its complete
  tree exactly matches local pre-feature HEAD `b741c9f`. That equality verifies
  the reviewed baseline against current remote main without trusting stale refs.
  Use a clean working checkout for the eventual release.
- The optional outside Claude reviewer is unavailable locally. Native independent
  reviews are recorded separately; missing outside coverage is not a clean pass.

## Remaining release gates

1. Use a clean release checkout, then run CI, including the expanded MySQL suite
   and a full-history secret scan of the published commit. Publish source links
   only after the reviewed branch/release exists remotely.
2. Verified production backups, immutable release, additive migration, feature
   enablement, reload, and live smoke tests using the established deployment
   process. Recheck browser transfer and inference latency on PythonAnywhere.

Native browser-menu zoom and assistive technology checks remain explicitly
outside the automated evidence; 200%-equivalent reflow was exercised.
