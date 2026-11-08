#!/usr/bin/env python3
"""Build one cost.py input from an E1/E6 Step run, using a fixed 525s window."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path
import sys

WINDOW_SECONDS = 525
POOL_BY_SCENARIO = {"E1": "e1-orders", "E6": "e6-spot-orders"}
CAPACITY_BY_SCENARIO = {"E1": "on-demand", "E6": "spot"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def epoch(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def iso(value):
    return dt.datetime.fromtimestamp(value, dt.timezone.utc).isoformat()


def build(directory, price, price_date, price_source):
    metadata = read_json(directory / "metadata.json")
    scenario = metadata.get("scenario")
    if scenario not in POOL_BY_SCENARIO or metadata.get("variant") != "elastic" or metadata.get("profile") != "step" or metadata.get("config", 1) != 1:
        raise ValueError("Chỉ hỗ trợ E1 Config 1 Elastic Step hoặc E6 Elastic Step")
    if not math.isfinite(price) or price <= 0 or not price_date.strip() or not price_source.strip():
        raise ValueError("Cần giá dương, ngày và nguồn giá")
    collection = read_json(directory / "collection.json")
    if collection.get("status") != "finished":
        raise ValueError("Chỉ hỗ trợ collection đã finished")
    metrics = read_json(directory / "raw/k6-summary.json")["metrics"]
    if (metrics.get("workload_model_version", {}).get("value") != 4
            or metrics.get("workload_profile_code", {}).get("value") != 1
            or metrics.get("workload_low_rate", {}).get("value") != 5
            or metrics.get("workload_high_rate", {}).get("value") != 20
            or metrics.get("workload_batch_size", {}).get("value") != 1
            or metrics.get("workload_work_units", {}).get("value") != 100
            or metrics.get("workload_db_mode_code", {}).get("value") != 1):
        raise ValueError("Workload không khớp Step v4 và cấu hình E1")
    start = float(metrics["workload_started_at_unix_ms"]["value"]) / 1000
    load_end = float(metrics["workload_finished_at_unix_ms"]["value"]) / 1000
    end = start + WINDOW_SECONDS
    if not start < load_end <= end or epoch(collection["started_at_utc"]) > start or epoch(collection["ended_at_utc"]) < end:
        raise ValueError("Collection/workload không bao phủ cửa sổ 525s")
    accepted = metrics.get("e1_accepted_jobs", {}).get("count", 0)
    if not isinstance(accepted, (int, float)) or isinstance(accepted, bool) or not math.isfinite(accepted) or accepted <= 0:
        raise ValueError("Không có số job được chấp nhận hợp lệ")

    pool = POOL_BY_SCENARIO[scenario]
    expected_capacity = CAPACITY_BY_SCENARIO[scenario]
    samples = []
    for line in (directory / "events/collect-topology-samples.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sample = json.loads(line)
        groups = {}
        for node in sample["data"]["nodes"]:
            labels = node.get("labels", {})
            if labels.get("karpenter.sh/nodepool") != pool:
                continue
            kind = labels.get("node.kubernetes.io/instance-type")
            az = labels.get("topology.kubernetes.io/zone")
            capacity = labels.get("karpenter.sh/capacity-type", "on-demand" if scenario == "E1" else None)
            if not kind or not az or capacity != expected_capacity:
                raise ValueError("Thiếu type/AZ hoặc capacity type node không khớp")
            key = (kind, az, capacity)
            groups[key] = groups.get(key, 0) + 1
        samples.append((epoch(sample["observed_at_utc"]), groups))
    samples.sort(key=lambda item: item[0])
    prior = [item for item in samples if item[0] <= start]
    following = [item for item in samples if item[0] >= end]
    if not prior or not following:
        raise ValueError("Thiếu mẫu topology trước đầu hoặc sau cuối cửa sổ")
    points = [prior[-1]] + [item for item in samples if start < item[0] < end] + [following[0]]
    max_gap = 3 * float(collection.get("requested_interval_seconds", 5)) + 10
    if any(b[0] - a[0] > max_gap for a, b in zip(points, points[1:])):
        raise ValueError("Mẫu topology có khoảng trống quá lớn trong cửa sổ")
    totals = {}
    for (t, groups), (next_t, _) in zip(points, points[1:]):
        seconds = max(0, min(next_t, end) - max(t, start))
        for key, count in groups.items():
            totals[key] = totals.get(key, 0) + seconds * count
    if not totals or sum(totals.values()) <= 0:
        raise ValueError("Không có worker node trong cửa sổ")
    groups = [{"instance_type": kind, "availability_zone": az, "capacity_type": capacity,
               "node_seconds": round(seconds, 3), "idle_node_seconds": None, "hourly_price": price}
              for (kind, az, capacity), seconds in sorted(totals.items())]
    return {"run_id": f"{metadata['run_id']}-525s", "source_run": metadata["run_id"],
            "configuration": f"elastic-{expected_capacity}", "workload": "E1-step-v4",
            "region": metadata["target"]["aws_region"], "currency": "USD",
            "price_date": price_date, "price_source": price_source,
            "window_start": iso(start), "window_end": iso(end),
            "processed_success": accepted,
            "success_count_method": "Giả định tất cả job API chấp nhận hoàn thành; chưa đối soát job ID",
            "instances": groups,
            "limitations": "Node Kubernetes được lấy mẫu là proxy EC2; một đơn giá nhập được áp cho mọi node/AZ và toàn bộ cửa sổ. Kiểm tra giá thực tế và drain thủ công."}


def main():
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--hourly-price", required=True, type=float)
    parser.add_argument("--price-date", required=True)
    parser.add_argument("--price-source", required=True)
    parser.add_argument("--assume-accepted-success", required=True, action="store_true",
                        help="công khai giả định job được API chấp nhận đều thành công")
    parser.add_argument("--output", required=True, type=Path, help="file mới; không ghi đè")
    args = parser.parse_args()
    try:
        data = build(args.run_dir, args.hourly_price, args.price_date, args.price_source)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        print(f"Đã lưu {args.output}; kiểm tra giá theo AZ và drain trước khi so sánh.")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Không tạo được input: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
