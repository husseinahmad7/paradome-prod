# English technical-discussion triage

Offline training tools for the Engineering Lab. The deployed application imports
only Python's standard library and a plain JSON model. It never loads pickle,
downloads models, calls a remote inference service, or requires a GPU. Training
dependencies do not belong in the production virtual environment.

## Scope and evidence

The task has three labels: **bug report**, **idea**, and **question**. An observed
malfunction takes precedence; otherwise a proposed capability is an idea;
otherwise a request for guidance is a question. A question mark alone does not
determine the label.

The corpus contains **360 LLM-authored synthetic English discussions** in **90
scenario groups**, with four paraphrases per group. These are not production
messages or independently human-annotated examples. The public data file records
provenance and split assignments. No personal data or external corpus was used.

- Training: 216 examples / 54 groups.
- Validation: 72 examples / 18 groups.
- Test: 72 examples / 18 groups.
- Separate challenges: 24 ambiguous, unfamiliar, and unsupported-script examples.

Group assignment was fixed before fitting: within each ordered block of 30
class-specific scenarios, indices modulo five of 0–2 are training, 3 validation,
and 4 test. All paraphrases stay together. Topic groups differ, but a common
authoring style still makes this a small synthetic benchmark; its scores must not
be represented as real-world production accuracy.

The checked-in `evaluation-v1.json` contains the actual held-out scores,
per-class precision/recall/F1/support/coverage, baseline, challenge outcomes,
artifact fingerprint, parity error, and measured local latency. The application
model card reads the same evidence embedded in the artifact. Test macro-F1
includes **every** held-out row, including rows where the deployed model would
abstain. Accepted precision is **correct accepted predictions / all accepted
predictions**; coverage is **accepted / all held-out examples**. Per-class
coverage is accepted rows whose true label is that class / all rows of that class.

Promotion requires macro-F1 ≥ 0.80, accepted precision ≥ 0.85, and coverage ≥ 0.50.
A failed target is reported, never repaired by tuning against the same holdout.
The baseline predicts the training-majority class; the balanced counts tie, so the
lexically first label is the fixed tie-break. It is a deliberately modest baseline,
not evidence of superiority to language models or human triage.

## Reproduce the published model

### Measured v1 result

The 72-row held-out test yielded macro-F1 **0.9177** (majority baseline
**0.1667**), accepted precision **0.9403** (63/67), and coverage **0.9306**
(67/72). All three promotion targets passed at the validation-frozen threshold
**0.45**. The artifact is **256,961 bytes** with **2,740 features**; maximum
numeric parity error was **4.44e-16**. A separate 500-call warm CPU benchmark
measured p95 **2.6315 ms**, excluding artifact loading, Django, and the network.
These are synthetic-benchmark and local-runtime results, not production claims.

| True class | Raw precision | Raw recall | Raw F1 | Accepted precision | Coverage |
|---|---:|---:|---:|---:|---:|
| Bug report | 0.8462 | 0.9167 | 0.8800 | 0.8750 | 0.9167 |
| Idea | 0.9167 | 0.9167 | 0.9167 | 0.9545 | 0.9583 |
| Question | 1.0000 | 0.9167 | 0.9565 | 1.0000 | 0.9167 |

The separate ambiguity challenges are a useful warning: **three of seven
accepted mixed-intent examples were wrong**, and one additional example
abstained. All eight unsupported-script examples abstained. Four of eight
unfamiliar examples were accepted (all four correct here), which is far too small
to establish out-of-domain reliability. These findings did not change v1.

### Environment and commands

Use Python 3.12 and a separate development environment. A CPU is sufficient.

```console
python -m venv .gstack/ml-venv
# Activate the environment, then:
python -m pip install -r ml/requirements-training.txt
python ml/train_triage.py --phase reproduce
python -m unittest engineering.test_triage -v
python ml/benchmark_runtime.py
```

`triage_colab.ipynb` performs the same steps in a CPU Colab runtime after the lab
revision is available in the public repository. No Colab account or training
library is needed by a visitor or the deployed Django process.

The reproduce phase refits on training only, selects the threshold on validation
only, checks parameters/vocabulary against the existing artifact, and checks
held-out metrics against the frozen report. It does not rewrite artifacts.
Cross-platform floating-point results are compared within 1e-6.

## Two-phase release procedure

The initial v1 run used two separate invocations:

```console
python ml/train_triage.py --phase train
python ml/train_triage.py --phase evaluate
```

The train phase fits TF-IDF and logistic regression only on training groups. It
writes a frozen candidate to the ignored `.gstack/ml-training/` directory and a
public `frozen-v1.json` manifest **before** evaluation. Vocabulary size, logistic
regression hyperparameters, minimum vocabulary evidence, and threshold candidates
are in `CONFIG`, fixed before testing. Among validation thresholds meeting
accepted precision ≥ 0.85, choose greatest coverage, then greatest precision,
then the smaller threshold for an exact tie. If none meets the floor, use 1.0
(effectively abstaining), and report the failed promotion.

