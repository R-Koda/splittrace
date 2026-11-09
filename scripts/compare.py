"""Run reproducible synthetic cases against SplitTrace and leakfence 0.5.0.

No accuracy claims: no model training. Parent graphs are not part of leakfence's
native API. Also show a manually flattened source-group adapter, so a missing
native input is not misrepresented as an intrinsically undetectable leak.
"""
import html
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))
from splittrace import audit
from splittrace.cli import html_report
from scenarios import scenarios
import leakfence
import numpy as np


def competitor(case, source_groups=False):
    nodes = {s["sample_id"]: s for s in case["samples"]}
    ids = sorted({a["sample_id"] for a in case["assignments"]})
    active = [nodes[sid] for sid in ids]
    reports = []
    for fold in sorted({a["fold"] for a in case["assignments"]}):
        assignments = [a for a in case["assignments"] if a["fold"] == fold]
        kwargs = dict(train_idx=[ids.index(a["sample_id"]) for a in assignments if a["split"] == "train"],
                      test_idx=[ids.index(a["sample_id"]) for a in assignments if a["split"] == "test"],
                      n_rows=len(ids))
        if all("subject_id" in s for s in active):
            kwargs["subject"] = [s["subject_id"] for s in active]
            kwargs["paradigm"] = "cross-subject" if case["policy"] == "cross_subject" else "within-session"
        if all(all(k in s for k in ("recording_id","start","end")) for s in active):
            kwargs["recording"] = [s["recording_id"] for s in active]
            kwargs["sample_range"] = np.array([[s["start"],s["end"]] for s in active])
        if source_groups:
            # Fixture-specific adapter: known common parent supplied as group.
            # A general graph/coordinate adapter would require extra user code.
            kwargs["subject"] = ["epoch-01", "epoch-01"]
            kwargs["paradigm"] = "cross-subject"
        reports.append(leakfence.audit_split(**kwargs).to_dict())
    return reports


def main():
    out=ROOT/"results"
    out.mkdir(exist_ok=True)
    rows=[]
    for case in scenarios():
        result=audit(case["samples"],case["assignments"],policy=case["policy"],lineage_complete=True)
        assert result["status"] == case["expected"], case["name"]
        native=competitor(case)
        native_flag=any(not r["ok"] for r in native)
        if case["name"] in ("subject_mix", "window_overlap"):
            assert native_flag, case["name"]
        if case["name"] in ("clean_cross_subject", "clean_future", "normal_kfold"):
            assert not native_flag, case["name"]
        note="Comparable metadata supplied for supported checks; not a global safety certificate."
        if case["name"] in ("derived_same_origin","missing_metadata"):
            note="Native call can only check shared row indices here; subject/interval metadata absent. Parent graph unsupported. No flag is NOT a clean verdict."
        row=dict(case=case["name"],expected=result["status"],splittrace=result,
                 leakfence_native_flag=native_flag,leakfence_reports=native,note=note)
        if case["name"] == "derived_same_origin":
            adapted=competitor(case,True)
            row["leakfence_with_manual_source_group_flag"]=any(not r["ok"] for r in adapted)
            assert row["leakfence_with_manual_source_group_flag"]
            (ROOT/"examples"/"derived-samples.json").write_text(json.dumps(case["samples"],indent=2)+"\n")
            (ROOT/"examples"/"derived-assignments.json").write_text(json.dumps(case["assignments"],indent=2)+"\n")
            (out/"derived-audit.html").write_text(html_report(result))
        rows.append(row)
    evidence=dict(python=platform.python_version(),leakfence=version("leakfence"),numpy=version("numpy"),
                  dataset="Synthetic fixtures only; no trained models or real subject data.",
                  methodology="Only nearest direct competitor tested. Same available supported metadata; lineage adapter shown separately.",cases=rows)
    (out/"comparison.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+"\n")
    cells=[]
    for r in rows:
        adapted=r.get("leakfence_with_manual_source_group_flag")
        vals=[r["case"],r["splittrace"]["status"],"Flagged" if r["leakfence_native_flag"] else "No flag (see coverage)",
              "Flagged after source grouping" if adapted else "Not run",r["note"]]
        cells.append("<tr>"+"".join("<td>"+html.escape(v)+"</td>" for v in vals)+"</tr>")
    (out/"comparison.html").write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SplitTrace synthetic comparison</title><style>body{font:15px system-ui;max-width:1200px;margin:40px auto;padding:0 20px;line-height:1.6}h1{font-size:24px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:10px;text-align:left;vertical-align:top}.scroll{overflow:auto}</style>
<h1>合成データによる実行比較</h1><p>SplitTrace試作品 / leakfence '''+html.escape(evidence["leakfence"])+'''</p>
<p>7ケース。モデル学習・予測精度の比較ではありません。No flagは検査できた範囲での結果であり、安全認定ではありません。</p>
<div class="scroll"><table><thead><tr><th>Case</th><th>SplitTrace</th><th>leakfence native</th><th>Manual adapter</th><th>Coverage / interpretation</th></tr></thead><tbody>'''+"".join(cells)+'''</tbody></table></div>
<h2>分かったこと</h2><p>通常の被験者混入・区間重複は両者で検出。加工サンプルの親子関係はSplitTraceで経路付き検出。leakfenceも元サンプルをグループに変換して渡せば検出できました。現時点の価値は、検出原理の優位性ではなく、由来の取り扱いと説明を標準化する点です。</p>
<p>メタデータ欠損をUNKNOWNにする設計も確認。性能・大規模処理・実利用者の需要は未検証。</p></html>''')
    print(json.dumps({"cases":len(rows),"expected_statuses_matched":True,
                      "leakfence":evidence["leakfence"],"output":str(out/"comparison.html")},ensure_ascii=False))


if __name__ == "__main__":
    main()
