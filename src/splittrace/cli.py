import argparse
import csv
import hashlib
import html
import json
from pathlib import Path

from .core import audit


def read_rows(path, samples=False):
    path = Path(path)
    if path.suffix.lower() == ".json":
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError("JSON input must be a list of objects")
        return rows
    if path.suffix.lower() != ".csv":
        raise ValueError("inputs must be .csv or .json")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [{k: v for k, v in row.items() if v != ""} for row in csv.DictReader(handle)]
    if samples:
        for row in rows:
            row["parent_ids"] = json.loads(row.get("parent_ids", "[]"))
            for key in ("start", "end"):
                if key in row:
                    row[key] = float(row[key])
    return rows


def html_report(report):
    """Standalone, script-free report; all user-controlled content is escaped."""
    body = html.escape(json.dumps(report, ensure_ascii=False, indent=2))
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>SplitTrace audit</title><style>body{font:16px system-ui;max-width:1000px;'
            'margin:40px auto;padding:0 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere;'
            'font-size:13px}h1{font-size:24px}</style><h1>SplitTrace: ' + report["status"] +
            '</h1><p>Metadata-only audit. PASS does not certify absence of all leakage. '
            'This report may contain sample identifiers; review before sharing.</p><pre>' + body + '</pre></html>')


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit existing signal-ML splits and declared sample lineage.")
    parser.add_argument("samples", help="CSV or JSON list of provenance nodes")
    parser.add_argument("assignments", help="CSV or JSON list: sample_id, split, fold")
    parser.add_argument("--policy", required=True, choices=["cross_subject", "within_recording_future"])
    parser.add_argument("--lineage-complete", action="store_true", help="Assert all parent relationships are supplied")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(read_rows(args.samples, True), read_rows(args.assignments),
                       policy=args.policy, lineage_complete=args.lineage_complete)
        report["input_sha256"] = {name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                                  for name,path in [("samples",args.samples),("assignments",args.assignments)]}
        encoded = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(encoded + "\n", encoding="utf-8")
        if args.html:
            args.html.write_text(html_report(report), encoding="utf-8")
        print(encoded)
        return {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[report["status"]]
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
