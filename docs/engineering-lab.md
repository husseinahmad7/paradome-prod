# ParaDome Engineering Lab

The lab is an isolated, request-driven architecture demonstration for platform
and backend recruiters. It does not change ParaDome's live chat transport.
Enable it with `ENGINEERING_LAB_ENABLED=true`; the default is **false**.
The portfolio and Dome-shell links are conditional on the same flag.

## Walkthrough

1. Open `/engineering/` and start a run (POST, no additional login).
2. Submit the example text. The source transaction creates a submission and
   its one-to-one outbox event. The saved ML suggestion cannot affect permissions.
3. Choose **Lost acknowledgement**, then press **Attempt delivery**.
   The destination now has a receipt, while the source is ready to retry.
4. Choose **Deliver / recover**, then press **Attempt delivery** again.
   The receipt stays the same; the source acknowledgement is recorded.
5. Press **Replay this submission**. The original submission and event come back.
6. To inspect a conflict, submit different text with the saved request key.
   The server returns HTTP 409 without changing the original operation.

The ordinary HTML forms implement the entire flow. HTMX is an optional partial
replacement, never a prerequisite. There is no polling or autonomous worker.
This fits PythonAnywhere's current [free-account limits](https://help.pythonanywhere.com/pages/FreeAccountsFeatures/):
only grandfathered accounts retain a daily task, and [always-on workers](https://help.pythonanywhere.com/pages/AlwaysOnTasks/)
require a paid account. The lab reuses the existing daily maintenance command.

## Boundaries and invariants

| Boundary | Implementation | Evidence |
| --- | --- | --- |
| Session ownership | Random session secret; HMAC hash on the run, no user foreign key | `engineering.services.owner_hash`, cross-session tests |
| Source commit | Submission and outbox event in one transaction, unique run/key | `engineering.services.submit`, rollback and conflicting-replay tests |
| Destination commit | One receipt is the inbox effect; separate transaction from source ack | `commit_receipt`, lost-ack tests |
| Duplicate prevention | Database one-to-one event/receipt | duplicate and simultaneous-attempt tests |
| Lease fencing | 15-second claim with token and expiry checks at sink and completion | expired-claim replacement tests |
| Policy reuse | Pure facts/decision evaluator drives object checks; query policy remains equivalent | `Domes.access`, `engineering.test_permissions` |
| Model boundary | Non-executable JSON, bounded validation, standard-library inference | `engineering.triage`, golden-vector and corruption tests |

Every service locks the run before its event. This intentionally serializes the
small run, making caps and trace trimming race-safe. It is not a throughput
benchmark. No lab model refers to posts, live channels, media, or real users, and
no lab request can select a transport URL. The destination is an internal adapter,
not a distributed service; this demonstrates idempotent effects, not a universal
exactly-once delivery guarantee.

Runs expire after at most 24 hours. Existing authentication deadlines are not
extended when adding the owner secret. Logout flushes the secret; a UUID alone
cannot recover access. Starting three active runs reaches the per-browser cap.
Each run allows ten submissions, five attempts per event, and eighty trace rows.
IP-based database rate limits apply even to shared demo identities.

Trace durations use `perf_counter()` for individual stages up to the trace write;
they exclude the eventual transaction commit and network latency. The run's wall
age is separately labelled and includes time between manual clicks. Traces contain
fixed high-level explanations, never SQL, raw exceptions, or credentials.

## Maintenance and rollback

`cleanup_engineering_runs --batch-size 100 --max-batches 5` deletes only expired
lab runs and their dependent records. Bounds are validated (maximum 500 roots per
batch, twenty batches). The existing daily `reset_demo_sandbox` command also calls
bounded cleanup; do not replace or add PythonAnywhere scheduled tasks for the lab.
Cleanup remains available while the feature flag is off.

Use the existing verified backup and immutable-release process in `DEPLOYMENT.md`:

1. Back up MySQL, media, repository state, WSGI, environment, and task configuration.
2. Install a fresh Python 3.12 release with the flag off. No training dependency is
   added to production requirements. Include the checked-in JSON model artifact.
3. Apply additive migrations, run deployment checks, and collect static files.
4. Complete MySQL race tests, independent review, browser/accessibility verification,
   and performance measurements before enabling the flag and reloading the site.
5. Verify anonymous and shared-demo browser isolation, all three delivery scenarios,
   replay/conflict behavior, policy results, and classifier fallback.

Rollback: set `ENGINEERING_LAB_ENABLED=false` in the protected external environment,
reload, and restore the previous release if needed. Retain the additive lab tables;
do not roll back the database or delete unrelated product data for a lab-only issue.
Use the pre-release database/media snapshots only if the established rollback
assessment calls for them. Source evidence links must resolve to the released code.

## Verification

Run `python manage.py test --settings=paradome.settings.test` for the isolated SQLite
suite and `--settings=paradome.settings.ci` with the existing disposable MySQL 8.4
service for concurrency proof. SQLite deliberately skips the MySQL-only race cases.
`makemigrations --check --dry-run`, `check --deploy`, static collection, dependency
auditing, and history secret scanning remain release gates in CI.
Run `node --test engineering/test_lab_js.cjs` for the small progressive-enhancement
event contracts and `python ml/benchmark_runtime.py` for reproducible warm latency.

See `ml/README.md` for two-phase training/validation freeze and holdout evaluation.
If held-out results guide a new model version, author a fresh untouched holdout.
Never claim a model score is calibrated confidence or a synthetic dataset result
is a production-traffic evaluation.

Browser checks: JavaScript off, keyboard only, 200% zoom, reduced motion, and
320/390/768/1440-pixel layouts. Measure cold total page transfer (<300 KB compressed)
and warm inference p95 (<50 ms), while retaining the homepage budget. Server-side
form tests and compressed source-size calculations are not substitutes for a real
browser accessibility, responsive, or network measurement.
