# Frozen search evidence v1

This English retrieval experiment uses 120 fictional technical discussions and
180 AI-authored, relevance-labelled queries. It is a portfolio demonstration;
there is no independent human label review or production traffic in this report.

The v1 corpus, queries, and document index are byte-addressed artifacts. Git
attributes preserve their original line endings on every platform so their
frozen SHA-256 digests match on Windows and Linux. This portability correction
does not change any JSON values, rankings, fitted confidence, or test results.

## Result and release decision

The first frozen test failed the semantic-default gate. Recall@5 is **0.71875**,
below the required **0.85**. Paraphrase Recall@5 is **0.625**, above BM25's
**0.541667**. Keyword search therefore remains the default. Visitors can opt into
an explicitly labelled experiment and inspect its abstentions and failures.

The top-result confidence model achieved test acceptance precision **0.791667**,
coverage **0.666667**, expected calibration error **0.146825**, and Brier score
**0.130826**. All four no-answer test queries were rejected; that small count
cannot establish reliable production abstention. Similarity is displayed
separately from the estimated probability of top-result relevance. Supporting
results have no calibrated confidence. The older triage score keeps its existing
labelling and is unrelated to this confidence model.

## Provenance and split discipline

`author_corpus.py` records fictional authoring provenance. Sixty intent groups
each have two discussions and three queries: literal wording, a paraphrase, and
either a distractor or a question outside the corpus. Pairwise relevance grades
are 2 for the primary discussion and 1 for its supporting discussion. Sparse
judgements can count a useful cross-topic discussion as irrelevant.

Group hashes assigned 36 development, 12 calibration, and 12 test groups before
encoding. Related rewrites stay together. `frozen-v1.json` records the split,
corpus, labels, and preregistered release policy. Development fits a regularized
two-feature logistic calibrator using top cosine similarity and the first/second
margin. Calibration chooses the highest-F1 threshold subject to precision >= 0.90
and coverage >= 0.50, breaking ties with the higher threshold. If no threshold
qualifies, reject all. The selected threshold is 0.493.

The untouched test was evaluated once after policy freeze. Its results are now
public. Do not edit its corpus, labels, calibrator, or threshold to improve these
numbers. Any revision informed by these failures needs a new version and fresh
holdout. Verification reruns use the frozen calibrator without fitting it again.

Recall@5 measures the fraction of the two labelled relevant documents retrieved.
nDCG@5 uses graded relevance. Ranking averages exclude queries with no relevant
answer. Metrics score raw cosine rankings before confidence abstention; coverage,
acceptance precision, and no-answer rejection are reported separately. BM25 uses
the same title/body corpus, k1=1.2, b=0.75, and the documented English stopwords.
See `evaluation-v1.json` for slices, competing IDs, predictions, and failures.

## Exact encoder and assets

Model: `Xenova/all-MiniLM-L6-v2`, immutable revision
`751bff37182d3f1213fa05d7196b954e230abad9`, `model_quantized.onnx`, q8,
384-dimensional mean pooling with L2 normalization. Transformers.js is pinned to
4.3.1, with all transitive dependencies pinned in `package-lock.json`.

The browser Web Worker uses the same ONNX model and tokenizer as offline Node CPU
encoding, with WASM inference and one thread. An explicit `BertTokenizer` built
from the hash-checked tokenizer JSON and `AutoModel` avoid v4 discovery skipping
HTTP-local tokenizer metadata when remote models are disabled. A warm-up
inference must succeed before the model is ready.
The model is about 23 MB; the complete self-hosted worker/runtime/model bundle is
about 53 MB. Nothing downloads until a visitor opens Search with semantic retrieval
enabled. HTTP and browser caches reuse assets. No Hugging Face or CDN requests
occur at inference time. `assets-lock-v1.json` binds every asset to its SHA-256.

```sh
npm ci
npm run search:assets
npm run search:encode
python ml/search/evaluate.py --verify
npm test
```

The checked-in corpus, index, calibration, goldens, and report suffice for Django
keyword/cosine ranking. The larger runtime assets and intermediate encodings are
ignored and rebuilt from the pinned sources. The builder refuses changed asset
digests. `--refresh-worker` is a deliberate source-only rebuild: it requires every
model/tokenizer/runtime digest to stay unchanged. Update the golden manifest's
worker digest together, without refitting or changing the frozen report.

The worker imports the official pinned Transformers.js distribution, assembled
at build time rather than committed as generated third-party code. The Wasmer
Python builder verifies the same nine asset hashes without requiring Node on
the deployment host. Runtime requests use only this site's asset endpoint.

The first evaluation invocation without `--verify` creates artifacts and refuses
to overwrite an existing frozen report. Do not delete v1's report to refit it.
Create a distinct version and fresh holdout for a new experiment.

Open **Architecture -> Browser worker -> Check embedding agreement** in the real
browser after loading the model. Three public golden vectors compare Node CPU
against browser WASM with maximum absolute error <= 0.01, cosine >= 0.999, and
identical top answers and top-five result sets. The first stricter 0.001 component
check passed two of three sentences. The measured maximum difference was
0.004814 and minimum cosine 0.999484; all top answers and all fifteen top-five
members agreed. The numerical contract records this CPU/WASM rounding allowance;
the frozen retrieval evaluation and acceptance policy were not revised.
`verify-browser.mjs` exposes the same numerical comparator to external evidence
collection; it does not launch a browser or imply that a browser check passed.

## Privacy, monitoring, and timing

Django accepts text and an optional versioned vector, validates dimensions and
finite values, and processes them in memory. It stores only numeric metadata,
fallback reason codes, and public result IDs. A root row lock keeps the newest 40
observations per session-owned run. Runs expire after 24 hours. CSRF protection,
shared rate limiting, and ownership checks apply before retrieval.

Metrics show this visitor's actual retained observations, score bins, low-confidence
rate, reason counts, and artifact/version health. Delivery counters come from the
existing durable source/outbox/receipt records. Duplicate/replay totals are bounded
by the newest 80 trace stages; they are not lifetime global counters.

Frozen latency is offline host evidence. Live server ranking, browser inference,
browser loading including warm-up, and request round trip are separate. Browser
timings are client-reported. Parent-page and worker Resource Timing report initial
transfer separately from lazy asset transfer; cache hits can transfer zero bytes.
Never interpret local or frozen latency as measured Wasmer performance.
