# Control room verification — 2026-10-10

Release status: **draft; browser visual verification and Wasmer release blocked**.
The implementation is on `hussein/portfolio-control-room`, starting at main
`c92e9db89ef7f41369e2168b875d00fb393ed119`. The original dirty checkout was
preserved in a separate working tree.

## Verified implementation and automated checks

[CI run 38050134719](https://github.com/husseinahmad7/paradome-prod/actions/runs/38050134719)
tested commit `8f6fb959f5f6c44f78749c83258c1554c7e26a91`:

- MySQL 8.4: **252 tests passed, no skips**, including concurrent delivery,
  per-owner caps, session isolation, newest-forty search telemetry, and maintenance.
- **14 JavaScript tests passed** for delivery recovery and control-room contracts.
- Model drift checks, production settings, MySQL migrations, compressed static
  collection, pinned asset verification, dependency audit, and full-history
  secret scan passed.
- Local SQLite: 252 tests passed with 11 MySQL-only skips. After the portability
  and streamed-response correction, all 18 search tests and the additional asset
  GET/HEAD/304 checks passed locally; full MySQL CI exercised the final code.

Frozen byte-addressed corpus/query/index files now retain their originally
evaluated line endings through Git. Staged and working SHA-256 digests match;
JSON values are unchanged. `evaluate.py --verify` reproduces the frozen report
and confidence policy without refitting. The streamed-response test consumes
Django's test-client iterator; directly closing the response had incorrectly
closed MySQL inside the test transaction.

## Real in-app Browser evidence

The isolated local QA server used independent seeded data and local verification
controls. Browser actions were performed through Codex's in-app Browser.

- Search a development paraphrase, inspect a relevant discussion, and explicitly
  use its content in Delivery.
- Submit once, lose the first acknowledgement, recover successfully, then replay
  the original request. The run contained **one source submission, one inbox
  receipt, two delivery attempts, one prevented duplicate, and one replay**.
- Keyboard activation exercised submission, recovery, replay, and the controlled
  outage switch. The outage search displayed “Simulated model outage. These are
  keyword results.” and ranked BM25 results without a browser embedding.
- Browser WASM and offline Node CPU used the same hash-locked quantized ONNX and
  tokenizer. All three public numerical goldens passed the documented agreement
  contract: max component difference 0.004814, minimum cosine 0.999484, identical
  top answers and all fifteen top-five members. See the
  [numerical tolerance and initial stricter trial](../ml/search/README.md).
- Axe 4.14.0 initially reported one serious accessible-name mismatch in the
  incumbent notification close control. Changing its name to “Close notification”
  resolved it. The rerun reported **31 passing rules and zero violations** on the
  loaded control room. This is an automated audit of that state.
- A local QA button successfully applied the reduced-motion CSS branch. It did
  not change or emulate the browser/OS preference.

The model is approximately 23 MB; the complete nine-file worker/runtime/model
bundle is **52,674,666 bytes**. Local Browser Resource Timing separately reported
initial transfer and lazy worker/model/runtime requests. One warm-cache trial
reported 28.7 KiB initial transfer, 576.5 KiB lazy worker script, and 27,688.7 KiB
worker model/runtime requests. These are local QA observations with cache and
verification-harness overhead, not a cold production transfer claim.

## Frozen ML result

The 120 fictional discussions and 180 AI-authored labelled queries have recorded
provenance and grouped development/calibration/test splits. Held-out Recall@5 is
**0.71875**, below the required **0.85**. Paraphrase Recall@5 is **0.625** against
BM25's **0.541667**. Keyword remains the default; semantic search is explicitly
experimental. Similarity and estimated relevance confidence are separate.
Calibration error, coverage, latency, competing results, and failure examples
are published in the [frozen report](../ml/search/evaluation-v1.json).
Any new experiment informed by these test failures needs a distinct version and
fresh holdout. v1 has not been retuned.

## Remaining verification

The in-app Browser intermittently timed out on frame/input commands. Read-only
DOM inspection and native keyboard/AX controls recovered for functional checks,
but `Page.captureScreenshot` timed out. The requested 1440×900 override still
reported 1280×720. Connected Edge failed to load its browser request policy and
later timed out while listing tabs. A fresh in-app tab also failed screenshot
capture. No valid final screenshot matrix was saved.

The independent Impeccable finish reviewer returned **`recapture`** because the
desktop, mobile, and requested four-width captures were missing. It issued no
visual approval or ship verdict. Temporary viewport and visibility overrides
were reset; the local preview tab is retained for verification after reconnection.

Still required before release:

- Actual 320/390/768/1440 px reflow and full-page captures; independent visual
  finish review of those captures.
- Complete workflow with browser JavaScript disabled, actual reduced-motion
  preference, and connected Edge; the server/form tests and forced CSS branch
  do not complete these browser checks.
- Final production transfer measurement, with a cold model download measured
  separately from the initial page.
- Full Wasmer runtime and release gates in [the deployment record](wasmer-deployment.md).

The Impeccable detector ran once on changed CSS/JS/templates. Its one remaining
`flat-type-hierarchy` warning concerns the incumbent portfolio template. It also
reported that Django `{% static %}` stylesheet links could not be resolved, so
its inferred 16px heading sizes are incomplete evidence. No extra typography
change or second detector pass was made from that warning alone.
