#!/usr/bin/env python3
"""List sampled E2 two-level events; correlations require manual verification."""
import argparse
import datetime as dt
import json
from pathlib import Path
import sys


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def analyze(directory):
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8-sig"))
    if metadata.get("scenario") != "E2" or metadata.get("variant") != "elastic":
        raise ValueError("Chỉ hỗ trợ lượt E2 elastic")
    summary = json.loads((directory / "raw/k6-summary.json").read_text(encoding="utf-8-sig"))["metrics"]
    start = float(summary["workload_started_at_unix_ms"]["value"]) / 1000
    to_epoch = lambda x: dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()
    pod_samples = read_lines(directory / "events/collect-worker-samples.jsonl")
    topo_samples = read_lines(directory / "events/collect-topology-samples.jsonl")
    pending, ready, claims, nodes = {}, {}, {}, {}
    before_claims, before_nodes = set(), set()
    for sample in sorted(topo_samples, key=lambda x: x["observed_at_utc"]):
        seen = sample["observed_at_utc"]
        for n in sample["data"].get("nodes", []):
            if n.get("labels", {}).get("karpenter.sh/nodepool") != "e2-orders": continue
            uid = n.get("uid")
            if to_epoch(seen) < start: before_nodes.add(uid); continue
            if uid in before_nodes or not uid: continue
            if any(x.get("type") == "Ready" and x.get("status") == "True" for x in n.get("conditions", [])):
                nodes.setdefault(uid, {"uid": uid, "name": n.get("name"), "provider_id": n.get("provider_id"), "ready_first_observed_utc": seen})
        for claim in sample["data"].get("nodeclaims", []):
            if claim.get("labels", {}).get("karpenter.sh/nodepool") != "e2-orders": continue
            uid = claim.get("uid")
            if to_epoch(seen) < start: before_claims.add(uid); continue
            if uid in before_claims or not uid: continue
            status = claim.get("status", {})
            claims.setdefault(uid, {"uid": uid, "name": claim.get("name"), "created_utc": claim.get("created"),
                                   "provider_id": status.get("providerID"), "node_name": status.get("nodeName"), "first_observed_utc": seen})
            if status.get("providerID"): claims[uid]["provider_id"] = status["providerID"]
            if status.get("nodeName"): claims[uid]["node_name"] = status["nodeName"]
    for sample in sorted(pod_samples, key=lambda x: x["observed_at_utc"]):
        seen = sample["observed_at_utc"]
        if to_epoch(seen) < start: continue
        for pod in sample["data"].get("pods", []):
            uid = pod.get("uid")
            if not uid: continue
            if any(c.get("type") == "PodScheduled" and c.get("status") == "False" and c.get("reason") == "Unschedulable" for c in pod.get("conditions", [])):
                pending.setdefault(uid, {"uid": uid, "name": pod.get("name"), "first_observed_utc": seen})
            if pod.get("node") and pod.get("containers") and all(c.get("ready") for c in pod["containers"]):
                ready.setdefault(uid, {"uid": uid, "name": pod.get("name"), "node": pod.get("node"), "first_observed_utc": seen})
    links = []
    for uid, pending_pod in pending.items():
        ready_pod = ready.get(uid)
        if not ready_pod:
            continue
        node = next((item for item in nodes.values() if item.get("name") == ready_pod.get("node")), None)
        if not node:
            continue
        claim = next((item for item in claims.values() if
                      (node.get("provider_id") and item.get("provider_id") == node["provider_id"]) or
                      (item.get("node_name") and item["node_name"] == node["name"])), None)
        if not claim:
            continue
        delay = to_epoch(ready_pod["first_observed_utc"]) - to_epoch(pending_pod["first_observed_utc"])
        links.append({"pod_uid": uid, "pod_name": ready_pod["name"], "node_name": node["name"],
                      "nodeclaim_name": claim["name"], "provider_id": node.get("provider_id"),
                      "pending_to_pod_ready_seconds_approx": round(delay, 1) if delay >= 0 else None})
    profile = metadata.get("profile")
    high_offset = {"step": 180, "burst": 60}.get(profile)
    return {"run_id": metadata["run_id"], "workload_started_utc": dt.datetime.fromtimestamp(start,dt.timezone.utc).isoformat(),
            "high_rate_started_utc": dt.datetime.fromtimestamp(start + high_offset,dt.timezone.utc).isoformat() if high_offset is not None else None,
            "unschedulable_pods": list(pending.values()), "new_nodeclaims": list(claims.values()),
            "new_ready_nodes": list(nodes.values()), "ready_pods": list(ready.values()), "candidate_links": links,
            "note": "Mốc observed là thời điểm lấy mẫu, không phải thời điểm chính xác. Liên kết là ứng viên theo UID Pod, providerID hoặc nodeName; phải kiểm tra scheduler event để xác định thiếu capacity và xác nhận cùng đường provisioning. Danh sách rỗng không chứng minh sự kiện không xảy ra."}


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    try: print(json.dumps(analyze(args.run_dir), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Không dựng được timeline: {exc}", file=sys.stderr); return 1
    return 0

if __name__ == "__main__": raise SystemExit(main())