The evaluate phase verifies the corpus/configuration fingerprint and threshold
against the frozen manifest, then opens test predictions once. It produces:

- `engineering/ml_artifacts/triage-v1.json`: bounded, non-executable parameters
  and compact model evidence.
- `engineering/ml_artifacts/golden-v1.json`: scikit-learn probabilities/logits
  for all test examples plus preprocessing edge cases.
- `ml/evaluation-v1.json`: complete held-out report and separate challenges.

A completed evaluation prevents another train/evaluate run from silently
replacing v1. Use reproduce to verify it. If a finding influences a new version,
author and freeze a **new untouched scenario-group holdout**, update versioned
paths and data provenance, then repeat the two-phase procedure. Do not delete the
v1 report and recycle its holdout. Generated JSON is flushed, synced, and
read-verified before the command reports success.

## Frozen inference contract

1. Unicode NFKC normalization, followed by Python Unicode lowercase.
2. Tokens match `(?u)\b\w\w+\b`: word-character tokens of at least two
   characters. Punctuation separates tokens; accents are not stripped.
3. Word unigrams and adjacent word bigrams, with raw term counts; no stop-word
   list, binary counts, or sublinear TF.
4. Smoothed IDF fitted on training documents only:
   `log((1 + training_document_count) / (1 + document_frequency)) + 1`.
5. L2 normalization of the complete nonzero TF-IDF vector.
6. Ordered labels `["bug report", "idea", "question"]`; one coefficient vector
   and one intercept for each class.
7. Class logits are intercept plus the dot product. Stable softmax subtracts
   the maximum logit before exponentiation. The largest score wins.

The exported vocabulary is capped at 5,000 features (v1 configuration allows
4,000), and the JSON is capped at 1 MiB. Runtime validation checks the contract,
label order, shapes, uniqueness, finite numeric values, and byte budget. There
are no executable objects or external references in the model.

All nonzero feature contributions plus the winning intercept reconstruct its
logit. The UI shows at most six contributions ranked by absolute magnitude;
**positive supports, negative opposes**. They explain the linear score, not
causal importance or a probability decomposition. Displayed terms alone omit
the remaining smaller contributions.

## Abstention and limitations

Runtime abstains if any letter is outside the Latin script, fewer than three
distinct recognized words occur, recognized distinct words cover less than 25%
of input distinct words, or the maximum score is below the frozen threshold.
The script guard runs after normalization, so full-width Latin letters normalize
normally. It deliberately is **not language detection**: unfamiliar English,
other Latin-script languages, code, negation, and mixed intents can still receive
confidently wrong predictions.

Scores are uncalibrated softmax outputs, not a promised probability of correctness.
Do not treat this classifier as moderation, security, diagnosis, or automation.
Suggestions never alter authorization or delivery and do not address real posts.
Missing, corrupt, oversized, or incompatible artifacts mark triage unavailable;
the lab's submission and delivery flow remains usable.

Challenge outcomes are diagnostic, not threshold-selection data or promotion
metrics. In particular, publishing a failure on unfamiliar English is more useful
than implying that vocabulary coverage detects every out-of-domain request.

## Runtime API and tests

`engineering.triage.classify(text)` returns `status`, `label`, `score`, `terms`,
`version`, `latency_ms`, `reason`, and a safe human-readable `explanation`.
Status is suggested, uncertain, or unavailable. Uncertain/unavailable never
return a selected label. Inputs are bounded to 1,500 characters.

`model_card()` returns artifact metadata, dataset/test evidence, and limitations.
The application loads the artifact lazily and revalidates a changed file.
No model loading happens at import time; a missing file cannot prevent startup.

`engineering/test_triage.py` runs without NumPy or scikit-learn. It checks golden
prediction parity within 1e-6, contributions, normalization/TF-IDF, provenance
and split integrity, threshold freeze, recomputed metrics, unsupported scripts,
low vocabulary, corrupt-artifact fallback, and the artifact fingerprint.
The offline script separately compares sparse features, logits, and softmax
probabilities with scikit-learn.

Latency in the report is measured over 500 warm local inference+abstention calls;
its recorded platform and scope are part of the evidence. It excludes model
loading, Django, and network time and is not a PythonAnywhere latency guarantee.
The separate standard-library benchmark measures the entire warm classify API,
including the artifact file-stat/cache lookup and result construction. It prints
the machine, sample count, p50/p95/maximum, and whether training libraries are
installed; run it on the deployment host for host-specific evidence.

## References

- [scikit-learn text feature extraction](https://scikit-learn.org/stable/modules/feature_extraction.html)
- [TF-IDF vectorizer contract](https://scikit-learn.org/stable/modules/generated/sklearn.feature_extraction.text.TfidfVectorizer.html)
- [Logistic regression](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.LogisticRegression.html)
