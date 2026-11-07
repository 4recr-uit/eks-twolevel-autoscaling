#!/usr/bin/env python3
"""Tóm tắt một lượt E1 từ dữ liệu đã thu; không truy cập cluster."""

import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sys


def timestamp(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def matrix(directory, name):
    path = directory / "metrics" / f"collect-prometheus-{name}.json"
    if not path.is_file():
        return []
    data = read_json(path)
    if data.get("status") != "success":
        return []
    return data.get("data", {}).get("result", [])


def counter_delta(series, start, end):
    """Chỉ tính chênh lệch mẫu trong cửa sổ, kể cả reset; là ước lượng thấp."""
    points = [(float(t), float(v)) for t, v in series.get("values", [])
              if start <= float(t) <= end and math.isfinite(float(v))]
    if len(points) < 2:
        return None
    points.sort()
    return sum(b if b < a else b - a for (_, a), (_, b) in zip(points, points[1:]))


def count_by_label(series, label, start, end):
    values = {}
    for item in series:
        key = item.get("metric", {}).get(label, "unknown")
        delta = counter_delta(item, start, end)
        if delta is not None:
            values[key] = values.get(key, 0) + delta
    return {key: round(value, 2) for key, value in values.items()}


def histogram_quantile(buckets, q):
    if "+Inf" not in buckets or buckets["+Inf"] <= 0:
        return None
    target = q * buckets["+Inf"]
    finite = sorted((float(k), v) for k, v in buckets.items() if k != "+Inf")
    previous_bound = previous_count = 0.0
    for bound, count in finite:
        if count < previous_count:  # Không suy diễn từ histogram thiếu mẫu.
            return None
        if count >= target:
            if count == previous_count:
                return round(bound, 3)
            return round(previous_bound + (bound - previous_bound) * (target - previous_count) / (count - previous_count), 3)
        previous_bound, previous_count = bound, count
    return None  # Phân vị vượt bucket hữu hạn lớn nhất.


def replica_minutes(series, start, end, step):
    if len(series) != 1:
        return None
    points = sorted((float(t), float(v)) for t, v in series[0].get("values", [])
                    if math.isfinite(float(v)))
    before = [x for x in points if x[0] <= start]
    if not before:
        return None
    points = [before[-1]] + [x for x in points if start < x[0] <= end]
    if end - points[-1][0] > step * 3:
        return None
    total, previous_t, previous_v = 0.0, start, points[0][1]
    for t, value in points[1:]:
        if t - previous_t > step * 3:
            return None
        total += (t - previous_t) * previous_v
        previous_t, previous_v = t, value
    return round((total + (end - previous_t) * previous_v) / 60, 2)


def first_scale_after_high(values, start, end, profile, version):
    if profile not in ("step", "burst"):
        return None
    offsets = {1: 60, 2: 180, 3: 360, 4: 180} if profile == "step" else {1: 60, 2: 60, 3: 60, 4: 60}
    high_start = start + offsets[version]
    before_high = [v for t, v in values if t <= high_start]
    if not before_high:
        return None
    first = next((t for t, v in values if high_start <= t <= end and v > before_high[-1]), None)
    return round(first - high_start, 1) if first is not None else None


def summarize(directory, after=60, before=60):
    metadata = read_json(directory / "metadata.json")
    collection = read_json(directory / "collection.json")
    initial = read_json(directory / "events/collect-before.json")
    initial_worker = initial.get("worker", {})
    config = metadata.get("config", 1)
    minimums = {1: 1, 2: 3, 3: 5}
    if type(config) is not int or config not in minimums or metadata.get("min_workers", minimums.get(config)) != minimums[config]:
        raise ValueError("metadata config/min_workers không hợp lệ")
    autoscaler = initial.get("autoscaler")
    if ((config != 1 or autoscaler is not None) and (not isinstance(autoscaler, dict)
            or autoscaler.get("min_replica_count") != minimums[config]
            or autoscaler.get("hpa_min_replicas") != minimums[config])):
        raise ValueError("Snapshot autoscaler không xác nhận mức worker tối thiểu")
    configuration = {"queue_name": metadata.get("target", {}).get("queue_name"),
                     "region": metadata.get("target", {}).get("aws_region"),
                     "node_selector": initial_worker.get("node_selector"),
                     "containers": initial_worker.get("containers"),
                     "image_ids": sorted({c.get("imageID") for p in initial_worker.get("pods", [])
                                          for c in p.get("containers", []) if c.get("imageID")})}
    if metadata.get("scenario") != "E1" or collection.get("status") not in ("finished", "partial"):
        raise ValueError("Cần hồ sơ E1 có collection đã kết thúc")
    if metadata.get("variant") not in ("warm", "elastic"):
        raise ValueError("Variant E1 phải là warm hoặc elastic")
    k6 = read_json(directory / "raw/k6-summary.json")["metrics"]
    profile_codes = {0: "steady", 1: "step", 2: "burst"}
    db_codes = {0: "none", 1: "light", 2: "full"}
    actual_profile = profile_codes.get(k6["workload_profile_code"]["value"])
    if actual_profile != metadata.get("profile"):
        raise ValueError("PROFILE trong summary không khớp hồ sơ lượt chạy")
    version = k6.get("workload_model_version", {}).get("value", 1)
    if version not in (1, 2, 3, 4):
        raise ValueError("Phiên bản workload không được hỗ trợ")
    workload = {"model_version": version,
                "low_request_per_second": k6["workload_low_rate"]["value"],
                "high_request_per_second": k6["workload_high_rate"]["value"],
                "batch_size": k6["workload_batch_size"]["value"],
                "work_units": k6["workload_work_units"]["value"],
                "db_mode": db_codes.get(k6["workload_db_mode_code"]["value"])}
    if workload["db_mode"] is None:
        raise ValueError("DB mode trong summary không hợp lệ")
    start = k6["workload_started_at_unix_ms"]["value"] / 1000
    load_end = k6["workload_finished_at_unix_ms"]["value"] / 1000
    end = load_end + after
    if (before < 0 or start >= load_end or timestamp(collection["started_at_utc"]) > start - before
            or timestamp(collection["ended_at_utc"]) < end):
        raise ValueError("Cần thu hết workload và đủ thời gian quan sát sau workload trước khi lập báo cáo")
    step = float(collection.get("prometheus_export_step_seconds", 5))
    warnings = list(collection.get("warnings", []))
    if collection["status"] != "finished":
        warnings.append("collection_partial")
    if k6.get("dropped_iterations", {}).get("count", 0):
        warnings.append("k6_dropped_iterations")
    if k6.get("e1_failed_requests", {}).get("passes", 0):
        warnings.append("k6_failed_requests")
    completed = count_by_label(matrix(directory, "worker_tasks_processed_total"), "status", start, end)
    completed_during_load = count_by_label(matrix(directory, "worker_tasks_processed_total"), "status", start, load_end)
    buckets = count_by_label(matrix(directory, "worker_job_e2e_latency_seconds_bucket"), "le", start, end)
    if not completed:
        warnings.append("missing_worker_counter")
    if not buckets:
        warnings.append("missing_latency_histogram")
    latency = {f"p{int(q * 100)}": histogram_quantile(buckets, q) for q in (.5, .95, .99)}
    queue_wait_buckets = count_by_label(matrix(directory, "worker_job_queue_wait_seconds_bucket"), "le", start, end)
    duration_buckets = count_by_label(matrix(directory, "worker_task_duration_seconds_bucket"), "le", start, end)
    queue_wait = {"p95": histogram_quantile(queue_wait_buckets, .95)} if queue_wait_buckets else None
    task_duration = {"p95": histogram_quantile(duration_buckets, .95)} if duration_buckets else None
    if any(value is None for value in latency.values()):
        warnings.append("latency_percentile_unavailable")
    samples_path = directory / "metrics/collect-sqs-samples.jsonl"
    samples = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    queue = []
    for sample in samples:
        t = timestamp(sample["observed_at_utc"])
        counts = sample["data"]["main"]["counts"]
        if start <= t <= end:
            queue.append((t, counts["ApproximateNumberOfMessages"], counts["ApproximateNumberOfMessagesNotVisible"],
                          counts["ApproximateNumberOfMessagesDelayed"]))
    peak = max((visible + inflight for _, visible, inflight, _ in queue), default=None)
    if not queue:
        warnings.append("missing_sqs_samples_in_window")
    drain = None
    consecutive = []
    max_gap = 3 * float(collection.get("requested_interval_seconds", 5)) + 10
    # A confirmation after the fixed resource window can still establish drain.
    for sample in samples:
        t = timestamp(sample["observed_at_utc"])
        if t < load_end:
            continue
        counts = sample["data"]["main"]["counts"]
        if any(counts.values()) or (consecutive and t - consecutive[-1] > max_gap):
            consecutive = []
        if not any(counts.values()):
            consecutive.append(t)
        if len(consecutive) >= 3:
            drain = round(t - load_end, 1)
            break
    if drain is None:
        warnings.append("drain_not_confirmed")
    completed_through_drain = (count_by_label(matrix(directory, "worker_tasks_processed_total"), "status", start, load_end + drain)
                               if drain is not None else None)
    desired = matrix(directory, "desired_replicas")
    ready = matrix(directory, "ready_replicas")
    if not desired:
        warnings.append("missing_desired_replica_samples")
    ready_minutes = replica_minutes(ready, start, end, step)
    if ready_minutes is None:
        warnings.append("ready_replica_samples_incomplete")
    first_scale, first_high_scale = None, None
    if len(desired) == 1:
        values = sorted((float(t), float(v)) for t, v in desired[0].get("values", []))
        initial = [v for t, v in values if t <= start]
        if initial:
            first = next((t for t, v in values if start <= t <= end and v > initial[-1]), None)
            if first is not None:
                first_scale = round(first - start, 1)
        first_high_scale = first_scale_after_high(values, start, end, metadata.get("profile"), version)
    pending = matrix(directory, "pending_pods")
    pending_values = [float(v) for item in pending for t, v in item.get("values", [])
                      if start <= float(t) <= end and math.isfinite(float(v))]
    pending_observed = any(v > 0 for v in pending_values) if pending_values else None
    if pending_observed is None:
        warnings.append("missing_pending_samples")
    if pending_observed:
        warnings.append("pending_pod_observed")
    node_points = {}
    for item in matrix(directory, "node_info"):
        name = item.get("metric", {}).get("node")
        if name:
            for t, v in item.get("values", []):
                if start <= float(t) <= end and float(v) == 1:
                    node_points.setdefault(float(t), set()).add(name)
    if not node_points:
        warnings.append("missing_node_samples")
    elif len({tuple(sorted(nodes)) for nodes in node_points.values()}) > 1:
        warnings.append("node_set_changed_in_window")
    topology_path = directory / "events/collect-topology-samples.jsonl"
    node_minutes = None
    if topology_path.exists():
        topology = [json.loads(line) for line in topology_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        points = sorted((timestamp(x["observed_at_utc"]),
                         sum(n.get("labels", {}).get("karpenter.sh/nodepool") == "e1-orders"
                             for n in x["data"].get("nodes", []))) for x in topology)
        if points:
            node_minutes = replica_minutes([{"values": points}], start - before, end,
                                           float(collection.get("requested_interval_seconds", 5)) + 10)
    if node_minutes is None:
        warnings.append("worker_node_samples_incomplete")
    cpu_series = matrix(directory, "worker_cpu_counter")
    cpu_deltas = [counter_delta(x, start, end) for x in cpu_series]
    cpu_deltas = [v for v in cpu_deltas if v is not None]
    if not cpu_deltas:
        warnings.append("missing_cpu_samples")
    return {
        "run_id": metadata["run_id"], "variant": metadata["variant"], "profile": metadata["profile"],
        "config": config, "min_workers": minimums[config], "workload": workload,
        "configuration": configuration,
        "workload_started_utc": dt.datetime.fromtimestamp(start, dt.timezone.utc).isoformat(),
        "workload_finished_utc": dt.datetime.fromtimestamp(load_end, dt.timezone.utc).isoformat(),
        "resource_window_before_workload_seconds": before,
        "resource_window_after_workload_seconds": after,
        "accepted_jobs": k6.get("e1_accepted_jobs", {}).get("count"),
        "success_per_second_during_workload_approx": (round(completed_during_load["success"] / (load_end - start), 2)
                                                      if "success" in completed_during_load else None),
        "completed_by_status_approx": completed or None,
        "completed_by_status_through_drain_approx": completed_through_drain or None,
        "latency_seconds_approx_all_statuses": latency,
        "queue_wait_seconds_approx_all_statuses": queue_wait,
        "task_duration_seconds_approx_all_statuses": task_duration,
        "peak_visible_plus_inflight_approx": peak,
        "drain_confirmation_seconds_approx": drain,
        "ready_pod_minutes_approx": ready_minutes,
        "worker_node_minutes_approx": node_minutes,
        "worker_node_scope": "e1-orders; workload start - before to workload end + after; Kubernetes node presence, not EC2 billed duration",
        "mean_worker_cpu_millicores_approx": round(sum(cpu_deltas) / (end - start) * 1000, 1) if cpu_deltas else None,
        "first_scale_out_after_start_seconds_approx": first_scale,
        "first_scale_out_after_high_seconds_approx": first_high_scale,
        "pending_pod_observed": pending_observed,
        "warnings": sorted(set(warnings)), "validity": "not_assessed",
        "notes": "Ước lượng từ mẫu Prometheus/SQS; histogram gồm error/duplicate; counter có thể thiếu đầu series hoặc pod sống ngắn. Đối chiếu node, Pending, DLQ, lỗi và job trước kết luận.",
    }


def main():
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--before", type=int, default=60, help="giây idle trước workload trong cửa sổ Node-minutes")
    parser.add_argument("--after", type=int, default=60, help="giây quan sát sau workload; giữ giống nhau giữa các lượt")
    args = parser.parse_args()
    try:
        if args.after < 0 or args.before < 0:
            raise ValueError("--before và --after phải không âm")
        report = summarize(args.run_dir, args.after, args.before)
        output = args.run_dir / "report.json"
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(f"Đã lưu {output}. Kiểm tra warnings và đánh giá lượt trước khi so sánh.")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Không tạo được báo cáo: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
