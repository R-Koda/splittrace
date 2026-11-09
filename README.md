# SplitTrace — trace data leakage back to its source

[![Tests](https://github.com/R-Koda/splittrace/actions/workflows/tests.yml/badge.svg)](https://github.com/R-Koda/splittrace/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**Experimental Python library for auditing existing EEG and sensor-data splits.**

Audit existing train/validation/test assignments for EEG and sensor experiments.
Trace derived examples back through declared parent IDs, inspect intervals in
original-recording coordinates, and return evidence for each violation.

Different filenames and different pixel values can still come from the same
source epoch. SplitTrace accepts declared parent relationships and reports the
path that connects a training example to an evaluation example:

```text
train: a → image-01 → epoch-01 ← b :test
                     ^ shared source example
```

It also checks subject mixing, overlapping source intervals and, under an explicit
policy, chronological ordering. Missing metadata is **UNKNOWN**, not a clean bill
of health. All bundled examples are synthetic; no patient data is included.

**Early prototype:** small manifests only, with no real-user validation yet.
Not published to PyPI. Install from this repository; do not assume that a package
named `splittrace` on a registry is this project.

日本語の試用手順は [PILOT.md](PILOT.md)。実行済みの比較結果は
[results/comparison.html](results/comparison.html)、派生元追跡の出力例は
[results/derived-audit.html](results/derived-audit.html) を開いてください。

## Article & live demo / 紹介記事と公開デモ

- [紹介記事：データを分ける・評価する・公開する。Pythonの小さな確認ツールを3つ作りました](https://ryu-koda.com/blog/python-tools-splittrace-eventscore-notebook/) — Japanese overview of SplitTrace, EventScore Explorer, and Notebook Publish Check.
- [公開デモをブラウザで開く / Open the live demo](https://ryu-koda.com/articles/python-tools/splittrace-demo.html) — Synthetic data only; no installation required.

公開デモは合成データの出力例です。自分のファイルをアップロードする画面ではありません。
The hosted demo is a sample report, not a file-upload service.

## Run without installing anything

Python 3.10+; the core and CLI use only the standard library.

```sh
git clone https://github.com/R-Koda/splittrace.git
cd splittrace
```

From the repository directory:

```sh
PYTHONPATH=src python3 -m splittrace.cli \
  examples/derived-samples.json examples/derived-assignments.json \
  --policy cross_subject --lineage-complete \
  --output results/local-audit.json --html results/local-audit.html
```

This intentionally leaking example exits **1**; that is the expected result,
not an installation error. The report contains the paths
`a → image-01 → epoch-01` and `b → epoch-01`. No signal values are read.
CLI exit codes: `0` = all applicable checks PASS; `1` = a declared policy violation;
`2` = UNKNOWN coverage or invalid input (inspect `status` to distinguish them).

For an editable install in your own virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/splittrace --help
```

## Python API

```python
from splittrace import audit, map_interval

samples = [
    {"sample_id": "epoch-01"},
    {"sample_id": "image-01", "parent_ids": ["epoch-01"]},
    {"sample_id": "a", "parent_ids": ["image-01"]},
    {"sample_id": "b", "parent_ids": ["epoch-01"]},
]
assignments = [
    {"sample_id": "a", "split": "train", "fold": "0"},
    {"sample_id": "b", "split": "test", "fold": "0"},
]
report = audit(samples, assignments, policy="cross_subject", lineage_complete=True)
assert report["status"] == "FAIL"
# Other checks remain UNKNOWN when their required metadata is absent.

# Convert a local, resampled interval to original sample coordinates explicitly:
start, end = map_interval(0, 128, origin_offset=256, original_units_per_local_unit=2)
assert (start, end) == (256, 512)
```

## Data contract

Samples are dictionaries / JSON objects. CSV is also accepted; its `parent_ids`
cell must be a JSON array, quoted following normal CSV rules. Blank optional CSV
cells are missing metadata. Numeric interval cells are parsed as floats.

- `sample_id`: nonempty, globally unique string. Reference nodes may exist without
  assignment to a split. Parent references must resolve; cycles are rejected.
- `parent_ids`: list of directly contributing source-example IDs. Declare all
  parents for mixtures. Examples sharing a sample ancestor are flagged across
  partitions. This is a conservative **source-example separation policy**, not a
  statistical proof that all shared ancestry invalidates every evaluation.
- `kind`: `sample` (default) or `recording`. A whole raw recording used as a graph
  parent should be `recording`; merely sharing that parent does not fail lineage.
  Interval or subject checks still apply. Do not label an actual shared training
  example as a recording to bypass the check.
- `subject_id`: canonical ID; namespace IDs that are only unique within a site.
- `recording_id`: canonical original-recording ID, not a derived filename.
- `coordinate_system`: explicit common coordinate label, e.g.
  `original-samples-256hz` or `original-seconds`.
- `start`, `end`: finite values in that original coordinate system, `[start,end)`.
  Touching intervals are not overlapping. Values are not rounded implicitly.

The library does not automatically inherit time intervals or subject metadata
through arbitrary transformations. Attach canonical metadata to assigned leaves.
`map_interval` only implements a supplied positive affine mapping. Nonlinear
warps, filter support, padding and unknown clock shifts require user-provided
provenance or must remain unverified.

Assignments contain `sample_id`, `split` (`train`, `validation`, `test`) and `fold`
(string, default `"0"`). Each fold needs train and an evaluation partition. All
partition pairs within a fold are checked. Ordinary reuse across independent
folds is allowed; nested-CV semantics are not implemented.

## Policies and coverage

- `cross_subject`: subject IDs must not cross partitions. No global time ordering
  is required. Shared source examples and raw interval overlap are also checked.
- `within_recording_future`: subject sharing is allowed; within each common
  recording/coordinate system, train must end no later than validation/test
  starts, and validation must precede test. Cross-recording chronological claims
  are UNKNOWN because clocks are not assumed comparable. This narrowly scoped
  policy does not audit future-target availability or preprocessing fit history.

`lineage_complete=True` is a declaration by the caller, not something the library
can prove. Omitting it makes lineage coverage UNKNOWN even if no shared ancestor
was found. Missing subject or interval metadata makes affected checks UNKNOWN.
A proven violation makes the overall result FAIL even if other checks are UNKNOWN.
PASS means only that the supplied metadata satisfies the applicable rules.

Results include per-fold checks, unknown-pair counts, violation counts and evidence
paths. `max_findings` limits returned examples, not failure counts. HTML/JSON
reports include identifiers and paths; keep them local or redact before sharing.
The tool performs no network requests, uploads, model training or automatic edits.

## Validation performed

On 2026-11-09, Python 3.14.7:

- 23 standard-library tests passed, including malformed manifests, parent cycles,
  multiple parents, interval boundaries, coordinate mapping, missing metadata,
  ordinary K-fold reuse, validation/test contamination and HTML escaping.
- 7 synthetic scenarios matched their expected PASS/FAIL/UNKNOWN outcomes.
- Compared against **leakfence 0.5.0**, NumPy 2.5.4 in an isolated environment.
  Subject mixing and interval overlap were detected by both tools. Clean splits
  were not flagged. The full machine-readable output is `results/comparison.json`.

In the derived-source case, leakfence's native input has no parent-graph field.
Calling it with only the available native metadata produced no flag; that is not
a safety verdict. **Manually grouping leaves by source also made leakfence detect
the problem.** Our demonstrated distinction is accepting the parent graph and
returning the chain of evidence, not a uniquely powerful detection algorithm.

The comparison uses the same available supported metadata, with the manual
source-group adapter shown separately. It is a small functional comparison, not
an independent benchmark, speed test, accuracy improvement, or proof of demand.
Deepchecks and other competitors were not executed in this prototype comparison.

Reproduce tests and the nearest-competitor comparison:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m venv /tmp/splittrace-comparison
/tmp/splittrace-comparison/bin/python -m pip install -r requirements-comparison.txt
/tmp/splittrace-comparison/bin/python scripts/compare.py
```

## Deliberate limits

Pairwise scanning is quadratic in partition sizes; ancestor-path storage also
grows with graph size/depth. Use small manifests. There is no performance claim.
No approximate content matching, nested-CV audit, persistent exception management,
automatic clock recovery, preprocessing tracing, causal/label leakage analysis or
proof of independence is implemented. Synthetic tests are not real-user validation.

Feedback is welcome from EEG, wearable-sensor and other windowed-signal projects:
can you supply source IDs/coordinates, and does a provenance path help you fix a
split? See [CONTRIBUTING.md](CONTRIBUTING.md) and the Japanese [trial guide](PILOT.md).

## References

- [leakfence](https://github.com/ptapal/leakfence)
- [Deepchecks train-test validation](https://docs.deepchecks.com/stable/api/generated/deepchecks.tabular.suites.train_test_validation.html)
- [bioLeak](https://github.com/selcukorkmaz/bioLeak)

This prototype contains no copied competitor implementation. Optional comparison
dependencies retain their own licenses and are installed separately.

## License

[MIT](LICENSE). Copyright (c) 2026 Ryu Koda.
