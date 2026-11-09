import copy
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

from splittrace import audit, map_interval
from splittrace.cli import main, html_report


def sample(sid, subject="p1", recording="r1", start=0, end=10, parents=None):
    return dict(sample_id=sid, subject_id=subject, recording_id=recording,
                start=start, end=end, coordinate_system="original-seconds",
                parent_ids=parents or [])


def assignment(sid, split, fold="0"):
    return dict(sample_id=sid, split=split, fold=fold)


class AuditTests(unittest.TestCase):
    def test_explicit_resampling_mapping(self):
        # 128 local samples at 128 Hz, starting at original sample 256 at 256 Hz.
        self.assertEqual(map_interval(0,128,origin_offset=256,original_units_per_local_unit=2),(256,512))
        nodes = [sample("a",start=200,end=300), sample("b",start=256,end=512)]
        report = self.run_audit(nodes,policy="within_recording_future")
        self.assertEqual(report["violation_counts"]["interval"],1)

    def test_invalid_coordinate_mapping(self):
        with self.assertRaises(ValueError):
            map_interval(0,10,origin_offset=0,original_units_per_local_unit=-1)

    def run_audit(self, nodes, assignments=None, policy="cross_subject", **kwargs):
        return audit(nodes, assignments or [assignment("a", "train"), assignment("b", "test")],
                     policy=policy, lineage_complete=True, **kwargs)

    def test_cross_subject_clean(self):
        report = self.run_audit([sample("a"), sample("b", "p2", "r2")])
        self.assertEqual(report["status"], "PASS")

    def test_subject_overlap_without_interval_overlap(self):
        report = self.run_audit([sample("a"), sample("b", start=10, end=20)])
        self.assertEqual(report["violation_counts"]["subject"], 1)
        self.assertEqual(report["violation_counts"]["interval"], 0)

    def test_touching_intervals_valid_for_known_recording_future(self):
        report = self.run_audit([sample("a"), sample("b", start=10, end=20)], policy="within_recording_future")
        self.assertEqual(report["status"], "PASS")

    def test_overlapping_intervals_report_exact_overlap(self):
        report = self.run_audit([sample("a"), sample("b", start=8, end=18)], policy="within_recording_future")
        finding = next(f for f in report["findings"] if f["rule"] == "interval")
        self.assertEqual((finding["evidence"]["overlap_start"], finding["evidence"]["overlap_end"]), (8,10))

    def test_reversed_time_without_overlap_still_fails(self):
        report = self.run_audit([sample("a", start=20, end=30), sample("b")], policy="within_recording_future")
        self.assertEqual(report["violation_counts"]["interval"], 0)
        self.assertEqual(report["violation_counts"]["chronology"], 1)

    def test_transformed_siblings_share_ancestor(self):
        nodes = [dict(sample_id="origin"), dict(sample_id="image", parent_ids=["origin"]),
                 dict(sample_id="a", parent_ids=["image"]), dict(sample_id="b", parent_ids=["origin"])]
        report = self.run_audit(nodes)
        finding = next(f for f in report["findings"] if f["rule"] == "lineage")
        self.assertEqual(finding["evidence"]["left_path"], ["a","image","origin"])
        self.assertEqual(finding["evidence"]["right_path"], ["b","origin"])
        self.assertEqual(report["status"], "FAIL")

    def test_shared_recording_parent_is_not_sample_leak(self):
        nodes = [dict(sample_id="raw", kind="recording"), sample("a", parents=["raw"]),
                 sample("b", start=10, end=20, parents=["raw"])]
        report = self.run_audit(nodes, policy="within_recording_future")
        self.assertEqual(report["status"], "PASS")

    def test_unknown_lineage_never_passes(self):
        report = audit([sample("a"), sample("b", "p2", "r2")],
                       [assignment("a","train"), assignment("b","test")], policy="cross_subject")
        self.assertEqual(report["status"], "UNKNOWN")

    def test_unknown_group_metadata(self):
        nodes = [sample("a"), sample("b", "p2", "r2")]
        nodes[1].pop("subject_id")
        self.assertEqual(self.run_audit(nodes)["status"], "UNKNOWN")

    def test_unaligned_coordinates_are_unknown(self):
        nodes = [sample("a"), sample("b", start=10,end=20)]
        nodes[1]["coordinate_system"] = "local-samples-256hz"
        report = self.run_audit(nodes, policy="within_recording_future")
        self.assertEqual(report["status"], "UNKNOWN")

    def test_multiple_recordings_future_not_assumed_comparable(self):
        nodes = [sample("a"), sample("b", recording="other", start=20,end=30)]
        self.assertEqual(self.run_audit(nodes, policy="within_recording_future")["status"], "UNKNOWN")

    def test_normal_kfold_reuse_allowed(self):
        nodes = [sample("a"),sample("b","p2","r2")]
        assignments = [assignment("a","train","0"),assignment("b","test","0"),
                       assignment("b","train","1"),assignment("a","test","1")]
        self.assertEqual(self.run_audit(nodes,assignments)["status"], "PASS")

    def test_validation_test_are_also_compared(self):
        nodes = [sample("a"),sample("b","p2","r2"),sample("c","p2","r2")]
        report = self.run_audit(nodes,[assignment("a","train"),assignment("b","validation"),assignment("c","test")])
        self.assertTrue(any(f["left_split"]=="validation" and f["right_split"]=="test" for f in report["findings"]))

    def test_same_id_between_partitions(self):
        report = self.run_audit([sample("a")], [assignment("a","train"),assignment("a","test")])
        self.assertEqual(report["violation_counts"]["sample_identity"], 1)

    def test_truncation_does_not_suppress_failure(self):
        report = self.run_audit([sample("a"),sample("b")], max_findings=0)
        self.assertEqual(report["status"],"FAIL")
        self.assertEqual(report["findings"],[])
        self.assertTrue(report["findings_truncated"])

    def test_multiple_parents_find_shared_one(self):
        nodes = [dict(sample_id="x"),dict(sample_id="y"),dict(sample_id="a",parent_ids=["x","y"]),dict(sample_id="b",parent_ids=["y"])]
        report = self.run_audit(nodes)
        self.assertEqual(next(f for f in report["findings"] if f["rule"]=="lineage")["evidence"]["ancestor"],"y")

    def test_inputs_not_mutated_and_result_deterministic(self):
        nodes = [sample("a"),sample("b")]
        before = copy.deepcopy(nodes)
        self.assertEqual(self.run_audit(nodes),self.run_audit(nodes))
        self.assertEqual(nodes,before)

    def test_invalid_manifests(self):
        invalid = [
            [dict(sample_id="a",parent_ids=["b"]),dict(sample_id="b",parent_ids=["a"])],
            [dict(sample_id="a",parent_ids=["missing"]),sample("b")],
            [sample("a"),sample("a")],
            [sample("a", start=float("nan")),sample("b")],
            [sample("a",start=10,end=0),sample("b")],
        ]
        for nodes in invalid:
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                self.run_audit(nodes)

    def test_invalid_assignments(self):
        for assignments in [[],[assignment("a","train")],
                            [assignment("a","train"),assignment("missing","test")],
                            [assignment("a","train"),assignment("a","train"),assignment("b","test")]]:
            with self.subTest(assignments=assignments), self.assertRaises(ValueError):
                audit([sample("a"),sample("b")],assignments,policy="cross_subject")

    def test_html_escapes_untrusted_ids(self):
        report = self.run_audit([sample("a"),sample("b")])
        report["findings"][0]["left"] = "<script>alert(1)</script>"
        rendered = html_report(report)
        self.assertNotIn("<script>",rendered)
        self.assertIn("&lt;script&gt;",rendered)

    def test_cli_csv_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"assign.csv").write_text("sample_id,split,fold\na,train,0\nb,test,0\n")
            (root/"samples.csv").write_text("sample_id,subject_id,recording_id,coordinate_system,start,end\na,p1,r1,seconds,0,10\nb,p2,r2,seconds,0,10\n")
            args=[str(root/"samples.csv"),str(root/"assign.csv"),"--policy","cross_subject"]
            with redirect_stdout(StringIO()):
                self.assertEqual(main(args),2)
                self.assertEqual(main(args+["--lineage-complete","--output",str(root/"result.json"),"--html",str(root/"result.html")]),0)
                (root/"samples.csv").write_text((root/"samples.csv").read_text().replace("b,p2","b,p1"))
                self.assertEqual(main(args+["--lineage-complete"]),1)
            self.assertEqual(json.loads((root/"result.json").read_text())["status"],"PASS")


if __name__ == "__main__":
    unittest.main()
