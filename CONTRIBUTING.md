# Contributing

SplitTrace is an experimental, metadata-only auditor. Small, reproducible examples
are more useful at this stage than a large new feature surface.

## Report a problem or try the prototype

Open an issue with:

- Python version and the commit you tested;
- intended evaluation policy (new subjects or future windows in a recording);
- a **synthetic** sample manifest and split assignments;
- expected outcome and actual report;
- how you currently handle this with another tool or a short script.

Please do not upload patient records, private datasets, credentials, or reports
containing real subject identifiers. Reduce examples to invented IDs and intervals.
Private security issues should use the process in [SECURITY.md](SECURITY.md).

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
```

Keep core runtime dependencies empty. Add behavior tests for new rules, including
a legitimate split that should not be flagged and a missing-metadata case.
Do not silently turn UNKNOWN into PASS or remove evaluation examples automatically.
Document changes to the data contract and report schema.

## Optional comparison

Use a separate environment and `requirements-comparison.txt` to run
`scripts/compare.py`. It regenerates synthetic fixtures and reports. Do not infer
real-world accuracy, adoption or speed from this small functional comparison.
When comparing tools, show unsupported inputs and manual adapters separately.

## Pull requests

Explain the concrete scenario, expected behavior and tests run. Contributions
are provided under the repository's MIT license. Do not submit code or data you
do not have permission to share.
