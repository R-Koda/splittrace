"""Small, deterministic metadata auditor with explicit coverage limits.

Intervals must already refer to ORIGINAL recording coordinates. No signal data
is inspected and no implicit conversion between clocks or sample rates occurs.
"""
from collections import deque
from itertools import combinations
from math import isfinite

ROLES = ("train", "validation", "test")
RULES = ("sample_identity", "subject", "lineage", "interval", "chronology")


def map_interval(start, end, *, origin_offset, original_units_per_local_unit):
    """Explicit affine mapping to original coordinates (e.g. resampled indices).

    Only positive linear transforms are supported. Caller supplies provenance;
    this does not infer clocks, filtering support, padding or nonlinear warps.
    """
    values = (start, end, origin_offset, original_units_per_local_unit)
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v) for v in values):
        raise ValueError("mapping values must be finite numbers")
    if start >= end or original_units_per_local_unit <= 0:
        raise ValueError("mapping needs start < end and a positive scale")
    mapped = (origin_offset + start * original_units_per_local_unit,
              origin_offset + end * original_units_per_local_unit)
    if not all(isfinite(v) for v in mapped) or mapped[0] >= mapped[1]:
        raise ValueError("mapping overflow or collapsed interval")
    return mapped


def _id(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _nodes(samples):
    nodes = {}
    for item in samples:
        item = dict(item)
        sid = _id(item.get("sample_id"), "sample_id")
        if sid in nodes:
            raise ValueError(f"duplicate sample_id: {sid}")
        kind = item.setdefault("kind", "sample")
        if kind not in ("sample", "recording"):
            raise ValueError("kind must be sample or recording")
        parents = item.setdefault("parent_ids", [])
        if not isinstance(parents, list) or len(set(map(str, parents))) != len(parents):
            raise ValueError("parent_ids must be a list without duplicates")
        for parent in parents:
            _id(parent, "parent_id")
        for key in ("subject_id", "recording_id", "coordinate_system"):
            if item.get(key) is not None:
                _id(item[key], key)
        start, end = item.get("start"), item.get("end")
        if (start is None) != (end is None):
            raise ValueError("start and end must be supplied together")
        if start is not None:
            if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v)
                   for v in (start, end)) or start >= end:
                raise ValueError("interval must have finite numeric start < end")
            if not item.get("recording_id") or not item.get("coordinate_system"):
                raise ValueError("interval needs recording_id and coordinate_system")
        nodes[sid] = item
    if not nodes:
        raise ValueError("samples must not be empty")
    # Iterative topological ordering: no recursion-limit failure on long chains.
    children = {sid: [] for sid in nodes}
    indegree = {}
    for sid, node in nodes.items():
        indegree[sid] = len(node["parent_ids"])
        for parent in node["parent_ids"]:
            if parent not in nodes:
                raise ValueError(f"missing parent {parent} referenced by {sid}")
            children[parent].append(sid)
    ready = deque(sorted(sid for sid, count in indegree.items() if count == 0))
    order = []
    while ready:
        sid = ready.popleft()
        order.append(sid)
        for child in sorted(children[sid]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(order) != len(nodes):
        raise ValueError("cycle in parent_ids")
    # One deterministic witness path per ancestor, including the node itself.
    paths = {}
    for sid in order:
        paths[sid] = {sid: [sid]}
        for parent in sorted(nodes[sid]["parent_ids"]):
            for ancestor, path in paths[parent].items():
                paths[sid].setdefault(ancestor, [sid] + path)
    return nodes, paths


def audit(samples, assignments, *, policy, lineage_complete=False, max_findings=1000):
    """Return JSON-serializable findings for each independent fold.

    policy: cross_subject OR within_recording_future.
    lineage_complete: user's declaration that all parent relationships are given.
    Max findings limits returned examples, NEVER the underlying failure counts.
    Unknown metadata fails closed (UNKNOWN) unless a proven violation makes FAIL.
    All comparisons are within each fold; ordinary cross-fold reuse is allowed.
    """
    if policy not in ("cross_subject", "within_recording_future"):
        raise ValueError("explicit policy must be cross_subject or within_recording_future")
    if not isinstance(lineage_complete, bool):
        raise ValueError("lineage_complete must be boolean")
    if isinstance(max_findings, bool) or not isinstance(max_findings, int) or max_findings < 0:
        raise ValueError("max_findings must be a nonnegative integer")
    nodes, paths = _nodes(samples)
    folds, seen = {}, set()
    for row in assignments:
        sid = _id(row.get("sample_id"), "assignment sample_id")
        fold = _id(row.get("fold", "0"), "fold")
        role = row.get("split")
        if sid not in nodes or nodes[sid]["kind"] != "sample":
            raise ValueError(f"assignment must reference a sample: {sid}")
        if role not in ROLES:
            raise ValueError("split must be train, validation or test")
        key = (fold, role, sid)
        if key in seen:
            raise ValueError(f"duplicate assignment: {key}")
        seen.add(key)
        folds.setdefault(fold, {}).setdefault(role, []).append(sid)
    if not folds:
        raise ValueError("assignments must not be empty")
    findings, counts, fold_results = [], {r: 0 for r in RULES}, []
    for fold, groups in sorted(folds.items()):
        if "train" not in groups or not any(r in groups for r in ("validation", "test")):
            raise ValueError(f"fold {fold} needs train and an evaluation partition")
        state = {r: {"violations": 0, "unknown_pairs": 0} for r in RULES}

        def emit(rule, left, right, left_role, right_role, evidence):
            counts[rule] += 1
            state[rule]["violations"] += 1
            if len(findings) < max_findings:
                findings.append(dict(rule=rule, fold=fold, left=left, right=right,
                                     left_split=left_role, right_split=right_role, evidence=evidence))

        for left_role, right_role in combinations([r for r in ROLES if r in groups], 2):
            for left in sorted(groups[left_role]):
                for right in sorted(groups[right_role]):
                    a, b = nodes[left], nodes[right]
                    args = (left, right, left_role, right_role)
                    if left == right:
                        emit("sample_identity", *args, {"sample_id": left})
                    if policy == "cross_subject":
                        if a.get("subject_id") is None or b.get("subject_id") is None:
                            state["subject"]["unknown_pairs"] += 1
                        elif a["subject_id"] == b["subject_id"]:
                            emit("subject", *args, {"subject_id": a["subject_id"]})
                    common = sorted(set(paths[left]) & set(paths[right]))
                    # A whole recording may legitimately feed both partitions.
                    # Shared example ancestors (e.g. one augmented epoch) may not.
                    example_ancestors = [s for s in common if nodes[s]["kind"] == "sample"]
                    if example_ancestors:
                        ancestor = min(example_ancestors, key=lambda s: (len(paths[left][s]) + len(paths[right][s]), s))
                        emit("lineage", *args, {"ancestor": ancestor,
                            "left_path": paths[left][ancestor], "right_path": paths[right][ancestor]})
                    if not lineage_complete:
                        state["lineage"]["unknown_pairs"] += 1
                    complete = all(n.get(k) is not None for n in (a, b)
                                   for k in ("recording_id", "coordinate_system", "start", "end"))
                    comparable = complete and a["recording_id"] == b["recording_id"] and a["coordinate_system"] == b["coordinate_system"]
                    if not complete or (a.get("recording_id") == b.get("recording_id") and not comparable):
                        state["interval"]["unknown_pairs"] += 1
                    elif comparable:
                        start, end = max(a["start"], b["start"]), min(a["end"], b["end"])
                        if start < end:
                            emit("interval", *args, {"recording_id": a["recording_id"],
                                "coordinate_system": a["coordinate_system"],
                                "overlap_start": start, "overlap_end": end, "overlap_length": end-start})
                    if policy == "within_recording_future":
                        if not comparable:
                            state["chronology"]["unknown_pairs"] += 1
                        elif a["end"] > b["start"]:
                            emit("chronology", *args, {"earlier_split_end": a["end"],
                                "later_split_start": b["start"], "recording_id": a["recording_id"]})
        for rule, details in state.items():
            skip = (rule == "subject" and policy != "cross_subject") or (rule == "chronology" and policy != "within_recording_future")
            details["status"] = "SKIP" if skip else "FAIL" if details["violations"] else "UNKNOWN" if details["unknown_pairs"] else "PASS"
        fold_results.append({"fold": fold, "partition_sizes": {r:len(ids) for r,ids in groups.items()}, "checks": state})
    statuses = [check["status"] for f in fold_results for check in f["checks"].values()]
    verdict = "FAIL" if "FAIL" in statuses else "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    return {"schema_version": 1, "policy": policy, "lineage_complete": lineage_complete,
            "status": verdict, "folds": fold_results, "violation_counts": counts,
            "findings": findings, "findings_truncated": sum(counts.values()) > len(findings),
            "limitations": ["Checks declared metadata only; PASS is not proof of absence of all leakage.",
                            "Coordinates must already be mapped to the original recording; no implicit conversion.",
                            "No nested-CV, signal similarity, fitted-preprocessing or target-availability audit.",
                            "Quadratic pair scan: prototype for small manifests, not large-scale production."]}
