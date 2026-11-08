#!/usr/bin/env python3
"""Reconstruct the E2 timeline from recorded samples without accessing the cluster."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys

COUNTS = ("ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible", "ApproximateNumberOfMessagesDelayed")


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def read_json(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def read_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def utc(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat()


def interval(first, last):
    if first is None or last is None:
        return None
    seconds = timestamp(last) - timestamp(first)
    return round(seconds, 1) if seconds >= 0 else None


def empty_counts(counts):
    return isinstance(counts, dict) and all(key in counts and counts[key] == 0 for key in COUNTS)


def analyze(directory):
    metadata = read_json(directory / "metadata.json")
    if metadata.get("scenario") != "E2" or metadata.get("variant") != "elastic":
        raise ValueError("Chỉ hỗ trợ lượt E2 elastic")
    summary = read_json(directory / "raw/k6-summary.json")["metrics"]
    start = float(summary["workload_started_at_unix_ms"]["value"]) / 1000
    finished = summary.get("workload_finished_at_unix_ms", {}).get("value")
    end = float(finished) / 1000 if finished is not None else None
    before = read_json(directory / "events/collect-before.json", {})
    collection = read_json(directory / "collection.json", {})
    pod_samples = sorted(read_lines(directory / "events/collect-worker-samples.jsonl"), key=lambda x: x["observed_at_utc"])
    topo_samples = sorted(read_lines(directory / "events/collect-topology-samples.jsonl"), key=lambda x: x["observed_at_utc"])
    queue_samples = sorted(read_lines(directory / "metrics/collect-sqs-samples.jsonl"), key=lambda x: x["observed_at_utc"])
    pool = "e2-orders"
    initial_nodes = {n["name"] for n in before.get("nodes", [])
                     if n.get("labels", {}).get("karpenter.sh/nodepool") == pool and n.get("name")}
    before_nodes, before_claims = set(), set()
    pending, ready, claims, nodes = {}, {}, {}, {}
    for sample in topo_samples:
        seen = sample["observed_at_utc"]
        for node in sample["data"].get("nodes", []):
            if node.get("labels", {}).get("karpenter.sh/nodepool") != pool:
                continue
            uid = node.get("uid")
            if timestamp(seen) < start:
                before_nodes.add(uid)
                if node.get("name"):
                    initial_nodes.add(node["name"])
                continue
            if (not uid or uid in before_nodes or node.get("name") in initial_nodes
                    or (node.get("created_at") and timestamp(node["created_at"]) < start)):
                continue
            if any(c.get("type") == "Ready" and c.get("status") == "True" for c in node.get("conditions", [])):
                nodes.setdefault(uid, {"uid": uid, "name": node.get("name"), "provider_id": node.get("provider_id"),
                                       "ready_first_observed_utc": seen})
        for claim in sample["data"].get("nodeclaims", []):
            if claim.get("labels", {}).get("karpenter.sh/nodepool") != pool:
                continue
            uid = claim.get("uid")
            if timestamp(seen) < start:
                before_claims.add(uid)
                continue
            if not uid or uid in before_claims or (claim.get("created") and timestamp(claim["created"]) < start):
                continue
            status = claim.get("status", {})
            item = claims.setdefault(uid, {"uid": uid, "name": claim.get("name"), "created_utc": claim.get("created"),
                                           "provider_id": None, "node_name": None, "first_observed_utc": seen})
            item["provider_id"] = status.get("providerID") or item["provider_id"]
            item["node_name"] = status.get("nodeName") or item["node_name"]

    active_observed = False
    scaled_zero = None
    for sample in pod_samples:
        seen, data = sample["observed_at_utc"], sample["data"]
        if timestamp(seen) < start:
            continue
        if data.get("desired", 0) > 0 or data.get("ready", 0) > 0 or data.get("pods"):
            active_observed = True
        if (end is not None and timestamp(seen) >= end and active_observed and scaled_zero is None
                and data.get("desired") == 0 and data.get("ready") == 0 and data.get("pods") == []):
            scaled_zero = seen
        for pod in data.get("pods", []):
            uid = pod.get("uid")
            if not uid:
                continue
            condition = next((c for c in pod.get("conditions", []) if c.get("type") == "PodScheduled"
                              and c.get("status") == "False" and c.get("reason") == "Unschedulable"), None)
            if condition:
                pending.setdefault(uid, {"uid": uid, "name": pod.get("name"), "first_observed_utc": seen,
                                         "message": condition.get("message")})
            if pod.get("node") and pod.get("containers") and all(c.get("ready") for c in pod["containers"]):
                ready.setdefault(uid, {"uid": uid, "name": pod.get("name"), "node": pod.get("node"),
                                       "first_observed_utc": seen})

    links = []
    for uid, waiting in pending.items():
        running = ready.get(uid)
        if not running:
            continue
        node = next((item for item in nodes.values() if item.get("name") == running.get("node")), None)
        if not node:
            continue
        claim = next((item for item in claims.values() if
                      (node.get("provider_id") and item.get("provider_id") == node["provider_id"]) or
                      (item.get("node_name") and item["node_name"] == node["name"])), None)
        if not claim:
            continue
        links.append({"pod_uid": uid, "pod_name": running["name"], "node_name": node["name"],
                      "nodeclaim_name": claim["name"], "provider_id": node.get("provider_id"),
                      "pending_first_observed_utc": waiting["first_observed_utc"],
                      "pending_message": waiting.get("message"),
                      "nodeclaim_created_utc": claim.get("created_utc"),
                      "node_ready_first_observed_utc": node["ready_first_observed_utc"],
                      "pod_ready_first_observed_utc": running["first_observed_utc"],
                      "pending_to_pod_ready_seconds_approx": interval(waiting["first_observed_utc"], running["first_observed_utc"])})

    first_ready = next((p for p in ready.values() if p.get("node") in initial_nodes), None)
    # Unschedulable by itself is not evidence of insufficient capacity.
    chosen = next((link for link in links if "insufficient " in (link.get("pending_message") or "").lower()), None)
    first_pending = next((item for item in pending.values()
                          if "insufficient " in (item.get("message") or "").lower()), None)
    drain = None
    consecutive = []
    max_gap = 3 * float(collection.get("requested_interval_seconds", 5)) + 10
    for sample in queue_samples:
        seen, data = sample["observed_at_utc"], sample["data"]
        if end is None or timestamp(seen) < end:
            continue
        main = data.get("main", {}).get("counts")
        dlq = data.get("dlq", {}).get("counts")
        needs_dlq = bool(before.get("dlq"))
        empty = empty_counts(main) and (empty_counts(dlq) if dlq is not None else not needs_dlq)
        if not empty or (consecutive and timestamp(seen) - timestamp(consecutive[-1]) > max_gap):
            consecutive = []
        if empty:
            consecutive.append(seen)
        if len(consecutive) >= 3:
            drain = seen
            break

    marks = {"T0": utc(start), "T1": first_ready["first_observed_utc"] if first_ready else None,
             "T2": chosen["pending_first_observed_utc"] if chosen else (first_pending["first_observed_utc"] if first_pending else None),
             "T3": chosen["nodeclaim_created_utc"] if chosen else None,
             "T4": chosen["node_ready_first_observed_utc"] if chosen else None,
             "T5": chosen["pod_ready_first_observed_utc"] if chosen else None,
             "T6": utc(end) if end is not None else None, "T7": drain, "T8": scaled_zero}
    version = summary.get("workload_model_version", {}).get("value")
    high_offset = 60 if metadata.get("profile") == "burst" and version in (1, 2, 3, 4, 5) else None
    return {"run_id": metadata["run_id"], "workload_started_utc": marks["T0"],
            "high_rate_started_utc": utc(start + high_offset) if high_offset is not None else None,
            "timeline_utc": marks,
            "intervals_seconds_approx": {"cold_start_pod": interval(marks["T0"], marks["T1"]),
                "node_provisioning": interval(marks["T3"], marks["T4"]),
                "pod_startup_on_new_node": interval(marks["T4"], marks["T5"]),
                "queue_drain_after_workload": interval(marks["T6"], marks["T7"]),
                "scale_to_zero_after_workload": interval(marks["T6"], marks["T8"])},
            "initial_node_names": sorted(initial_nodes), "unschedulable_pods": list(pending.values()),
            "new_nodeclaims": list(claims.values()), "new_ready_nodes": list(nodes.values()),
            "ready_pods": list(ready.values()), "candidate_links": links,
            "note": "Mốc observed là mẫu, T0/T6 lấy từ k6 setup/teardown; NodeClaim là proxy. Liên kết là ứng viên: kiểm tra scheduler event, nguyên nhân thiếu capacity và đồng hồ. Thiếu bằng chứng hoặc khoảng âm là null, không phải 0."}


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.run_dir), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Không dựng được timeline: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
