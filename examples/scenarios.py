"""Synthetic fixtures only. No private code, identifiers or patient data."""


def node(sid, subject, recording, start, end, parents=None):
    return dict(sample_id=sid, subject_id=subject, recording_id=recording,
                coordinate_system="original-seconds", start=start, end=end, parent_ids=parents or [])


def scenarios():
    standard = [dict(sample_id="a",split="train",fold="0"),dict(sample_id="b",split="test",fold="0")]
    def case(name,nodes,policy,expected,assignments=None):
        return dict(name=name,samples=nodes,assignments=assignments or standard,policy=policy,expected=expected)
    return [
        case("clean_cross_subject",[node("a","p1","r1",0,10),node("b","p2","r2",0,10)],"cross_subject","PASS"),
        case("subject_mix",[node("a","p1","r1",0,10),node("b","p1","r1",10,20)],"cross_subject","FAIL"),
        case("window_overlap",[node("a","p1","r1",0,10),node("b","p1","r1",8,18)],"within_recording_future","FAIL"),
        case("clean_future",[node("a","p1","r1",0,10),node("b","p1","r1",10,20)],"within_recording_future","PASS"),
        # IDs/clocks of the exported files look independent. Declared provenance
        # reveals a shared source example; values alone are intentionally different.
        case("derived_same_origin",[
            dict(sample_id="epoch-01"),dict(sample_id="image-01",parent_ids=["epoch-01"]),
            dict(sample_id="a",parent_ids=["image-01"]),
            dict(sample_id="b",parent_ids=["epoch-01"])],"cross_subject","FAIL"),
        case("missing_metadata",[dict(sample_id="a"),dict(sample_id="b")],"cross_subject","UNKNOWN"),
        case("normal_kfold",[node("a","p1","r1",0,10),node("b","p2","r2",0,10)],"cross_subject","PASS",[
            dict(sample_id="a",split="train",fold="0"),dict(sample_id="b",split="test",fold="0"),
            dict(sample_id="b",split="train",fold="1"),dict(sample_id="a",split="test",fold="1")]),
    ]
